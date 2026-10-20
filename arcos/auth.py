"""Autenticação: senha com PBKDF2 + sessão com validade + bloqueio por tentativas erradas."""

import getpass
import hashlib
import hmac
import secrets
import time

from .config import home, read_json, write_json

ITERATIONS = 200_000
MIN_LEN = 6


class AuthError(Exception):
    pass


class Auth:
    def __init__(self, cfg):
        self.cfg = cfg

    # ---- senha -------------------------------------------------------
    def _load(self):
        d = read_json("auth.json", {})
        return d if isinstance(d, dict) else {}

    @staticmethod
    def _derive(password, salt_hex, iterations):
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations).hex()

    def configured(self):
        d = self._load()
        return all(k in d for k in ("salt", "hash", "iterations"))

    def set_password(self, password):
        salt = secrets.token_hex(16)
        write_json("auth.json", {
            "salt": salt,
            "iterations": ITERATIONS,
            "hash": self._derive(password, salt, ITERATIONS),
            "failed": 0,
            "locked_until": 0,
        })

    def lock_remaining(self):
        return max(0, int(self._load().get("locked_until", 0) - time.time()))

    def verify(self, password):
        d = self._load()
        wait = self.lock_remaining()
        if wait > 0:
            raise AuthError("Muitas tentativas erradas. Aguarde %ds." % wait)
        good = hmac.compare_digest(self._derive(password, d["salt"], int(d["iterations"])), d["hash"])
        if good:
            d["failed"] = 0
            d["locked_until"] = 0
        else:
            d["failed"] = int(d.get("failed", 0)) + 1
            if d["failed"] >= self.cfg.get("max_attempts"):
                d["failed"] = 0
                d["locked_until"] = time.time() + self.cfg.get("lockout_seconds")
        write_json("auth.json", d)
        return good

    # ---- sessão ------------------------------------------------------
    def session_remaining(self):
        d = read_json("session.json", {})
        exp = d.get("expires", 0) if isinstance(d, dict) else 0
        try:
            return max(0, int(exp - time.time()))
        except TypeError:
            return 0

    def start_session(self):
        write_json("session.json", {"expires": time.time() + self.cfg.get("session_timeout")})

    touch = start_session  # sessão deslizante: cada comando protegido renova a validade

    def end_session(self):
        try:
            (home() / "session.json").unlink()
        except FileNotFoundError:
            pass


# ---- interação com o terminal -------------------------------------------
def ask_password(msg):
    return getpass.getpass(msg)  # não ecoa o que é digitado


def prompt_new_password():
    """Pede e confirma uma nova senha. Retorna None se cancelar ou der erro."""
    try:
        p1 = ask_password("Nova senha: ")
        if len(p1) < MIN_LEN:
            print("A senha precisa ter pelo menos %d caracteres." % MIN_LEN)
            return None
        if ask_password("Confirmar senha: ") != p1:
            print("As senhas não conferem.")
            return None
        return p1
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def require(auth, cfg):
    """Garante uma sessão autenticada; pede a senha se preciso. Retorna True/False."""
    if auth.session_remaining() > 0:
        auth.touch()
        return True
    if not auth.configured():
        print("Primeiro acesso: crie a senha do ArcOS.")
        pw = prompt_new_password()
        if pw is None:
            return False
        auth.set_password(pw)
        auth.start_session()
        print("Senha criada.")
        return True
    for _ in range(cfg.get("max_attempts")):
        try:
            pw = ask_password("Autorização (senha): ")
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        try:
            good = auth.verify(pw)
        except AuthError as e:
            print(e)
            return False
        if good:
            auth.start_session()
            print("Autenticado.")
            return True
        print("Senha incorreta.")
    return False
