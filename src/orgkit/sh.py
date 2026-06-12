"""Subprocess wrapper with logging and dry-run support."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

from orgkit import log


def run(
    cmd: Sequence[str],
    *,
    check: bool = True,
    dry: bool = False,
    capture: bool = False,
    env_overrides: dict[str, str] | None = None,
    cwd: str | Path | None = None,
) -> subprocess.CompletedProcess[str] | None:
    """Run ``cmd``, logging it first. Returns ``None`` when ``dry``."""
    shown = " ".join(cmd)
    if cwd is not None:
        shown = f"(cd {cwd} && {shown})"
    log.log(shown, "dry" if dry else "info")
    if dry:
        return None

    env = None
    if env_overrides is not None:
        env = {**os.environ, **env_overrides}

    return subprocess.run(
        list(cmd),
        check=check,
        env=env,
        cwd=cwd,
        text=True,
        capture_output=capture,
    )


def capture(cmd: Sequence[str], *, check: bool = True, cwd: str | Path | None = None) -> str:
    """Run ``cmd`` and return stripped stdout. On failure, surfaces stderr."""
    try:
        result = run(cmd, check=check, capture=True, cwd=cwd)
    except subprocess.CalledProcessError as e:
        if e.stderr:
            log.error(e.stderr.rstrip())
        raise
    assert result is not None  # not dry
    return result.stdout.strip()
