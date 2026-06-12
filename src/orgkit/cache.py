"""XDG cache and data paths for orgkit."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


def _xdg(env: str, fallback: str) -> Path:
    val = os.environ.get(env)
    if val:
        return Path(val).expanduser()
    return Path.home() / fallback


def cache_dir() -> Path:
    return _xdg("XDG_CACHE_HOME", ".cache") / "orgkit"


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share") / "orgkit"


def config_hash(config_path: Path) -> str:
    """Stable short hash of a config file's absolute path; used as cache key."""
    return hashlib.sha256(str(config_path.resolve()).encode()).hexdigest()[:16]


def entrypoint_cache_path(config_path: Path) -> Path:
    return cache_dir() / config_hash(config_path) / "entrypoints.json"
