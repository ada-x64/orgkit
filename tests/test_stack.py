from __future__ import annotations

from pathlib import Path

import pytest

from orgkit.commands.stack import parse_stack_decoration
from orgkit.plugin import build_install_argv

# ---------------------------------------------------------------------------
# parse_stack_decoration
# ---------------------------------------------------------------------------


def test_parse_basic() -> None:
    raw = "HEAD -> feat/top\nfeat/middle\nfeat/bottom"
    assert parse_stack_decoration(raw, {"origin"}) == [
        "feat/top",
        "feat/middle",
        "feat/bottom",
    ]


def test_parse_preserves_slashed_branches() -> None:
    """Regression: don't drop `feat/x`-style names just because they contain `/`."""
    raw = "HEAD -> feat/x, origin/feat/x\nrelease/v1, origin/release/v1"
    out = parse_stack_decoration(raw, {"origin"})
    assert "feat/x" in out
    assert "release/v1" in out
    assert "origin/feat/x" not in out
    assert "origin/release/v1" not in out


def test_parse_strips_tag_refs() -> None:
    raw = "HEAD -> feat/x, tag: v1.0\nfeat/y"
    assert parse_stack_decoration(raw, {"origin"}) == ["feat/x", "feat/y"]


def test_parse_dedupes() -> None:
    raw = "HEAD -> feat/x\nfeat/x"
    assert parse_stack_decoration(raw, {"origin"}) == ["feat/x"]


def test_parse_multi_remote() -> None:
    raw = "HEAD -> feat/x, origin/feat/x, upstream/feat/x"
    assert parse_stack_decoration(raw, {"origin", "upstream"}) == ["feat/x"]


def test_parse_empty() -> None:
    assert parse_stack_decoration("", {"origin"}) == []
    assert parse_stack_decoration("\n\n", {"origin"}) == []


# ---------------------------------------------------------------------------
# build_install_argv (B1 regression)
# ---------------------------------------------------------------------------


def test_install_argv_installs_orgkit_with_plugin() -> None:
    """The plugin must be `--with`'d into orgkit's tool env, not the reverse."""
    argv = build_install_argv("git+https://example.com/p.git", editable=False)
    assert argv[:6] == ["uv", "tool", "install", "--reinstall", "orgkit", "--with"]
    assert argv[6] == "git+https://example.com/p.git"


def test_install_argv_editable_path() -> None:
    argv = build_install_argv("/abs/path/to/plugin", editable=True)
    assert argv == [
        "uv",
        "tool",
        "install",
        "--reinstall",
        "orgkit",
        "--with",
        "--editable=/abs/path/to/plugin",
    ]


# ---------------------------------------------------------------------------
# `_run_uv_install` argv via monkeypatched subprocess (round-trip)
# ---------------------------------------------------------------------------


def test_run_uv_install_calls_correct_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from orgkit import plugin as plugin_mod

    captured: dict[str, list[str]] = {}

    class _CP:
        returncode = 0

    def fake_run(argv, *a, **kw):  # type: ignore[no-untyped-def]
        captured["argv"] = argv
        return _CP()

    monkeypatch.setattr(plugin_mod.shutil, "which", lambda _: "/usr/bin/uv")
    monkeypatch.setattr(plugin_mod.subprocess, "run", fake_run)

    rc = plugin_mod._run_uv_install("pkg-spec", editable=False)
    assert rc == 0
    assert captured["argv"][:5] == ["uv", "tool", "install", "--reinstall", "orgkit"]
    assert "pkg-spec" in captured["argv"]
