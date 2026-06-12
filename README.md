# orgkit

`orgkit` (CLI: `ok`) is a multi-repo workspace toolkit for GitHub organizations.
It manages a sibling-directory layout of repos (typically bare + worktrees),
discovers per-org configuration by walking up from `$PWD`, and lets each org
ship its own command plugin without forking the core.

## Status

Early. Core: config discovery, plugin loader, `ok self {install,update}`,
`ok config {show,validate}`, `ok stack {push,rebase,rebase-i}`. `sync` and
`prune` are stubs awaiting port from the existing per-org implementations.

## Install

```sh
uv tool install git+https://github.com/ada-x64/orgkit.git
```

## CLI surface (v0.1)

```
ok sync           # stub — port pending
ok prune          # stub — port pending
ok stack push     # force-with-lease push every branch in the current stack
ok stack rebase   # git rebase --update-refs against origin/<default>
ok stack rebase-i # git rebase -i --update-refs --keep-base
ok self install   # materialize the configured plugin
ok self update    # reinstall the configured plugin
ok config show    # print discovered config as JSON
ok config validate
ok config path    # print discovered .ok.toml path
ok --version
```

## Configure

Drop a `.ok.toml` at the root of your org workspace, e.g.
`~/repos/cubething-qproj/.ok.toml`. `ok` walks up from `$PWD` until it finds
one (or errors).

```toml
default_branch = "main"
remote = "origin"

[repos]
url = "https://raw.githubusercontent.com/cubething-qproj/infra/main/downstream-repos.json"
# inline = ["cubething-qproj/quell", "cubething-qproj/q_term"]

[plugin]
# Tried in order: path → uv-tool → import.
path    = "./infra/scripts"
uv-tool = "git+https://github.com/cubething-qproj/infra.git#subdirectory=scripts"
import  = "qproj_scripts"
```

## Plugins

A plugin is any Python package that exposes a single `typer.Typer` instance
via the `orgkit.plugin` entry-point group:

```toml
# in your plugin's pyproject.toml
[project.entry-points."orgkit.plugin"]
app = "qproj_scripts.cli:app"
```

`ok self install` materializes the plugin per `[plugin]` config; `ok self
update` refreshes it. Plugin commands appear flat under `ok`.

## License

MIT OR Apache-2.0.
