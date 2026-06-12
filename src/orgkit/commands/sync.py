"""``ok sync`` — generic per-repo bare+worktree sync.

For each repo in the org config:

1. Ensure ``<root>/<repo>/`` exists.
2. Ensure ``<root>/<repo>/.bare/`` is a bare clone of
   ``https://github.com/<repo>``.
3. Set ``remote.<remote>.fetch = +refs/heads/*:refs/remotes/<remote>/*`` and
   run ``fetch --all --prune``.
4. Write the ``.git`` pointer file (``gitdir: ./.bare``) so the directory
   acts as a normal working tree parent.
5. Enable ``worktree.useRelativePaths`` and run ``worktree repair`` +
   ``worktree prune``.
6. Invoke every registered ``post_sync_repo`` plugin hook for org-specific
   finishing (symlinks, ``.envrc``, editor configs, etc.).

Dry-run by default; pass ``-x`` / ``--execute`` to mutate.
"""

from __future__ import annotations

import typer

from orgkit import hooks, log, repos, sh, worktrees
from orgkit.config import OrgConfig, load_config


def _write_file(path, content: str, *, dry: bool) -> None:
    log.log(f"write {path}", "dry" if dry else "info")
    if dry:
        return
    path.write_text(content)


def _sync_repo(cfg: OrgConfig, repo: str, *, dry: bool) -> None:
    rd = worktrees.repo_dir(cfg, repo)
    bare = worktrees.bare_dir(cfg, repo)
    typer.echo(f"\n=== {repo} ===")

    if not rd.is_dir():
        log.log(f"creating {rd}", "dry" if dry else "info")
        if not dry:
            rd.mkdir(parents=True, exist_ok=True)
    else:
        log.info(f"{rd} exists")

    if not bare.is_dir():
        log.info(".bare missing")
        sh.run(
            ["git", "clone", "--bare", f"https://github.com/{repo}", str(bare)],
            dry=dry,
        )
    else:
        log.info(".bare exists")

    log.info("syncing .bare")
    sh.run(
        [
            "git",
            "-C",
            str(bare),
            "config",
            f"remote.{cfg.remote}.fetch",
            f"+refs/heads/*:refs/remotes/{cfg.remote}/*",
        ],
        dry=dry,
    )
    sh.run(["git", "-C", str(bare), "fetch", "--all", "--prune"], dry=dry, check=False)

    _write_file(rd / ".git", "gitdir: ./.bare\n", dry=dry)
    sh.run(
        ["git", "-C", str(bare), "config", "worktree.useRelativePaths", "true"],
        dry=dry,
    )
    sh.run(["git", "-C", str(bare), "worktree", "repair"], dry=dry, check=False)
    # Drop refs for worktrees whose checkout was manually deleted, so
    # ``ok prune`` later sees them tagged ``[prunable]`` rather than
    # silently lingering in ``git worktree list`` forever.
    sh.run(["git", "-C", str(bare), "worktree", "prune"], dry=dry, check=False)

    # Plugin-supplied finishing (symlinks, .envrc, editor configs, ...).
    hooks.run_post_sync_repo(cfg, repo, rd, dry=dry)


def main(
    execute: bool = typer.Option(
        False, "-x", "--execute", help="Actually run mutating commands (default is dry-run)."
    ),
) -> None:
    cfg = load_config()
    dry = not execute
    repo_list = repos.load(cfg)
    if not repo_list:
        log.warn("no repos configured ([repos].inline / .url / .extra all empty)")
        raise typer.Exit(code=0)
    for repo in repo_list:
        _sync_repo(cfg, repo, dry=dry)
    errs = hooks.take_errors()
    if errs:
        log.error(f"{len(errs)} post_sync_repo hook failure(s); see above")
        raise typer.Exit(code=1)
