"""Tiny logger with colorized level prefixes, written to stderr.

Respects ``$NO_COLOR`` (any non-empty value disables ANSI codes) per
https://no-color.org/.
"""

from __future__ import annotations

import os
import sys
from typing import Literal

Level = Literal["warn", "error", "info", "dry", "ok"]

_PREFIX_COLOR: dict[Level, str] = {
    "warn": "\x1b[33m[warn] ",
    "error": "\x1b[31m[error] ",
    "info": "\x1b[34m[info] ",
    "dry": "\x1b[38;5;245m[dry] ",
    "ok": "\x1b[32m[ok] ",
}

_PREFIX_PLAIN: dict[Level, str] = {
    "warn": "[warn] ",
    "error": "[error] ",
    "info": "[info] ",
    "dry": "[dry] ",
    "ok": "[ok] ",
}


def _use_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stderr.isatty()


def log(msg: str, level: Level | None = None) -> None:
    if not level:
        print(msg, file=sys.stderr)
        return
    if _use_color():
        print(f"{_PREFIX_COLOR[level]}{msg}\x1b[0m", file=sys.stderr)
    else:
        print(f"{_PREFIX_PLAIN[level]}{msg}", file=sys.stderr)


def warn(msg: str) -> None:
    log(msg, "warn")


def error(msg: str) -> None:
    log(msg, "error")


def info(msg: str) -> None:
    log(msg, "info")


def ok(msg: str) -> None:
    log(msg, "ok")
