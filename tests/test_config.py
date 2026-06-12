from __future__ import annotations

from pathlib import Path

import pytest

from orgkit.config import CONFIG_FILENAME, ConfigError, find_config, parse_config


def _write(p: Path, body: str) -> Path:
    p.write_text(body)
    return p


def test_walk_up_finds_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORGKIT_CONFIG", raising=False)
    org = tmp_path / "org"
    deep = org / "a" / "b" / "c"
    deep.mkdir(parents=True)
    cfg = _write(org / CONFIG_FILENAME, "default_branch = 'main'\n")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert find_config(deep) == cfg.resolve()


def test_walk_up_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORGKIT_CONFIG", raising=False)
    # Skip if a real .ok.toml exists anywhere above tmp_path (host pollution).
    cur = tmp_path
    while True:
        if (cur / CONFIG_FILENAME).is_file():
            pytest.skip(f"host has {cur / CONFIG_FILENAME}; cannot test missing-case")
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    with pytest.raises(ConfigError, match=r"no \.ok\.toml found"):
        find_config(tmp_path)


def test_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _write(tmp_path / "custom.toml", "default_branch = 'main'\n")
    monkeypatch.setenv("ORGKIT_CONFIG", str(cfg))
    assert find_config(tmp_path / "elsewhere") == cfg.resolve()


def test_env_override_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORGKIT_CONFIG", str(tmp_path / "nope.toml"))
    with pytest.raises(ConfigError, match="does not point to a file"):
        find_config(tmp_path)


def test_parse_minimal(tmp_path: Path) -> None:
    p = _write(tmp_path / CONFIG_FILENAME, "")
    cfg = parse_config(p)
    assert cfg.default_branch == "main"
    assert cfg.remote == "origin"
    assert cfg.root == tmp_path
    assert cfg.plugin.has_any() is False


def test_parse_full(tmp_path: Path) -> None:
    body = """
default_branch = "trunk"
remote = "upstream"

[core]
disable = ["sync"]

[repos]
url = "https://example.com/x.json"

[plugin]
path = "./scripts"
uv-tool = "git+https://example.com/p.git"
import = "p.cli:app"
"""
    p = _write(tmp_path / CONFIG_FILENAME, body)
    cfg = parse_config(p)
    assert cfg.default_branch == "trunk"
    assert cfg.remote == "upstream"
    assert cfg.core.disable == ("sync",)
    assert cfg.repos.url == "https://example.com/x.json"
    assert cfg.plugin.path == "./scripts"
    assert cfg.plugin.uv_tool == "git+https://example.com/p.git"
    assert cfg.plugin.import_ == "p.cli:app"


def test_parse_rejects_url_and_inline(tmp_path: Path) -> None:
    body = """
[repos]
url = "https://x"
inline = ["a/b"]
"""
    p = _write(tmp_path / CONFIG_FILENAME, body)
    with pytest.raises(ConfigError, match="either url or inline"):
        parse_config(p)


def test_parse_unknown_key(tmp_path: Path) -> None:
    p = _write(tmp_path / CONFIG_FILENAME, "bogus = 1\n")
    with pytest.raises(ConfigError, match="unknown key"):
        parse_config(p)


def test_parse_wrong_types(tmp_path: Path) -> None:
    p = _write(tmp_path / CONFIG_FILENAME, "default_branch = 1\n")
    with pytest.raises(ConfigError, match="default_branch must be a string"):
        parse_config(p)
