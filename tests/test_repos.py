from __future__ import annotations

import json
from pathlib import Path

import pytest

from orgkit import repos
from orgkit.config import OrgConfig, ReposConfig


def _cfg(tmp_path: Path, **repos_kw) -> OrgConfig:
    return OrgConfig(
        path=tmp_path / ".ok.toml",
        root=tmp_path,
        repos=ReposConfig(**repos_kw),
    )


def test_load_inline(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, inline=("o/a", "o/b"))
    assert repos.load(cfg) == ["o/a", "o/b"]


def test_load_inline_with_extra(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, inline=("o/a",), extra=("o/x",))
    assert repos.load(cfg) == ["o/a", "o/x"]


def test_load_dedupes(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, inline=("o/a", "o/a"), extra=("o/a", "o/b"))
    assert repos.load(cfg) == ["o/a", "o/b"]


def test_load_empty(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    assert repos.load(cfg) == []


def test_load_url_uses_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Force the cache directory to a known place under tmp_path.
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    cfg = _cfg(tmp_path, url="https://example.invalid/repos.json")

    # First call: stub urlopen to "succeed" with a synthetic payload.
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            return json.dumps(["o/cached"]).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    assert repos.load(cfg) == ["o/cached"]

    # Second call: simulate network failure; should fall back to cache.
    def _boom(*a, **k):
        raise repos.urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", _boom)
    assert repos.load(cfg) == ["o/cached"]


def test_detect_current(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    repo_dir = tmp_path / "owner" / "name"
    (repo_dir / ".bare").mkdir(parents=True)
    (repo_dir / "active").mkdir()
    assert repos.detect_current(cfg, repo_dir / "active") == "owner/name"
    assert repos.detect_current(cfg, repo_dir) == "owner/name"


def test_detect_current_none(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    other = tmp_path / "unrelated"
    other.mkdir()
    assert repos.detect_current(cfg, other) is None
