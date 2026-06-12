from __future__ import annotations

from pathlib import Path

import pytest
import typer

from orgkit.config import OrgConfig, PluginConfig
from orgkit.plugin import _try_import, load_plugin


def _cfg(tmp_path: Path, **plugin_kw) -> OrgConfig:
    return OrgConfig(
        path=tmp_path / ".ok.toml",
        root=tmp_path,
        plugin=PluginConfig(**plugin_kw),
    )


def test_try_import_returns_typer_app() -> None:
    app = _try_import("orgkit.cli:app")
    assert isinstance(app, typer.Typer)


def test_try_import_missing_module() -> None:
    assert _try_import("definitely_not_a_real_module:app") is None


def test_try_import_missing_attr(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _try_import("orgkit.cli:nope_not_here") is None


def test_load_plugin_no_config(tmp_path: Path) -> None:
    assert load_plugin(_cfg(tmp_path)) is None


def test_load_plugin_via_import(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, import_="orgkit.cli:app")
    loaded = load_plugin(cfg)
    assert loaded is not None
    assert isinstance(loaded.app, typer.Typer)
