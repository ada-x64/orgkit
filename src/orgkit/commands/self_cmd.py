"""``ok self`` — manage orgkit's plugin install."""

from __future__ import annotations

import typer

from orgkit import plugin
from orgkit.config import load_config

app = typer.Typer(
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Manage orgkit's plugin install.",
)


@app.command("install", help="Install the configured plugin (path → uv-tool → import).")
def install() -> None:
    cfg = load_config()
    rc = plugin.install(cfg, update=False)
    raise typer.Exit(code=rc)


@app.command("update", help="Reinstall the configured plugin.")
def update() -> None:
    cfg = load_config()
    rc = plugin.install(cfg, update=True)
    raise typer.Exit(code=rc)
