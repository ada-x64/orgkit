from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from orgkit.cli import app

runner = CliRunner()


def test_help() -> None:
    res = runner.invoke(app, ["-h"])
    assert res.exit_code == 0
    assert "orgkit" in res.stdout.lower()


def test_config_show(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / ".ok.toml"
    cfg.write_text("default_branch = 'trunk'\n")
    monkeypatch.setenv("ORGKIT_CONFIG", str(cfg))
    res = runner.invoke(app, ["config", "show"])
    assert res.exit_code == 0
    assert "trunk" in res.stdout


def test_config_validate_ok(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / ".ok.toml"
    cfg.write_text("")
    monkeypatch.setenv("ORGKIT_CONFIG", str(cfg))
    res = runner.invoke(app, ["config", "validate"])
    assert res.exit_code == 0


def test_config_validate_bad(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / ".ok.toml"
    cfg.write_text("default_branch = 5\n")
    monkeypatch.setenv("ORGKIT_CONFIG", str(cfg))
    res = runner.invoke(app, ["config", "validate"])
    assert res.exit_code == 1
