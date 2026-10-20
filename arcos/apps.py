"""Abertura de aplicativos Android a partir do Termux.

Tenta várias estratégias, da mais precisa para a mais genérica. Nenhuma exige root.
Com ARCOS_DRY_RUN=1 os comandos só são impressos (útil para testar fora do Android).
"""

import errno
import os
import shutil
import subprocess

LAUNCHER = "android.intent.category.LAUNCHER"


def _dry():
    return bool(os.environ.get("ARCOS_DRY_RUN"))


def have(tool):
    return _dry() or shutil.which(tool) is not None


def _run(cmd):
    if _dry():
        print("[dry-run] " + " ".join(cmd))
        return 0, ""
    try:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        except OSError as e:
            if e.errno != errno.ENOEXEC or not shutil.which(cmd[0]):
                raise
            # scripts do Android (ex.: monkey) vêm sem '#!': roda pelo sh
            r = subprocess.run(["sh", shutil.which(cmd[0])] + cmd[1:], capture_output=True, text=True, timeout=15)
    except FileNotFoundError:
        return 127, "%s não encontrado" % cmd[0]
    except subprocess.TimeoutExpired:
        return 124, "tempo esgotado"
    except OSError as e:
        return 126, "%s: %s" % (cmd[0], e.strerror or e)
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def _failed(rc, out):
    if rc != 0:
        return True
    low = out.lower()
    return any(w in low for w in ("error", "exception", "aborted", "unable to resolve"))


def _resolve_activity(pkg):
    """Descobre a activity de launcher via `cmd package resolve-activity` (nem sempre disponível)."""
    if not have("cmd"):
        return None
    rc, out = _run(["cmd", "package", "resolve-activity", "--brief", "-c", LAUNCHER, pkg])
    if rc != 0:
        return None
    for line in reversed(out.splitlines()):
        line = line.strip()
        if "/" in line and " " not in line:
            return line
    return None


def launch(app):
    """Abre o aplicativo. Retorna (ok, mensagem, método)."""
    pkg = app["package"]
    activity = app.get("activity")
    attempts = []
    if activity:
        comp = activity if "/" in activity else "%s/%s" % (pkg, activity)
        attempts.append(("am -n", ["am", "start", "--user", "0", "-n", comp]))
    attempts.append((
        "am launcher",
        ["am", "start", "--user", "0", "-a", "android.intent.action.MAIN", "-c", LAUNCHER, "-p", pkg],
    ))
    attempts.append(("monkey", ["monkey", "-p", pkg, "-c", LAUNCHER, "1"]))

    last = "nenhum método disponível (am/monkey não encontrados)"
    errors = []
    for method, cmd in attempts:
        if not have(cmd[0]):
            continue
        rc, out = _run(cmd)
        if not _failed(rc, out):
            return True, "Aberto via %s" % method, method
        last = out.splitlines()[-1] if out else "falhou (código %d)" % rc
        errors.append("%s: %s" % (method, last))

    comp = _resolve_activity(pkg)
    if comp and have("am"):
        rc, out = _run(["am", "start", "--user", "0", "-n", comp])
        if not _failed(rc, out):
            return True, "Aberto via resolve-activity", "resolve"
        last = out.splitlines()[-1] if out else last
        errors.append("resolve: %s" % last)
    return False, " | ".join(errors) or last, None


def scan_installed():
    """Lista pacotes de terceiros (`pm list packages -3`). Retorna None se o Android não deixar."""
    if _dry():
        return []
    if not have("pm"):
        return None
    rc, out = _run(["pm", "list", "packages", "-3"])
    if rc != 0 or "package:" not in out:
        return None
    return sorted(line[len("package:"):].strip() for line in out.splitlines() if line.startswith("package:"))
