"""Configuração e armazenamento em disco do ArcOS (~/.arc-os)."""

import json
import os
import re
import tempfile
from pathlib import Path

# nome do tema -> cor ANSI 256 (None = sem cor)
THEMES = {
    "red": 196,
    "green": 46,
    "blue": 39,
    "purple": 135,
    "amber": 214,
    "mono": None,
}

DEFAULTS = {
    "session_timeout": 300,   # segundos que a sessão autenticada dura (0 = sempre pedir senha)
    "max_attempts": 5,        # tentativas erradas antes do bloqueio
    "lockout_seconds": 60,    # duração do bloqueio
    "history_limit": 500,     # quantas linhas de histórico guardar
    "theme": "red",
    "prompt": "arc-os",
    "banner": True,
}

SCHEMA = {
    "session_timeout": int,
    "max_attempts": int,
    "lockout_seconds": int,
    "history_limit": int,
    "theme": str,
    "prompt": str,
    "banner": bool,
}


def home():
    """Pasta de dados do ArcOS. Pode ser trocada com a variável ARCOS_HOME."""
    p = Path(os.environ.get("ARCOS_HOME") or (Path.home() / ".arc-os"))
    p.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(p, 0o700)
    except OSError:
        pass
    return p


def read_json(name, default):
    path = home() / name
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, UnicodeDecodeError):
        try:
            path.replace(path.with_name(path.name + ".corrupt"))
        except OSError:
            pass
        return default


def write_json(name, data):
    """Escrita atômica com permissão 600."""
    path = home() / name
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Config:
    def __init__(self):
        saved = read_json("config.json", {})
        self.data = dict(DEFAULTS)
        if isinstance(saved, dict):
            for k, v in saved.items():
                if k in SCHEMA and isinstance(v, SCHEMA[k]):
                    self.data[k] = v

    def get(self, key):
        return self.data[key]

    def set(self, key, raw):
        if key not in SCHEMA:
            raise ValueError("Chave desconhecida: %s (use: %s)" % (key, ", ".join(SCHEMA)))
        typ = SCHEMA[key]
        if typ is bool:
            low = raw.strip().lower()
            if low in ("1", "true", "on", "yes", "sim", "s"):
                val = True
            elif low in ("0", "false", "off", "no", "nao", "não", "n"):
                val = False
            else:
                raise ValueError("%s aceita on/off" % key)
        elif typ is int:
            try:
                val = int(raw)
            except ValueError:
                raise ValueError("%s precisa ser um número inteiro" % key)
            minimum = 1 if key in ("max_attempts", "history_limit") else 0
            if val < minimum or val > 86400 * 30:
                raise ValueError("%s fora do intervalo permitido (mínimo %d)" % (key, minimum))
        else:
            val = raw
            if key == "theme" and val not in THEMES:
                raise ValueError("Tema inválido. Opções: %s" % ", ".join(THEMES))
            if key == "prompt" and not re.fullmatch(r"[\w.@:/-]{1,20}", val):
                raise ValueError("prompt: 1 a 20 caracteres (letras, números, . _ - @ : /)")
        self.data[key] = val
        self.save()

    def reset(self):
        self.data = dict(DEFAULTS)
        self.save()

    def save(self):
        write_json("config.json", self.data)
