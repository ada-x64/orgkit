from __future__ import annotations

from pathlib import Path

from orgkit import worktrees
from orgkit.config import OrgConfig


def _cfg(tmp_path: Path) -> OrgConfig:
    return OrgConfig(path=tmp_path / ".ok.toml", root=tmp_path)


def test_default_branch_from_envrc(tmp_path: Path) -> None:
    (tmp_path / ".envrc").write_text("# preamble\nexport DEFAULT_BRANCH='trunk'\n")
    assert worktrees.default_branch_from_envrc(tmp_path) == "trunk"


def test_default_branch_from_envrc_no_quotes_no_export(tmp_path: Path) -> None:
    (tmp_path / ".envrc").write_text("DEFAULT_BRANCH=develop\n")
    assert worktrees.default_branch_from_envrc(tmp_path) == "develop"


def test_default_branch_from_envrc_missing(tmp_path: Path) -> None:
    assert worktrees.default_branch_from_envrc(tmp_path) is None


def test_default_branch_of_falls_back_to_cfg(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    (tmp_path / "o" / "r" / ".bare").mkdir(parents=True)
    # No envrc, bare has no remote/HEAD -> falls back to cfg.default_branch.
    assert worktrees.default_branch_of(cfg, "o/r") == "main"


def test_is_protected_default_active(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    rd = tmp_path / "o" / "r"
    (rd / "active").mkdir(parents=True)
    (rd / "feat-x").mkdir()
    assert worktrees.is_protected(cfg, rd / "active", "o/r") is True
    assert worktrees.is_protected(cfg, rd / "feat-x", "o/r") is False


def test_is_protected_configurable(tmp_path: Path) -> None:
    cfg = OrgConfig(
        path=tmp_path / ".ok.toml", root=tmp_path, protected_worktrees=("trunk", "active")
    )
    rd = tmp_path / "o" / "r"
    (rd / "trunk").mkdir(parents=True)
    assert worktrees.is_protected(cfg, rd / "trunk", "o/r") is True


def test_is_inside_repo(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    rd = tmp_path / "o" / "r"
    rd.mkdir(parents=True)
    assert worktrees.is_inside_repo(cfg, rd / "wt", "o/r") is True
    assert worktrees.is_inside_repo(cfg, Path("/tmp/elsewhere"), "o/r") is False
    assert worktrees.is_inside_repo(cfg, None, "o/r") is True
