"""Histórico de comandos (uma linha JSON por comando)."""

import json
import os
import time

from .config import home


class Logger:
    def __init__(self, cfg):
        self.cfg = cfg

    @property
    def path(self):
        return home() / "history.log"

    def log(self, cmd, ok=True, detail=""):
        entry = {"t": int(time.time()), "cmd": cmd, "ok": bool(ok), "detail": detail}
        try:
            is_new = not self.path.exists()
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            if is_new:
                os.chmod(self.path, 0o600)
            self._trim()
        except OSError:
            pass  # histórico é best-effort: nunca derruba o comando

    def _trim(self):
        limit = self.cfg.get("history_limit")
        # só confere o conteúdo quando o arquivo já passou de um tamanho plausível
        if self.path.stat().st_size < limit * 200:
            return
        lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) > limit:
            self.path.write_text("\n".join(lines[-limit:]) + "\n", encoding="utf-8")

    def tail(self, n):
        try:
            lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        except FileNotFoundError:
            return []
        out = []
        for line in lines[-n:]:
            try:
                e = json.loads(line)
                out.append(e)
            except json.JSONDecodeError:
                continue
        return out

    def clear(self):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
