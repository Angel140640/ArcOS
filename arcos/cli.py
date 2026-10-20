"""Interpretador de comandos do ArcOS (modo comando único e modo shell)."""

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import __version__, apps, boot, ui
from . import auth as authmod
from .config import DEFAULTS, SCHEMA, THEMES, Config, home
from .database import AppDB
from .logger import Logger

HELP = """ArcOS — launcher de aplicativos para o Termux

Uso: arc-os <comando> [argumentos]      (ou 'arc-os shell' para a sessão interativa)

Aplicativos
  list                       lista os aplicativos (código numerado)
  open <código|alias>        abre um aplicativo
  search <texto>             procura por nome, alias ou pacote
  info <código|alias>        detalhes de um aplicativo
  add <pacote>               cadastra um aplicativo (--name, --alias, --activity)
  remove <código|alias>      remove um cadastro
  alias <código> <nome>      define um apelido ('-' remove)
  scan [--import]            tenta descobrir apps instalados (pode exigir ADB)

Sessão
  auth                       autentica a sessão
  lock                       encerra a sessão
  passwd                     troca a senha
  status                     estado do ArcOS
  history [-n N]             histórico de comandos

Sistema
  shell                      abre o terminal do ArcOS
  bash                       sai para o shell real (pede senha)
  config [get|set|reset]     configurações
  theme [nome]               muda o tema do terminal
  boot install|remove|status inicialização automática
  doctor                     verifica a instalação
  version                    mostra a versão
  help [comando]             esta ajuda

Protegidos por senha: list, open, search, info, add, remove, alias, scan, history, bash, boot."""

PROTECTED = {"list", "open", "search", "info", "add", "remove", "alias", "scan", "history", "bash", "boot"}
NO_LOG = {"help", "version"}


class Ctx:
    def __init__(self):
        self.cfg = Config()
        ui.set_theme(self.cfg.get("theme"))
        self.auth = authmod.Auth(self.cfg)
        self.db = AppDB()
        self.log = Logger(self.cfg)
        self.parser, self.commands = build_parser()
        self.in_shell = False


# ---------------------------------------------------------------- utilitários
def fmt_secs(n):
    m, s = divmod(int(n), 60)
    return "%dm%02ds" % (m, s) if m else "%ds" % s


def need_auth(ctx):
    return authmod.require(ctx.auth, ctx.cfg)


def is_termux():
    return "com.termux" in os.environ.get("PREFIX", "") or Path("/data/data/com.termux").exists()


def app_line(a, verbose=False):
    line = "[%02d] %s" % (a["code"], ui.clean(a["name"]))
    extra = []
    if a.get("alias"):
        extra.append("alias: %s" % a["alias"])
    if verbose:
        extra.append(ui.clean(a["package"]))
    return line + (ui.paint("  (" + ", ".join(extra) + ")", dim=True, fixed="37") if extra else "")


# ------------------------------------------------------------------ comandos
def cmd_help(ctx, a):
    if a.topic:
        sp = ctx.commands.get(a.topic)
        if not sp:
            ui.err("Comando desconhecido: %s" % a.topic)
            return 1
        sp.print_help()
    else:
        print(HELP)
    return 0


def cmd_list(ctx, a):
    items = ctx.db.all()
    if not items:
        print("Nenhum aplicativo cadastrado. Use: add <pacote>  (ex.: add com.discord)")
        return 0
    for app in items:
        print(app_line(app, a.verbose))
    return 0


def cmd_open(ctx, a):
    app = ctx.db.find(a.ref)
    if not app:
        ui.err("Aplicativo '%s' não encontrado. Use 'list'." % ui.clean(a.ref))
        return 1
    print("Abrindo %s..." % ui.clean(app["name"]))
    good, msg, _ = apps.launch(app)
    if good:
        ui.dim(msg)
        return 0
    ui.err("Não foi possível abrir: %s" % ui.clean(msg))
    ui.dim("Dica: se disser 'unable to resolve Intent', o Android escondeu o app do Termux (visibilidade de pacotes).")
    ui.dim("Cadastre com a activity: add <pacote> --activity <Classe>  (veja 'help add').")
    return 1


def cmd_search(ctx, a):
    found = ctx.db.search(a.query)
    if not found:
        print("Nada encontrado para '%s'." % ui.clean(a.query))
        return 1
    for app in found:
        print(app_line(app, True))
    return 0


def cmd_info(ctx, a):
    app = ctx.db.find(a.ref)
    if not app:
        ui.err("Aplicativo '%s' não encontrado." % ui.clean(a.ref))
        return 1
    print("Código:   %02d" % app["code"])
    print("Nome:     %s" % ui.clean(app["name"]))
    print("Pacote:   %s" % ui.clean(app["package"]))
    print("Alias:    %s" % (app.get("alias") or "-"))
    print("Activity: %s" % (ui.clean(app["activity"]) if app.get("activity") else "(automática)"))
    return 0


def cmd_add(ctx, a):
    try:
        app = ctx.db.add(a.package, a.name, a.activity, a.alias)
    except ValueError as e:
        ui.err(str(e))
        return 1
    ui.ok("Cadastrado: " + app_line(app, True))
    return 0


def cmd_remove(ctx, a):
    app = ctx.db.find(a.ref)
    if not app:
        ui.err("Aplicativo '%s' não encontrado." % ui.clean(a.ref))
        return 1
    if not a.yes:
        try:
            resp = input("Remover [%02d] %s? [s/N] " % (app["code"], ui.clean(app["name"])))
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if resp.strip().lower() not in ("s", "sim", "y", "yes"):
            print("Cancelado.")
            return 1
    ctx.db.remove(app["code"])
    ui.ok("Removido: %s (o código %02d fica livre para o próximo cadastro)" % (ui.clean(app["name"]), app["code"]))
    return 0


def cmd_alias(ctx, a):
    app = ctx.db.find(a.ref)
    if not app:
        ui.err("Aplicativo '%s' não encontrado." % ui.clean(a.ref))
        return 1
    try:
        ctx.db.set_alias(app["code"], None if a.name == "-" else a.name)
    except ValueError as e:
        ui.err(str(e))
        return 1
    ui.ok("Alias atualizado: " + app_line(ctx.db.find(str(app["code"]))))
    return 0


def cmd_scan(ctx, a):
    pkgs = apps.scan_installed()
    if pkgs is None:
        ui.err("O Android não deixou listar os apps (normal sem ADB/root).")
        ui.dim("Cadastre manualmente: add com.pacote  — o nome do pacote aparece na URL do app na Play Store.")
        return 1
    known = {x["package"] for x in ctx.db.all()}
    new = [p for p in pkgs if p not in known]
    if not new:
        print("Nenhum aplicativo novo.")
        return 0
    for p in new:
        if a.do_import:
            try:
                ui.ok("Cadastrado: " + app_line(ctx.db.add(p), True))
            except ValueError as e:
                ui.warn("%s: %s" % (p, e))
        else:
            print("  " + p)
    if not a.do_import:
        ui.dim("Use 'scan --import' para cadastrar todos de uma vez.")
    return 0


def cmd_auth(ctx, a):
    left = ctx.auth.session_remaining()
    if left > 0:
        ui.ok("Sessão já autenticada (restam %s)." % fmt_secs(left))
        return 0
    return 0 if need_auth(ctx) else 1


def cmd_lock(ctx, a):
    ctx.auth.end_session()
    ui.ok("Sessão encerrada. A senha será pedida de novo.")
    return 0


def cmd_passwd(ctx, a):
    if not ctx.auth.configured():
        return 0 if need_auth(ctx) else 1
    try:
        cur = authmod.ask_password("Senha atual: ")
        if not ctx.auth.verify(cur):
            ui.err("Senha incorreta.")
            return 1
    except authmod.AuthError as e:
        ui.err(str(e))
        return 1
    except (EOFError, KeyboardInterrupt):
        print()
        return 1
    new = authmod.prompt_new_password()
    if new is None:
        return 1
    ctx.auth.set_password(new)
    ctx.auth.start_session()
    ui.ok("Senha alterada.")
    return 0


def cmd_status(ctx, a):
    left = ctx.auth.session_remaining()
    lock = ctx.auth.lock_remaining()
    if lock:
        sess = "BLOQUEADO (%ds)" % lock
    elif left:
        sess = "autenticada (restam %s)" % fmt_secs(left)
    else:
        sess = "bloqueada"
    print("ArcOS v%s" % __version__)
    print("Sessão:    %s" % sess)
    print("Senha:     %s" % ("definida" if ctx.auth.configured() else "não definida"))
    print("Apps:      %d cadastrados" % len(ctx.db.all()))
    print("Ambiente:  %s" % ("Termux" if is_termux() else "fora do Termux"))
    print("Tema:      %s" % ctx.cfg.get("theme"))
    print("Dados:     %s" % home())
    return 0


def cmd_history(ctx, a):
    entries = ctx.log.tail(max(1, a.n))
    if not entries:
        print("Histórico vazio.")
        return 0
    for e in entries:
        when = time.strftime("%d/%m %H:%M:%S", time.localtime(e.get("t", 0)))
        mark = ui.paint("✔", fixed="32") if e.get("ok") else ui.paint("✖", fixed="31")
        print("%s  %s  %s" % (when, mark, ui.clean(e.get("cmd", ""))))
    return 0


def cmd_theme(ctx, a):
    if not a.name:
        for t in THEMES:
            cur = " (atual)" if t == ctx.cfg.get("theme") else ""
            print("  %s%s" % (t, cur))
        return 0
    try:
        ctx.cfg.set("theme", a.name)
    except ValueError as e:
        ui.err(str(e))
        return 1
    ui.set_theme(a.name)
    ui.ok("Tema alterado para %s." % ui.paint(a.name, bold=True))
    return 0


def cmd_config(ctx, a):
    if a.action in (None, "get") and not a.key:
        for k in SCHEMA:
            print("%-16s %s" % (k, ctx.cfg.get(k)))
        return 0
    if a.action in (None, "get"):
        if a.key not in SCHEMA:
            ui.err("Chave desconhecida: %s" % ui.clean(a.key))
            return 1
        print(ctx.cfg.get(a.key))
        return 0
    if not need_auth(ctx):
        return 1
    if a.action == "reset":
        ctx.cfg.reset()
        ui.set_theme(ctx.cfg.get("theme"))
        ui.ok("Configurações restauradas.")
        return 0
    if not a.key or a.value is None:
        ui.err("Uso: config set <chave> <valor>")
        return 1
    try:
        ctx.cfg.set(a.key, a.value)
    except ValueError as e:
        ui.err(str(e))
        return 1
    ui.set_theme(ctx.cfg.get("theme"))
    ui.ok("%s = %s" % (a.key, ctx.cfg.get(a.key)))
    return 0


def cmd_boot(ctx, a):
    if a.action == "install":
        boot.install(kiosk=a.kiosk)
        ui.ok("Autostart instalado em ~/.bashrc e ~/.termux/boot/arc-os-boot.sh")
        if a.kiosk:
            ui.warn("Modo kiosk: o Termux abre direto no ArcOS. Use o comando 'bash' dentro dele para sair para o shell.")
        ui.dim("Para iniciar no boot: instale o app Termux:Boot, abra-o uma vez e dê ao Termux")
        ui.dim("a permissão 'Exibir sobre outros apps'. Desative a otimização de bateria do Termux.")
        return 0
    if a.action == "remove":
        if boot.remove():
            ui.ok("Autostart removido.")
        else:
            print("Nada para remover.")
        return 0
    st = boot.status()
    print("~/.bashrc:        %s" % (("ativo (kiosk)" if st["kiosk"] else "ativo") if st["bashrc"] else "inativo"))
    print("Termux:Boot:      %s" % ("script presente" if st["boot_script"] else "sem script"))
    return 0


def cmd_bash(ctx, a):
    shell = os.environ.get("SHELL") or shutil.which("bash") or shutil.which("sh") or "sh"
    if os.environ.get("ARCOS_DRY_RUN"):
        print("[dry-run] %s" % shell)
        return 0
    print("Saindo para o shell real. Digite 'exit' para voltar.")
    env = dict(os.environ, ARCOS_STARTED="1")
    try:
        return subprocess.call([shell], env=env)
    except OSError as e:
        ui.err("Não foi possível abrir %s: %s" % (shell, e))
        return 1


def cmd_doctor(ctx, a):
    bad = 0

    def check(good, label, fix="", fatal=True):
        nonlocal bad
        if good:
            ui.ok(label)
        elif fatal:
            bad += 1
            ui.err(label + (" — " + fix if fix else ""))
        else:
            ui.warn(label + (" — " + fix if fix else ""))

    check(sys.version_info >= (3, 8), "Python %d.%d" % sys.version_info[:2], "precisa de 3.8+")
    termux = is_termux()
    check(termux, "Rodando no Termux", "fora do Termux o ArcOS não consegue abrir apps", fatal=False)
    check(apps.have("am"), "Comando 'am' (abrir apps)", "instale: pkg install termux-tools", fatal=termux)
    check(apps.have("pm"), "Comando 'pm' (para o 'scan')", "opcional; sem ele use 'add'", fatal=False)
    try:
        mode = home().stat().st_mode & 0o077
    except OSError:
        mode = 0
    check(mode == 0, "Pasta de dados privada (%s)" % home(), "rode: chmod 700 %s" % home())
    check(ctx.auth.configured(), "Senha definida", "rode: arc-os auth", fatal=False)
    check(len(ctx.db.all()) > 0, "Aplicativos cadastrados: %d" % len(ctx.db.all()), "use: arc-os add <pacote>", fatal=False)
    st = boot.status()
    check(st["bashrc"], "Autostart no ~/.bashrc", "opcional: arc-os boot install", fatal=False)
    check(st["boot_script"], "Script do Termux:Boot", "opcional: arc-os boot install", fatal=False)
    return 1 if bad else 0


def cmd_version(ctx, a):
    print("ArcOS v%s" % __version__)
    return 0


def cmd_shell(ctx, a):
    if ctx.in_shell:
        ui.warn("Você já está no shell do ArcOS.")
        return 0
    return run_shell(ctx)


def cmd_exit(ctx, a):
    print("Use 'arc-os shell' para abrir a interface; dentro dela, 'exit' fecha.")
    return 0


# ---------------------------------------------------------------- parser
def build_parser():
    p = argparse.ArgumentParser(prog="arc-os", add_help=False)
    sub = p.add_subparsers(dest="cmd", metavar="<comando>")

    def cmd(name, fn, text, aliases=()):
        sp = sub.add_parser(name, help=text, description=text, aliases=list(aliases), prog="arc-os " + name)
        # '_cmd' (e não 'name'): comandos como 'add --name' e 'alias' têm um argumento
        # chamado 'name' que sobrescreveria o nome do comando e pularia a checagem de senha.
        sp.set_defaults(func=fn, _cmd=name)
        return sp

    cmd("help", cmd_help, "mostra os comandos").add_argument("topic", nargs="?")
    sp = cmd("list", cmd_list, "lista os aplicativos", ["ls"])
    sp.add_argument("-v", "--verbose", action="store_true", help="mostra também o pacote")
    cmd("open", cmd_open, "abre um aplicativo", ["o"]).add_argument("ref", metavar="código")
    cmd("search", cmd_search, "procura por nome, alias ou pacote").add_argument("query")
    cmd("info", cmd_info, "detalhes de um aplicativo").add_argument("ref", metavar="código")
    sp = cmd("add", cmd_add, "cadastra um aplicativo")
    sp.add_argument("package", metavar="pacote")
    sp.add_argument("--name")
    sp.add_argument("--alias")
    sp.add_argument("--activity", help="activity específica (opcional), ex.: .MainActivity")
    sp = cmd("remove", cmd_remove, "remove um cadastro", ["rm"])
    sp.add_argument("ref", metavar="código")
    sp.add_argument("-y", "--yes", action="store_true", help="não pedir confirmação")
    sp = cmd("alias", cmd_alias, "define um apelido para o código")
    sp.add_argument("ref", metavar="código")
    sp.add_argument("name", metavar="nome", help="'-' remove o alias")
    cmd("scan", cmd_scan, "tenta descobrir apps instalados").add_argument("--import", dest="do_import", action="store_true")
    cmd("auth", cmd_auth, "autentica a sessão")
    cmd("lock", cmd_lock, "encerra a sessão")
    cmd("passwd", cmd_passwd, "troca a senha")
    cmd("status", cmd_status, "estado do ArcOS")
    cmd("history", cmd_history, "histórico de comandos").add_argument("-n", type=int, default=15)
    cmd("theme", cmd_theme, "muda o tema").add_argument("name", nargs="?")
    sp = cmd("config", cmd_config, "configurações")
    sp.add_argument("action", nargs="?", choices=["get", "set", "reset"])
    sp.add_argument("key", nargs="?")
    sp.add_argument("value", nargs="?")
    sp = cmd("boot", cmd_boot, "inicialização automática")
    sp.add_argument("action", choices=["install", "remove", "status"])
    sp.add_argument("--kiosk", action="store_true", help="o Termux abre direto no ArcOS (exec)")
    cmd("bash", cmd_bash, "sai para o shell real (pede senha)", ["sh"])
    cmd("doctor", cmd_doctor, "verifica a instalação")
    cmd("version", cmd_version, "mostra a versão")
    cmd("shell", cmd_shell, "abre o terminal interativo do ArcOS")
    cmd("exit", cmd_exit, "fecha o shell", ["quit"])
    return p, sub.choices


# ---------------------------------------------------------------- execução
def dispatch(ctx, argv):
    if not argv:
        print(HELP)
        return 0
    if argv[0] in ("-h", "--help"):
        argv = ["help"] + argv[1:]
    elif argv[0] in ("-V", "--version"):
        argv = ["version"]
    if argv[0] not in ctx.commands:
        ui.err("Comando desconhecido: %s. Use 'help'." % ui.clean(argv[0]))
        return 2
    try:
        args = ctx.parser.parse_args(argv)
    except SystemExit as e:  # argparse sai por conta própria em erro ou -h
        return e.code if isinstance(e.code, int) else 0

    name = args._cmd
    text = " ".join(argv)
    if name in PROTECTED and not need_auth(ctx):
        ctx.log.log(text, False, "auth")
        return 1
    try:
        rc = args.func(ctx, args) or 0
    except Exception as e:  # um erro num comando nunca deve derrubar o shell
        ui.err("Erro inesperado em '%s': %s: %s" % (name, type(e).__name__, e))
        rc = 1
    if name not in NO_LOG:
        ctx.log.log(text, rc == 0)
    return rc


def _prompt(ctx):
    name = ctx.cfg.get("prompt")
    if ctx.auth.session_remaining() > 0:
        return ui.rl_paint(name, bold=True) + ui.rl_paint(" ●", fixed="32") + " > "
    return ui.rl_paint(name, bold=True) + " > "


def run_shell(ctx):
    try:
        import readline  # noqa: F401  (histórico e edição de linha)
    except ImportError:
        pass
    ctx.in_shell = True
    if ctx.cfg.get("banner"):
        ui.banner(__version__)
    print("Sistema iniciado. 'help' mostra os comandos, 'exit' sai.\n")
    try:
        while True:
            try:
                line = input(_prompt(ctx))
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                continue
            try:
                tokens = shlex.split(line)
            except ValueError as e:
                ui.err("Comando inválido: %s" % e)
                continue
            if tokens and tokens[0] == "arc-os":
                tokens = tokens[1:]
            if not tokens:
                continue
            if tokens[0] in ("exit", "quit"):
                break
            if tokens[0] in ("clear", "cls"):
                print("\033[2J\033[H", end="")
                continue
            try:
                dispatch(ctx, tokens)
            except KeyboardInterrupt:
                print()
    finally:
        ctx.auth.end_session()
        ctx.in_shell = False
        print("Sessão encerrada.")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        return dispatch(Ctx(), argv)
    except KeyboardInterrupt:
        print()
        return 130
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
