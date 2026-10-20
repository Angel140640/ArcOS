"""Saída colorida e utilidades de terminal."""

import os
import sys

from .config import THEMES

_theme = "red"


def set_theme(name):
    global _theme
    _theme = name if name in THEMES else "red"


def color_on():
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _sgr(codes):
    return "\033[%sm" % ";".join(codes)


def paint(text, bold=False, dim=False, fixed=None):
    """Pinta com a cor do tema (ou com uma cor ANSI fixa, ex.: '32')."""
    if not color_on():
        return text
    codes = []
    if bold:
        codes.append("1")
    if dim:
        codes.append("2")
    if fixed:
        codes.append(fixed)
    else:
        c = THEMES.get(_theme)
        if c is not None:
            codes.append("38;5;%d" % c)
    if not codes:
        return text
    return _sgr(codes) + text + "\033[0m"


def rl_paint(text, **kw):
    """Igual a paint, mas seguro para usar dentro do prompt do input()/readline."""
    out = paint(text, **kw)
    if out == text:
        return text
    head, tail = out.split(text, 1)
    return "\001" + head + "\002" + text + "\001" + tail + "\002"


def clean(text):
    """Remove caracteres de controle (evita escapes vindos de arquivos de dados)."""
    return "".join(ch if ch.isprintable() else "?" for ch in str(text))


def ok(msg):
    print(paint("✔ ", fixed="32") + msg)


def err(msg):
    print(paint("✖ ", fixed="31") + msg)


def warn(msg):
    print(paint("⚠ ", fixed="33") + msg)


def dim(msg):
    print(paint(msg, dim=True, fixed="37"))


def banner(version):
    width = 30
    print(paint("╔" + "═" * width + "╗"))
    print(paint("║" + ("  ArcOS Terminal v%s" % version).ljust(width) + "║", bold=True))
    print(paint("╚" + "═" * width + "╝"))
