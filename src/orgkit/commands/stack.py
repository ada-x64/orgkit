"""``ok stack`` — stacked-branch helpers.

All rebases pass ``--update-refs`` so branch tips referenced in the rebased
range are advanced atomically.
"""

from __future__ import annotations

import subprocess

import typer

from orgkit import log, sh
from orgkit.config import OrgConfig, load_config

app = typer.Typer(
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Stacked-branch helpers (uses --update-refs).",
)


def _default_upstream(remote: str, default_branch: str) -> str:
    return f"{remote}/{default_branch}"


def _list_remotes() -> set[str]:
    try:
        out = sh.capture(["git", "remote"])
    except subprocess.CalledProcessError:
        return set()
    return {r.strip() for r in out.splitlines() if r.strip()}


def parse_stack_decoration(decoration_lines: str, remotes: set[str]) -> list[str]:
    """Parse ``git log --pretty=format:%D`` output into a topo-ordered branch list.

    Filters out:
    - empty entries
    - ``HEAD -> X`` markers (we keep ``X``)
    - tag refs (``tag: vX.Y``)
    - any ref whose first path component matches a known remote
      (e.g. ``origin/main``); refs like ``feat/foo`` are preserved.
    """
    branches: list[str] = []
    seen: set[str] = set()
    for line in decoration_lines.splitlines():
        for raw in line.split(", "):
            ref = raw.strip().removeprefix("HEAD -> ").strip()
            if not ref or ref.startswith("tag: "):
                continue
            head, sep, _ = ref.partition("/")
            if sep and head in remotes:
                continue
            if ref in seen:
                continue
            seen.add(ref)
            branches.append(ref)
    return branches


def _stack_branches(cfg: OrgConfig, upstream: str) -> list[str]:
    raw = sh.capture(["git", "log", "--decorate=short", "--pretty=format:%D", f"{upstream}.."])
    return parse_stack_decoration(raw, _list_remotes() | {cfg.remote})


@app.command("push", help="Force-with-lease push every branch in the current stack.")
def push(
    dry: bool = typer.Option(False, "--dry-run", "-n", help="Print commands without running."),
) -> None:
    cfg = load_config()
    upstream = _default_upstream(cfg.remote, cfg.default_branch)
    branches = _stack_branches(cfg, upstream)
    if not branches:
        log.warn(f"no stack branches found above {upstream}")
        raise typer.Exit(code=0)
    log.info(f"pushing {len(branches)} branch(es): {', '.join(branches)}")
    sh.run(
        ["git", "push", "--force-with-lease", cfg.remote, *branches],
        check=True,
        dry=dry,
    )


def _fetch_default(cfg: OrgConfig) -> None:
    sh.run(["git", "fetch", cfg.remote, cfg.default_branch], check=True)


@app.command(
    "rebase",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="git rebase --update-refs against origin/<default> (or args).",
)
def rebase(ctx: typer.Context) -> None:
    cfg = load_config()
    extra = list(ctx.args)
    if not extra:
        _fetch_default(cfg)
        extra = [_default_upstream(cfg.remote, cfg.default_branch)]
    try:
        sh.run(["git", "rebase", "--update-refs", *extra], check=True)
    except subprocess.CalledProcessError as e:
        raise typer.Exit(code=e.returncode) from e


@app.command(
    "rebase-i",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="git rebase -i --update-refs --keep-base against origin/<default> (or args).",
)
def rebase_i(ctx: typer.Context) -> None:
    cfg = load_config()
    extra = list(ctx.args)
    if not extra:
        _fetch_default(cfg)
        extra = [_default_upstream(cfg.remote, cfg.default_branch)]
    try:
        sh.run(
            ["git", "rebase", "-i", "--update-refs", "--keep-base", *extra],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise typer.Exit(code=e.returncode) from e
