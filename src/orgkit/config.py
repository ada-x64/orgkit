"""Configuration loading for orgkit.

The config file is ``.ok.toml`` and is discovered by walking up from ``$PWD``
(or an explicit start path) until found, or until the filesystem root or
``$HOME`` is reached.

Override the discovered file with the ``ORGKIT_CONFIG`` environment variable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import tomlkit

CONFIG_FILENAME = ".ok.toml"
ENV_OVERRIDE = "ORGKIT_CONFIG"


class ConfigError(Exception):
    """Raised when config is missing, malformed, or invalid."""


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReposConfig:
    url: str | None = None
    inline: tuple[str, ...] = ()


@dataclass(frozen=True)
class PluginConfig:
    path: str | None = None
    uv_tool: str | None = None
    import_: str | None = None

    def has_any(self) -> bool:
        return bool(self.path or self.uv_tool or self.import_)


@dataclass(frozen=True)
class CoreConfig:
    disable: tuple[str, ...] = ()


@dataclass(frozen=True)
class OrgConfig:
    path: Path  # absolute path to the .ok.toml file
    root: Path  # directory containing it
    default_branch: str = "main"
    remote: str = "origin"
    core: CoreConfig = field(default_factory=CoreConfig)
    repos: ReposConfig = field(default_factory=ReposConfig)
    plugin: PluginConfig = field(default_factory=PluginConfig)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def find_config(start: Path | None = None) -> Path:
    """Walk up from ``start`` (or ``$PWD``) looking for ``.ok.toml``.

    Honors ``$ORGKIT_CONFIG`` if set. Stops at the filesystem root. Raises
    ``ConfigError`` if no config is found.
    """
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        p = Path(override).expanduser().resolve()
        if not p.is_file():
            raise ConfigError(f"{ENV_OVERRIDE}={override} does not point to a file")
        return p

    start_resolved = (start or Path.cwd()).resolve()
    cur = start_resolved
    while True:
        candidate = cur / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        parent = cur.parent
        if parent == cur:
            break
        cur = parent

    raise ConfigError(
        f"no {CONFIG_FILENAME} found above {start_resolved} (set ${ENV_OVERRIDE} to override)"
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_KNOWN_TOP = {"default_branch", "remote", "core", "repos", "plugin"}
_KNOWN_CORE = {"disable"}
_KNOWN_REPOS = {"url", "inline"}
_KNOWN_PLUGIN = {"path", "uv-tool", "import"}


def _check_unknown(section: str, got: dict, known: set[str]) -> list[str]:
    return [f"unknown key [{section}].{k}" for k in got if k not in known]


def parse_config(path: Path) -> OrgConfig:
    raw = tomlkit.parse(path.read_text("utf8")).unwrap()
    errors: list[str] = []

    errors.extend(_check_unknown("", raw, _KNOWN_TOP))

    default_branch = raw.get("default_branch", "main")
    if not isinstance(default_branch, str):
        errors.append("default_branch must be a string")

    remote = raw.get("remote", "origin")
    if not isinstance(remote, str):
        errors.append("remote must be a string")

    core_raw = raw.get("core") or {}
    if not isinstance(core_raw, dict):
        errors.append("[core] must be a table")
        core_raw = {}
    errors.extend(_check_unknown("core", core_raw, _KNOWN_CORE))
    disable = tuple(core_raw.get("disable", ()) or ())
    if not all(isinstance(x, str) for x in disable):
        errors.append("[core].disable must be a list of strings")

    repos_raw = raw.get("repos") or {}
    if not isinstance(repos_raw, dict):
        errors.append("[repos] must be a table")
        repos_raw = {}
    errors.extend(_check_unknown("repos", repos_raw, _KNOWN_REPOS))
    url = repos_raw.get("url")
    inline = tuple(repos_raw.get("inline", ()) or ())
    if url is not None and not isinstance(url, str):
        errors.append("[repos].url must be a string")
    if not all(isinstance(x, str) for x in inline):
        errors.append("[repos].inline must be a list of strings")
    if url and inline:
        errors.append("[repos]: set either url or inline, not both")

    plugin_raw = raw.get("plugin") or {}
    if not isinstance(plugin_raw, dict):
        errors.append("[plugin] must be a table")
        plugin_raw = {}
    errors.extend(_check_unknown("plugin", plugin_raw, _KNOWN_PLUGIN))
    p_path = plugin_raw.get("path")
    p_uv = plugin_raw.get("uv-tool")
    p_imp = plugin_raw.get("import")
    for k, v in (("path", p_path), ("uv-tool", p_uv), ("import", p_imp)):
        if v is not None and not isinstance(v, str):
            errors.append(f"[plugin].{k} must be a string")

    if errors:
        raise ConfigError(f"{path}:\n  " + "\n  ".join(errors))

    return OrgConfig(
        path=path,
        root=path.parent,
        default_branch=default_branch,
        remote=remote,
        core=CoreConfig(disable=disable),
        repos=ReposConfig(url=url, inline=inline),
        plugin=PluginConfig(path=p_path, uv_tool=p_uv, import_=p_imp),
    )


def load_config(start: Path | None = None) -> OrgConfig:
    """Find and parse the nearest ``.ok.toml``."""
    return parse_config(find_config(start))
