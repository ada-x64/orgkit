# orgkit

`orgkit` (CLI: `ok`) is a multi-repo workspace toolkit for GitHub
organizations. It manages a sibling-directory layout of repos in the bare +
worktree convention, discovers per-org configuration by walking up from
`$PWD` (direnv-style), and lets each org ship its own command plugin without
forking the core.

## Status

v0.1 — usable. Core commands all functional. Plugin contract stable.

## Requirements

- Python ≥ 3.12
- `git` ≥ 2.48 (for `worktree.useRelativePaths`)
- `gh` (only for `ok prune`'s PR classification — degrades gracefully if absent)
- `uv` (for `ok self install` / `ok self update`)

## Install

```sh
uv tool install git+https://github.com/ada-x64/orgkit.git
```

## CLI surface

```
ok sync [-x]                  # ensure bare+worktree layout for every configured repo
ok prune [--all-repos|--repo OWNER/NAME] [--delete-merged|--delete-stale|--delete-closed]
                              # classify branches per-repo; optionally delete by category
ok stack push                 # force-with-lease push every branch in the current stack
ok stack rebase [REVS]        # git rebase --update-refs against origin/<default>
ok stack rebase-i [REVS]      # git rebase -i --update-refs --keep-base
ok self install               # materialize the configured plugin
ok self update                # reinstall the configured plugin
ok config show                # print discovered config as JSON
ok config validate            # validate; exit non-zero on errors
ok config path                # print the discovered .ok.toml path
ok --version
```

## Configure

Drop a `.ok.toml` at the root of your org workspace, e.g.
`~/repos/cubething-qproj/.ok.toml`. `ok` walks up from `$PWD` until it finds
one (or errors). `$ORGKIT_CONFIG` overrides discovery.

```toml
# .ok.toml lives ABOVE your repos, never inside one.
default_branch = "main"            # fallback when a repo has no .envrc / remote HEAD
remote = "origin"

# Worktrees with these top-level names are operator-managed and never pruned.
protected_worktrees = ["active"]

[core]
# disable = ["sync"]   # subtractive disable of built-in verbs

[repos]
# One of:
url = "https://raw.githubusercontent.com/myorg/infra/main/downstream-repos.json"
# inline = ["myorg/a", "myorg/b"]

# Always appended (analogous to nanvix's PRIMARY_REPOS).
extra = ["myorg/infra"]

[plugin]
# Tried in order: path → uv-tool → import.
path    = "./infra/scripts"
uv-tool = "git+https://github.com/myorg/infra.git#subdirectory=scripts"
import  = "myorg_scripts"
```

## Layout managed by `ok sync`

```
~/repos/<org>/
├── .ok.toml
└── <owner>/<name>/
    ├── .bare/        # bare clone (fetch refspec set to refs/remotes/<remote>/*)
    ├── .git          # text file: ``gitdir: ./.bare``
    ├── active/       # operator-managed worktree (protected by default)
    └── <branch>/     # arbitrary worktrees, one per branch
```

The default branch is *not* stored in a static worktree; it's tracked via
`<remote>/<default_branch>` in the bare clone, and `active/` may point at
whatever the operator wants (including the default branch).

## Plugins

A plugin is any Python package that depends on `orgkit` and registers
*either* (or both) of two entry-point groups:

```toml
# in your plugin's pyproject.toml

[project.dependencies]
orgkit = "*"

# Commands: a single typer.Typer instance, flat-merged into ``ok``.
[project.entry-points."orgkit.plugin"]
app = "myorg_scripts.cli:app"

# Optional hooks fired by core verbs.
[project.entry-points."orgkit.hooks"]
post_sync_repo = "myorg_scripts.hooks:post_sync_repo"
```

### Hook signatures

```python
from pathlib import Path
from orgkit.config import OrgConfig

def post_sync_repo(cfg: OrgConfig, repo: str, repo_dir: Path, *, dry: bool) -> None:
    """Called after ``ok sync`` finishes per-repo work for ``repo``.

    Use for org-specific finishing: symlinking shared config files, writing
    ``.envrc``, copying editor settings, etc.
    """
    ...
```

Failures in a hook are logged as warnings and do not abort `ok sync`.

### Public API for plugin authors

```python
from orgkit import config, hooks, log, repos, sh, worktrees
from orgkit.config import OrgConfig, load_config
```

Stable in v0.1:
- `config.load_config()` — walk-up discovery + parsing
- `repos.load(cfg)`, `repos.detect_current(cfg)` — repo enumeration
- `worktrees.repo_dir(cfg, repo)`, `bare_dir(cfg, repo)`,
  `default_branch_of(cfg, repo)`, `list_worktrees(bare)`,
  `is_protected(cfg, path, repo)`, `local_branches(bare)`
- `sh.run(cmd, *, dry=False, ...)`, `sh.capture(cmd)`
- `log.info|warn|error|ok(msg)`

### Installing a plugin

```sh
ok self install        # uses [plugin] config; reinstalls orgkit's tool env with the plugin --with'd in
ok self update         # same, force-reinstall
```

The plugin must land in the same Python env as `ok` itself for its entry
points to be visible. `ok self install` does this by running
`uv tool install --reinstall orgkit --with <plugin-spec>`. After install,
plugin commands appear flat under `ok --help`.

## Migrating existing per-org scripts to a plugin

If you currently have a per-org `<org>_scripts` package (e.g. `nanvix-scripts`,
`qproj-scripts`) that duplicates sync/prune/stack logic:

1. **Add `orgkit` as a dependency** in your plugin's `pyproject.toml`.
2. **Delete** your local `sync.py`, `prune.py`, `stack-*` and any shared
   helpers (`_common.py`) — use `orgkit.{sh,log,repos,worktrees}` instead.
3. **Keep** your org-specific verbs (e.g. `build`, `clippy`, `test-windows`,
   `test-downstream`, `refresh-downstreams`).
4. **Convert your `cli.py`** to *only* register the org-specific commands on
   a `typer.Typer` and expose it via `orgkit.plugin`.
5. **Add a `hooks.py`** with `post_sync_repo` if you need symlinks / .envrc
   / editor-config finishing during `ok sync`.
6. **Drop your justfile** — `ok` is the entry point.
7. **Create `.ok.toml`** at the org root with the appropriate
   `[repos]` and `[plugin]` settings.

## License

MIT OR Apache-2.0.
