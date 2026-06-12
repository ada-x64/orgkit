"""``ok config`` — inspect / validate config."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import typer

from orgkit import log
from orgkit.config import ConfigError, find_config, load_config

app = typer.Typer(
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Inspect orgkit configuration.",
)


def _to_jsonable(cfg) -> dict:
    d = asdict(cfg)
    d["path"] = str(cfg.path)
    d["root"] = str(cfg.root)
    return d


@app.command("show", help="Print the discovered config as JSON.")
def show() -> None:
    cfg = load_config()
    print(json.dumps(_to_jsonable(cfg), indent=2, default=str))


@app.command("validate", help="Validate the discovered config; exit non-zero on errors.")
def validate() -> None:
    try:
        cfg = load_config()
    except ConfigError as e:
        log.error(str(e))
        raise typer.Exit(code=1) from e
    log.ok(f"valid: {cfg.path}")


@app.command("path", help="Print the path to the discovered .ok.toml.")
def path() -> None:
    try:
        p: Path = find_config()
    except ConfigError as e:
        log.error(str(e))
        raise typer.Exit(code=1) from e
    print(p)
