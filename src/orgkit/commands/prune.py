"""``ok prune`` — stub. See sync.py."""

from __future__ import annotations

import typer

from orgkit import log
from orgkit.config import load_config


def main() -> None:
    cfg = load_config()
    log.warn("ok prune: not yet implemented")
    log.info(f"would prune merged worktrees under {cfg.root}")
    raise typer.Exit(code=70)
