"""Plugin hooks for extending core verbs.

Plugins may register callables under the ``orgkit.hooks`` entry-point group::

    [project.entry-points."orgkit.hooks"]
    post_sync_repo = "qproj_scripts.hooks:post_sync_repo"

Hook signatures (callable identified by entry-point name):

    post_sync_repo(cfg: OrgConfig, repo: str, repo_dir: Path, *, dry: bool) -> None
        Called after orgkit's generic per-repo sync finishes. Use for
        symlinking shared config files, copying templates, writing
        ``.envrc``, etc.

Hook failures are surfaced (full traceback on stderr) and accumulated.
``run_post_sync_repo`` continues across hooks but records the failure; call
:func:`take_errors` after a batch to flush + count.
"""

from __future__ import annotations

import importlib.metadata
import traceback
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

from orgkit import log
from orgkit.config import OrgConfig

_GROUP = "orgkit.hooks"

_errors: list[tuple[str, str, BaseException]] = []


@cache
def _load_hooks(name: str) -> tuple[Callable[..., Any], ...]:
    out: list[Callable[..., Any]] = []
    for ep in importlib.metadata.entry_points(group=_GROUP):
        if ep.name != name:
            continue
        try:
            fn = ep.load()
        except Exception as e:
            log.warn(f"hook {name} from {ep.value} failed to load: {e}")
            continue
        if not callable(fn):
            log.warn(f"hook {name} from {ep.value} is not callable")
            continue
        out.append(fn)
    return tuple(out)


def _record(hook_name: str, repo: str, exc: BaseException) -> None:
    _errors.append((hook_name, repo, exc))
    log.error(f"{hook_name} hook raised on {repo}: {exc}")
    log.log(traceback.format_exc().rstrip(), "error")


def run_post_sync_repo(cfg: OrgConfig, repo: str, repo_dir: Path, *, dry: bool) -> None:
    """Invoke every registered ``post_sync_repo`` hook for ``repo``."""
    for fn in _load_hooks("post_sync_repo"):
        try:
            fn(cfg, repo, repo_dir, dry=dry)
        except Exception as e:
            _record("post_sync_repo", repo, e)


def take_errors() -> list[tuple[str, str, BaseException]]:
    """Drain and return accumulated hook errors. Empty if all hooks succeeded."""
    out = list(_errors)
    _errors.clear()
    return out


def reset_for_tests() -> None:  # pragma: no cover - test helper
    """Clear the entry-point cache and error list. Use from tests only."""
    _load_hooks.cache_clear()
    _errors.clear()
