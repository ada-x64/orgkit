"""``ok sync`` — stub.

The real implementation will be ported from the per-org scripts in a
follow-up PR. Tracked in README.
"""

from __future__ import annotations

import typer

from orgkit import log
from orgkit.config import load_config


def main() -> None:
    cfg = load_config()
    log.warn("ok sync: not yet implemented")
    log.info(f"would sync repos under {cfg.root}")
    raise typer.Exit(code=70)  # EX_SOFTWARE
