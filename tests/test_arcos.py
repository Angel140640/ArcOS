import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcos import auth as authmod  # noqa: E402
from arcos import boot, cli  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {
            "ARCOS_HOME": os.path.join(self.tmp, "data"),
            "HOME": self.tmp,
            "ARCOS_DRY_RUN": "1",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *argv, passwords=()):
        """Roda um comando; 'passwords' alimenta o getpass em ordem."""
        queue = list(passwords)

        def fake_ask(prompt=""):
            # acabou a fila = o usuário apertou Ctrl+D
            if not queue:
                raise EOFError
            item = queue.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item

        out = io.StringIO()
        with mock.patch.object(authmod, "ask_password", fake_ask), redirect_stdout(out):
            rc = cli.main(list(argv))
        return rc, out.getvalue()


class TestApps(Base):
    def test_add_list_open(self):
        # primeiro acesso cria a senha (nova + confirmação)
        rc, out = self.run_cli("add", "com.discord", "--name", "Discord", "--alias", "dc", passwords=["segredo1", "segredo1"])
        self.assertEqual(rc, 0, out)
        rc, out = self.run_cli("add", "com.whatsapp", "--name", "WhatsApp")
        self.assertEqual(rc, 0, out)  # sessão ainda válida
        rc, out = self.run_cli("list")
        self.assertIn("[01] Discord", out)
        self.assertIn("[02] WhatsApp", out)
        rc, out = self.run_cli("open", "02")
        self.assertEqual(rc, 0)
        self.assertIn("Abrindo WhatsApp", out)
        self.assertIn("-p com.whatsapp", out)  # dry-run mostra o comando
        rc, out = self.run_cli("open", "dc")
        self.assertIn("com.discord", out)

    def test_bad_input(self):
        self.run_cli("auth", passwords=["segredo1", "segredo1"])
        self.assertEqual(self.run_cli("add", "nao-e-pacote")[0], 1)
        self.assertEqual(self.run_cli("open", "99")[0], 1)
        self.run_cli("add", "com.a.b", "--alias", "x")
        self.assertEqual(self.run_cli("add", "com.c.d", "--alias", "x")[0], 1)  # alias duplicado
        self.assertEqual(self.run_cli("add", "com.a.b")[0], 1)  # pacote duplicado
        self.assertEqual(self.run_cli("add", "com.e.f", "--alias", "12")[0], 1)  # alias numérico

    def test_codes_reused_and_remove(self):
        self.run_cli("auth", passwords=["segredo1", "segredo1"])
        self.run_cli("add", "com.a.a")
        self.run_cli("add", "com.b.b")
        self.run_cli("remove", "1", "-y")
        rc, out = self.run_cli("add", "com.c.c")
        self.assertIn("[01]", out)

    def test_search_info_alias(self):
        self.run_cli("auth", passwords=["segredo1", "segredo1"])
        self.run_cli("add", "com.spotify.music", "--name", "Spotify")
        self.assertIn("Spotify", self.run_cli("search", "spot")[1])
        self.run_cli("alias", "1", "mus")
        self.assertIn("mus", self.run_cli("info", "mus")[1])
        self.run_cli("alias", "1", "-")
        self.assertEqual(self.run_cli("info", "mus")[0], 1)


class TestAuth(Base):
    def test_wrong_password_and_lockout(self):
        self.run_cli("auth", passwords=["segredo1", "segredo1"])
        self.run_cli("lock")
        self.run_cli("config", "set", "max_attempts", "2", passwords=["segredo1"])
        self.run_cli("lock")
        rc, out = self.run_cli("list", passwords=["errada1", "errada2"])
        self.assertEqual(rc, 1)
        self.assertIn("Senha incorreta", out)
        # agora está bloqueado: nem a senha certa funciona
        rc, out = self.run_cli("list", passwords=["segredo1"])
        self.assertEqual(rc, 1)
        self.assertIn("Aguarde", out)

    def test_right_password_after_lock(self):
        self.run_cli("auth", passwords=["segredo1", "segredo1"])
        self.run_cli("lock")
        rc, _ = self.run_cli("list", passwords=["segredo1"])
        self.assertEqual(rc, 0)

    def test_session_timeout_zero_always_asks(self):
        self.run_cli("auth", passwords=["segredo1", "segredo1"])
        self.run_cli("config", "set", "session_timeout", "0")
        self.run_cli("lock")
        self.assertEqual(self.run_cli("list", passwords=["segredo1"])[0], 0)
        rc, _ = self.run_cli("list", passwords=[])  # sem senha disponível
        self.assertEqual(rc, 1)

    def test_short_password_rejected(self):
        rc, _ = self.run_cli("auth", passwords=["abc", ])
        self.assertEqual(rc, 1)

    def test_passwd_change(self):
        self.run_cli("auth", passwords=["segredo1", "segredo1"])
        rc, _ = self.run_cli("passwd", passwords=["segredo1", "novasenha", "novasenha"])
        self.assertEqual(rc, 0)
        self.run_cli("lock")
        self.assertEqual(self.run_cli("list", passwords=["segredo1"])[0], 1)
        self.assertEqual(self.run_cli("list", passwords=["novasenha"])[0], 0)

    def test_password_not_stored_plain(self):
        self.run_cli("auth", passwords=["segredo1", "segredo1"])
        for p in Path(os.environ["ARCOS_HOME"]).iterdir():
            self.assertNotIn("segredo1", p.read_text())
            self.assertEqual(p.stat().st_mode & 0o077, 0, p)


class TestMisc(Base):
    def test_config_validation(self):
        self.run_cli("auth", passwords=["segredo1", "segredo1"])
        self.assertEqual(self.run_cli("config", "set", "theme", "rosa")[0], 1)
        self.assertEqual(self.run_cli("config", "set", "max_attempts", "0")[0], 1)
        self.assertEqual(self.run_cli("config", "set", "prompt", "a b")[0], 1)
        self.assertEqual(self.run_cli("config", "set", "prompt", "arc")[0], 0)
        self.assertEqual(self.run_cli("config", "get", "prompt")[1].strip(), "arc")

    def test_history(self):
        self.run_cli("auth", passwords=["segredo1", "segredo1"])
        self.run_cli("add", "com.a.a")
        rc, out = self.run_cli("history")
        self.assertIn("add com.a.a", out)

    def test_unauthenticated_commands_blocked(self):
        # inclui comandos com argumento chamado 'name' (regressão: pulavam a senha)
        for c in (["list"], ["open", "1"], ["history"], ["add", "com.a.a"],
                  ["add", "com.a.a", "--name", "X"], ["alias", "1", "foo"], ["search", "x"],
                  ["info", "1"], ["remove", "1", "-y"], ["scan"], ["bash"], ["boot", "status"]):
            rc, _ = self.run_cli(*c, passwords=[EOFError()])
            self.assertEqual(rc, 1, c)

    def test_unknown_and_help(self):
        self.assertEqual(self.run_cli("xyz")[0], 2)
        self.assertIn("arc-os", self.run_cli("help")[1])
        self.assertEqual(self.run_cli("version")[0], 0)
        self.assertEqual(self.run_cli("help", "open")[0], 0)

    def test_boot_install_remove(self):
        self.run_cli("auth", passwords=["segredo1", "segredo1"])
        Path(self.tmp, ".bashrc").write_text("alias x=y\n")
        self.assertEqual(self.run_cli("boot", "install", "--kiosk")[0], 0)
        text = Path(self.tmp, ".bashrc").read_text()
        self.assertIn("exec arc-os shell", text)
        self.assertIn("alias x=y", text)
        self.run_cli("boot", "install")  # reinstala sem duplicar
        text = Path(self.tmp, ".bashrc").read_text()
        self.assertEqual(text.count(boot.MARK_START), 1)
        self.assertNotIn("exec arc-os", text)
        self.assertTrue(boot.boot_script_path().exists())
        self.run_cli("boot", "remove")
        self.assertEqual(Path(self.tmp, ".bashrc").read_text(), "alias x=y\n")
        self.assertFalse(boot.boot_script_path().exists())

    def test_shell_loop(self):
        self.run_cli("auth", passwords=["segredo1", "segredo1"])
        inputs = iter(["add com.discord --name Discord", "arc-os list", "open 1", "bogus", "'aspas", "exit"])
        out = io.StringIO()
        with mock.patch("builtins.input", lambda prompt="": next(inputs)), redirect_stdout(out):
            cli.run_shell(cli.Ctx())
        text = out.getvalue()
        self.assertIn("[01] Discord", text)
        self.assertIn("Abrindo Discord", text)
        self.assertIn("Comando desconhecido", text)
        self.assertIn("Sessão encerrada", text)
        # ao sair do shell a sessão é encerrada
        self.assertEqual(self.run_cli("list", passwords=[EOFError()])[0], 1)

    def test_corrupt_apps_file(self):
        Path(os.environ["ARCOS_HOME"]).mkdir(parents=True, exist_ok=True)
        Path(os.environ["ARCOS_HOME"], "apps.json").write_text("{quebrado")
        self.run_cli("auth", passwords=["segredo1", "segredo1"])
        rc, out = self.run_cli("list")
        self.assertEqual(rc, 0)
        self.assertIn("Nenhum aplicativo", out)


if __name__ == "__main__":
    unittest.main()
