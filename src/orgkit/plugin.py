"""Plugin discovery and resolution.

A plugin exposes one ``typer.Typer`` instance via the ``orgkit.plugin``
entry-point group::

    [project.entry-points."orgkit.plugin"]
    app = "qproj_scripts.cli:app"

Resolution order (per ``[plugin]`` config): ``path`` → ``uv-tool`` → ``import``.
``path`` and ``uv-tool`` install the plugin *into orgkit's own uv tool env* via
``uv tool install --reinstall orgkit --with <spec>`` so its entry points are
visible to the running ``ok`` binary. ``import`` assumes the package is
already on ``sys.path`` (Nix-shell-friendly).
"""

from __future__ import annotations

import importlib
import importlib.metadata
import shutil
import subprocess
from dataclasses import dataclass

import typer

from orgkit import log
from orgkit.config import OrgConfig

_ENTRY_POINT_GROUP = "orgkit.plugin"


@dataclass(frozen=True)
class LoadedPlugin:
    name: str
    app: typer.Typer


def _try_import(module_path: str) -> typer.Typer | None:
    """Import ``module:attr`` and return the attr (must be a Typer)."""
    if ":" in module_path:
        modname, attr = module_path.split(":", 1)
    else:
        modname, attr = module_path, "app"
    try:
        mod = importlib.import_module(modname)
    except ImportError:
        return None
    obj = getattr(mod, attr, None)
    if obj is None:
        log.warn(f"plugin module {modname!r} has no attribute {attr!r}")
        return None
    if not isinstance(obj, typer.Typer):
        log.warn(f"plugin {module_path!r} is not a typer.Typer instance")
        return None
    return obj


def _discover_via_entrypoints() -> typer.Typer | None:
    """Pick the registered ``orgkit.plugin`` entry point.

    Warns if multiple are registered; returns the first valid one.
    """
    eps = list(importlib.metadata.entry_points(group=_ENTRY_POINT_GROUP))
    if len(eps) > 1:
        log.warn(
            f"multiple orgkit.plugin entry points found ({len(eps)}); "
            "using the first. Reinstall to clean up: `ok self update`."
        )
    for ep in eps:
        try:
            obj = ep.load()
        except Exception as e:
            log.warn(f"failed loading entry point {ep.name!r}: {e}")
            continue
        if isinstance(obj, typer.Typer):
            return obj
        log.warn(f"entry point {ep.name!r} is not a typer.Typer")
    return None


def load_plugin(cfg: OrgConfig) -> LoadedPlugin | None:
    """Resolve and load the plugin for ``cfg`` if any is configured.

    Load-order mirrors install-order: a ``path`` or ``uv-tool`` install
    materializes the plugin as a registered entry point, which we prefer.
    Falls back to ``[plugin].import`` for the Nix / already-on-sys.path case.
    """
    if not cfg.plugin.has_any():
        return None

    app = _discover_via_entrypoints()
    if app is not None:
        return LoadedPlugin(name="<entry-point>", app=app)

    if cfg.plugin.import_:
        app = _try_import(cfg.plugin.import_)
        if app is not None:
            return LoadedPlugin(name=cfg.plugin.import_, app=app)

    return None


# ---------------------------------------------------------------------------
# Install / update
# ---------------------------------------------------------------------------


def _have(prog: str) -> bool:
    return shutil.which(prog) is not None


def build_install_argv(spec: str, *, editable: bool) -> list[str]:
    """Build the ``uv tool install`` argv for installing a plugin.

    The plugin is injected as ``--with`` into orgkit's own tool env so its
    entry points are visible to the running ``ok`` binary. ``--reinstall`` is
    required because the env already exists.
    """
    with_spec = f"--editable={spec}" if editable else spec
    return ["uv", "tool", "install", "--reinstall", "orgkit", "--with", with_spec]


def install(cfg: OrgConfig, *, update: bool = False) -> int:
    """Materialize the plugin per config. Returns process exit code.

    ``update`` is accepted for symmetry with ``ok self update``; install is
    always ``--reinstall`` so the flag is currently a no-op signal.
    """
    _ = update
    if not cfg.plugin.has_any():
        log.warn("no [plugin] section configured; nothing to install")
        return 0

    if cfg.plugin.path:
        target = (cfg.root / cfg.plugin.path).resolve()
        if not target.exists():
            log.error(f"[plugin].path does not exist: {target}")
            return 1
        return _run_uv_install(str(target), editable=True)

    if cfg.plugin.uv_tool:
        return _run_uv_install(cfg.plugin.uv_tool, editable=False)

    # `import` only: nothing to install.
    if cfg.plugin.import_:
        log.info(f"[plugin].import = {cfg.plugin.import_!r}; assuming already importable")
        try:
            importlib.import_module(cfg.plugin.import_.split(":", 1)[0])
        except ImportError as e:
            log.error(f"import check failed: {e}")
            return 1
        log.ok("plugin importable")
        return 0

    return 0


def _run_uv_install(spec: str, *, editable: bool) -> int:
    if not _have("uv"):
        log.error("uv not found on PATH; install uv to materialize plugins")
        return 1
    cmd = build_install_argv(spec, editable=editable)
    log.info(" ".join(cmd))
    rc = subprocess.run(cmd).returncode
    if rc == 0:
        log.ok("plugin installed into orgkit tool env")
        log.info("ensure `uv tool dir --bin` is on your PATH so `ok` resolves correctly")
    return rc
