"""Inicialização automática: Termux:Boot + trecho no ~/.bashrc que abre o shell do ArcOS."""

import os
import re
from pathlib import Path

MARK_START = "# >>> arc-os autostart >>>"
MARK_END = "# <<< arc-os autostart <<<"

BOOT_SCRIPT = """#!/data/data/com.termux/files/usr/bin/sh
# Gerado pelo ArcOS (arc-os boot install). Roda quando o Android liga (requer o app Termux:Boot).
termux-wake-lock 2>/dev/null
am start --user 0 -n com.termux/com.termux.app.TermuxActivity >/dev/null 2>&1
"""


def bashrc_path():
    return Path.home() / ".bashrc"


def boot_script_path():
    return Path.home() / ".termux" / "boot" / "arc-os-boot.sh"


def _snippet(kiosk):
    cmd = "exec arc-os shell" if kiosk else "arc-os shell"
    return "\n".join([
        MARK_START,
        'if [ -z "$ARCOS_STARTED" ] && [ -t 0 ] && command -v arc-os >/dev/null 2>&1; then',
        "  export ARCOS_STARTED=1",
        "  " + cmd,
        "fi",
        MARK_END,
        "",
    ])


def _strip_block(text):
    pattern = re.compile(re.escape(MARK_START) + r".*?" + re.escape(MARK_END) + r"\n?", re.S)
    return pattern.sub("", text)


def _read_bashrc():
    try:
        return bashrc_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def install(kiosk=False):
    script = boot_script_path()
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(BOOT_SCRIPT, encoding="utf-8")
    os.chmod(script, 0o755)

    text = _strip_block(_read_bashrc())
    if text and not text.endswith("\n"):
        text += "\n"
    bashrc_path().write_text(text + _snippet(kiosk), encoding="utf-8")


def remove():
    removed = False
    text = _read_bashrc()
    if MARK_START in text:
        bashrc_path().write_text(_strip_block(text), encoding="utf-8")
        removed = True
    try:
        boot_script_path().unlink()
        removed = True
    except FileNotFoundError:
        pass
    return removed


def status():
    text = _read_bashrc()
    return {
        "bashrc": MARK_START in text,
        "kiosk": "exec arc-os shell" in text,
        "boot_script": boot_script_path().exists(),
    }
