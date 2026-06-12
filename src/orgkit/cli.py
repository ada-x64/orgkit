"""Top-level Typer app for ``ok`` and plugin dispatch."""

from __future__ import annotations

import importlib.metadata

import typer

from orgkit.commands import config_cmd, prune, self_cmd, stack, sync
from orgkit.config import ConfigError, load_config
from orgkit.plugin import load_plugin

_STRICT = {"help_option_names": ["-h", "--help"]}

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    context_settings=_STRICT,
    help=(
        "orgkit — multi-repo workspace toolkit. "
        "Run from inside an org tree containing a .ok.toml file."
    ),
)

# --- Core verbs -------------------------------------------------------------

app.command("sync", context_settings=_STRICT, help="Sync the local clone-tree of org repos.")(
    sync.main
)
app.command("prune", context_settings=_STRICT, help="Prune already-merged worktrees.")(prune.main)
app.add_typer(stack.app, name="stack", help="Stacked-branch helpers (uses --update-refs).")
app.add_typer(self_cmd.app, name="self", help="Manage orgkit itself and its plugin.")
app.add_typer(config_cmd.app, name="config", help="Inspect orgkit configuration.")


def _version_callback(value: bool) -> None:
    if not value:
        return
    try:
        ver = importlib.metadata.version("orgkit")
    except importlib.metadata.PackageNotFoundError:
        ver = "unknown"
    typer.echo(f"orgkit {ver}")
    raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print version and exit.",
    ),
) -> None:
    """Merge plugin commands at invocation time (kept out of import path)."""
    _ = version
    _merge_plugin_once()


_PLUGIN_MERGED = False


def _merge_plugin_once() -> None:
    """Best-effort plugin load. Silent if no config; warns on load failure.

    Idempotent: subsequent invocations within the same process are no-ops.
    """
    global _PLUGIN_MERGED
    if _PLUGIN_MERGED:
        return
    _PLUGIN_MERGED = True
    try:
        cfg = load_config()
    except ConfigError:
        return
    plugin = load_plugin(cfg)
    if plugin is None:
        return
    for command in plugin.app.registered_commands:
        app.registered_commands.append(command)
    for group in plugin.app.registered_groups:
        app.registered_groups.append(group)


if __name__ == "__main__":  # pragma: no cover
    app()
