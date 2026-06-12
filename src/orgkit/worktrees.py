"""Worktree introspection for the bare+worktree layout used by orgkit.

Layout (per repo)::

    <cfg.root>/<owner>/<name>/
    ├── .bare/        # bare clone, fetch refspec set to refs/remotes/<remote>/*
    ├── .git          # text file: ``gitdir: ./.bare``
    ├── active/       # operator-managed worktree (protected by default)
    └── <branch>/     # arbitrary worktrees, one per branch

The default branch is *not* stored in a static worktree; it's tracked via
``<remote>/<default_branch>`` in the bare clone.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from orgkit import log
from orgkit.config import OrgConfig

_DEFAULT_BRANCH_VALUE_RE = re.compile(r"^[ \t]*(?:export[ \t]+)?DEFAULT_BRANCH=(.*)$")


def repo_dir(cfg: OrgConfig, repo: str) -> Path:
    return cfg.root / repo


def bare_dir(cfg: OrgConfig, repo: str) -> Path:
    return repo_dir(cfg, repo) / ".bare"


# ---------------------------------------------------------------------------
# Default-branch discovery
# ---------------------------------------------------------------------------


def default_branch_from_envrc(dir_: Path) -> str | None:
    """Read ``DEFAULT_BRANCH=...`` from ``<dir>/.envrc`` if present."""
    envrc = dir_ / ".envrc"
    if not envrc.is_file():
        return None
    value: str | None = None
    for line in envrc.read_text("utf8").splitlines():
        m = _DEFAULT_BRANCH_VALUE_RE.match(line)
        if m:
            value = m.group(1).strip()
    if not value:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return value or None


def default_branch_from_bare(bare: Path, remote: str) -> str | None:
    """Resolve ``refs/remotes/<remote>/HEAD`` -> ``<branch>``."""
    res = subprocess.run(
        [
            "git",
            "-C",
            str(bare),
            "symbolic-ref",
            "--short",
            f"refs/remotes/{remote}/HEAD",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        return None
    name = res.stdout.strip()
    prefix = f"{remote}/"
    return name.removeprefix(prefix) if name.startswith(prefix) else None


def default_branch_of(cfg: OrgConfig, repo: str) -> str | None:
    """Return the default branch for ``repo``.

    Tries (in order): ``<repo>/.envrc``, ``<remote>/HEAD`` in the bare repo,
    and finally falls back to ``cfg.default_branch``.
    """
    rd = repo_dir(cfg, repo)
    return (
        default_branch_from_envrc(rd)
        or default_branch_from_bare(bare_dir(cfg, repo), cfg.remote)
        or cfg.default_branch
    )


# ---------------------------------------------------------------------------
# Worktree listing
# ---------------------------------------------------------------------------


def list_worktrees(bare: Path) -> dict[str, tuple[Path, bool]]:
    """``{branch: (path, prunable)}`` from ``git worktree list --porcelain``.

    Skips bare and detached entries.
    """
    res = subprocess.run(
        ["git", "-C", str(bare), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        return {}
    result: dict[str, tuple[Path, bool]] = {}
    cur: dict[str, object] = {}

    def flush() -> None:
        b = cur.get("branch")
        p = cur.get("worktree")
        if isinstance(b, str) and isinstance(p, str):
            branch = b.removeprefix("refs/heads/")
            result[branch] = (Path(p), bool(cur.get("prunable", False)))

    for line in res.stdout.splitlines():
        if not line.strip():
            flush()
            cur = {}
            continue
        key, _, val = line.partition(" ")
        if key in ("worktree", "branch"):
            cur[key] = val
        elif key in ("prunable", "bare", "detached"):
            cur[key] = True
    flush()
    return result


def is_protected(cfg: OrgConfig, worktree_path: Path | None, repo: str) -> bool:
    """True if ``worktree_path`` is one of the protected slots under ``repo``."""
    if worktree_path is None:
        return False
    rd = repo_dir(cfg, repo)
    try:
        rel = worktree_path.resolve().relative_to(rd.resolve())
    except ValueError:
        return False
    return len(rel.parts) == 1 and rel.parts[0] in cfg.protected_worktrees


def is_inside_repo(cfg: OrgConfig, worktree_path: Path | None, repo: str) -> bool:
    """True if ``worktree_path`` is under ``<cfg.root>/<repo>``."""
    if worktree_path is None:
        return True
    rd = repo_dir(cfg, repo)
    try:
        worktree_path.resolve().relative_to(rd.resolve())
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# Branch helpers
# ---------------------------------------------------------------------------


def local_branches(bare: Path, exclude: set[str] | None = None) -> list[str]:
    """All local branches in the bare repo, sorted, minus ``exclude``."""
    res = subprocess.run(
        [
            "git",
            "-C",
            str(bare),
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/heads/",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        log.warn(f"for-each-ref failed in {bare}")
        return []
    skip = exclude or set()
    out: list[str] = []
    for line in res.stdout.splitlines():
        name = line.strip()
        if name and name not in skip:
            out.append(name)
    return sorted(out)
