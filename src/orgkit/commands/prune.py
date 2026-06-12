"""``ok prune`` — classify and optionally prune local branches across repos.

Ported from the nanvix prune script. For each repo (auto-detected from cwd,
or via ``--repo`` / ``--all-repos``), fetch the bare clone then enumerate
every local branch (other than the default branch) and classify it as one
of: OPEN PR, MERGED, CLOSED PR, STALE, ACTIVE.

Annotations: ``[at:<path>]`` ``[prunable]`` ``[protected]`` ``[dirty]``
``[diverged]`` ``[no-pr]`` ``[cycle]``. Deletion is gated by ``[protected]``
(always blocks) and the ``--exclude-dirty`` / ``--exclude-diverged`` flags.

Default invocation is report-only. Pass ``--delete-merged``, ``--delete-stale``,
and/or ``--delete-closed`` to actually remove the branches.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from shutil import rmtree
from typing import TypedDict

import typer

from orgkit import log, sh, worktrees
from orgkit import repos as repos_mod
from orgkit.config import OrgConfig, load_config

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class State(StrEnum):
    OPEN_PR = "OPEN PR"
    MERGED = "MERGED"
    CLOSED_PR = "CLOSED PR"
    STALE = "STALE"
    ACTIVE = "ACTIVE"


class PRInfo(TypedDict):
    number: int
    state: str  # OPEN / MERGED / CLOSED
    isDraft: bool
    reviewDecision: str
    statusCheckState: str
    baseRefName: str
    url: str


@dataclass
class WorktreeStatus:
    path: Path | None
    branch: str
    state: State
    detail: str = ""
    pr: PRInfo | None = None
    annotations: list[str] = field(default_factory=list)

    @property
    def annotation_str(self) -> str:
        return "".join(f"[{a}]" for a in self.annotations)


# ---------------------------------------------------------------------------
# git helpers (return-code variants; we want to not raise on classification)
# ---------------------------------------------------------------------------


def _git_out(cmd: list[str]) -> tuple[int, str]:
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return res.returncode, res.stdout


def _git_rc(cmd: list[str]) -> int:
    return subprocess.run(cmd, capture_output=True, text=True, check=False).returncode


# ---------------------------------------------------------------------------
# gh integration
# ---------------------------------------------------------------------------


def _gh_available() -> bool:
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _checks_glyph(state: str | None) -> str:
    return {
        "SUCCESS": "\U0001f7e2",
        "FAILURE": "\U0001f534",
        "ERROR": "\U0001f534",
        "PENDING": "\U0001f7e1",
        "EXPECTED": "\U0001f7e1",
    }.get(state or "", "[not checked]")


def _load_prs(
    repo: str, branches: list[str], default_branch: str
) -> tuple[dict[str, PRInfo] | None, str | None]:
    """Look up PR + CI state for ``branches`` and CI state for ``default_branch``."""
    if not _gh_available():
        log.warn("gh not available; PR states will be unknown")
        return None, None

    parts = repo.split("/", 1)
    if len(parts) != 2:
        log.warn(f"unexpected repo spec {repo!r}; skipping PR lookup")
        return None, None
    owner, name = parts

    n = len(branches)
    ref_decls = "".join(f", $ref{i}:String!" for i in range(n))
    ref_selections = "\n".join(
        (
            f"    b{i}: ref(qualifiedName: $ref{i}) {{\n"
            f"      associatedPullRequests(first:10, "
            f"orderBy:{{field:CREATED_AT,direction:DESC}}) {{\n"
            f"        nodes {{ number url state isDraft reviewDecision "
            f"baseRefName statusCheckRollup {{ state }} }}\n"
            f"      }}\n"
            f"    }}"
        )
        for i in range(n)
    )
    query = (
        f"query($owner:String!,$name:String!,$default_ref:String!{ref_decls}) {{\n"
        f"  repository(owner:$owner,name:$name) {{\n"
        f"    defaultRef: ref(qualifiedName: $default_ref) {{\n"
        f"      target {{ ... on Commit {{ oid "
        f"statusCheckRollup {{ state }} }} }}\n"
        f"    }}\n"
        f"{ref_selections}\n"
        f"  }}\n"
        f"}}"
    )

    cmd = [
        "gh",
        "api",
        "graphql",
        "-F",
        f"owner={owner}",
        "-F",
        f"name={name}",
        "-F",
        f"default_ref=refs/heads/{default_branch}",
    ]
    for i, branch in enumerate(branches):
        cmd += ["-F", f"ref{i}=refs/heads/{branch}"]
    cmd += ["-f", f"query={query}"]

    log.info(f"querying GitHub for {repo}: default CI + {n} branch PR(s)")
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        log.warn(f"gh api graphql failed for {repo}: {res.stderr.strip()}")
        return None, None

    try:
        payload = json.loads(res.stdout or "{}")
    except json.JSONDecodeError as exc:
        log.warn(f"could not parse gh output for {repo}: {exc}")
        return None, None

    if payload.get("errors"):
        log.warn(f"gh graphql errors for {repo}: {payload['errors']}")

    repo_data = (payload.get("data") or {}).get("repository") or {}

    default_ci: str | None = None
    default_ref_obj = repo_data.get("defaultRef") or {}
    target = default_ref_obj.get("target") or {}
    rollup = target.get("statusCheckRollup")
    if rollup:
        default_ci = rollup.get("state")

    order = {"OPEN": 0, "MERGED": 1, "CLOSED": 2}
    index: dict[str, PRInfo] = {}
    unresolved: list[str] = []
    for i, branch in enumerate(branches):
        ref_obj = repo_data.get(f"b{i}")
        nodes: list[dict] = []
        if ref_obj:
            nodes = (ref_obj.get("associatedPullRequests") or {}).get("nodes") or []
        if nodes:
            pr = sorted(nodes, key=lambda p: (order.get(p.get("state", ""), 9), -p["number"]))[0]
            pr_rollup = pr.get("statusCheckRollup") or {}
            index[branch] = PRInfo(
                number=pr["number"],
                state=pr["state"],
                isDraft=bool(pr.get("isDraft", False)),
                reviewDecision=pr.get("reviewDecision") or "",
                statusCheckState=pr_rollup.get("state") or "",
                baseRefName=pr.get("baseRefName", ""),
                url=pr.get("url", ""),
            )
        elif ref_obj is None:
            unresolved.append(branch)

    if unresolved:
        index.update(_search_prs_by_head(repo, unresolved))

    return index, default_ci


def _search_prs_by_head(repo: str, branches: list[str]) -> dict[str, PRInfo]:
    """Fallback PR lookup for branches whose server-side ref is gone."""
    if not branches:
        return {}
    n = len(branches)
    q_decls = ", ".join(f"$q{i}:String!" for i in range(n))
    selections = "\n".join(
        (
            f"    s{i}: search(query:$q{i}, type:ISSUE, first:1) {{\n"
            f"      nodes {{ ... on PullRequest {{ number url state isDraft "
            f"reviewDecision baseRefName headRefName "
            f"statusCheckRollup {{ state }} }} }}\n"
            f"    }}"
        )
        for i in range(n)
    )
    query = f"query({q_decls}) {{\n{selections}\n}}"
    cmd = ["gh", "api", "graphql"]
    for i, branch in enumerate(branches):
        cmd += ["-F", f"q{i}=repo:{repo} is:pr head:{branch}"]
    cmd += ["-f", f"query={query}"]

    log.info(f"searching GitHub for {n} branch PR(s) in {repo} with missing refs")
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        log.warn(f"gh api graphql (search) failed: {res.stderr.strip()}")
        return {}
    try:
        payload = json.loads(res.stdout or "{}")
    except json.JSONDecodeError as exc:
        log.warn(f"could not parse gh search output: {exc}")
        return {}
    if payload.get("errors"):
        log.warn(f"gh graphql search errors: {payload['errors']}")

    data = payload.get("data") or {}
    order = {"OPEN": 0, "MERGED": 1, "CLOSED": 2}
    found: dict[str, PRInfo] = {}
    for i, branch in enumerate(branches):
        nodes = (data.get(f"s{i}") or {}).get("nodes") or []
        exact = [pr for pr in nodes if pr.get("headRefName") == branch]
        if not exact:
            continue
        best = sorted(exact, key=lambda p: (order.get(p["state"], 9), -p["number"]))[0]
        rollup = best.get("statusCheckRollup") or {}
        found[branch] = PRInfo(
            number=best["number"],
            state=best["state"],
            isDraft=bool(best.get("isDraft", False)),
            reviewDecision=best.get("reviewDecision") or "",
            statusCheckState=rollup.get("state") or "",
            baseRefName=best.get("baseRefName", ""),
            url=best.get("url", ""),
        )
    return found


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def _worktree_label(worktree_path: Path | None, repo_dir: Path) -> str | None:
    if worktree_path is None:
        return None
    try:
        rel = worktree_path.resolve().relative_to(repo_dir.resolve())
    except ValueError:
        return f"at:{worktree_path}"
    return f"at:{rel}"


def _classify(
    cfg: OrgConfig,
    repo: str,
    branch: str,
    worktree_path: Path | None,
    is_prunable: bool,
    bare: Path,
    repo_dir: Path,
    default_branch: str,
    pr_index: dict[str, PRInfo] | None,
) -> WorktreeStatus:
    have_checkout = worktree_path is not None and (worktree_path / ".git").exists()
    inspect = worktree_path if have_checkout else bare

    annotations: list[str] = []
    if not have_checkout and is_prunable:
        annotations.append("prunable")
    if worktrees.is_protected(cfg, worktree_path, repo):
        annotations.append("protected")
    label = _worktree_label(worktree_path, repo_dir)
    if have_checkout and label is not None:
        annotations.append(label)

    if have_checkout:
        _, status = _git_out(["git", "-C", str(inspect), "status", "--porcelain"])
        if status.strip():
            annotations.append("dirty")
        rc, _ = _git_out(
            [
                "git",
                "-C",
                str(inspect),
                "rev-parse",
                "--abbrev-ref",
                "--symbolic-full-name",
                "@{u}",
            ]
        )
        if rc == 0:
            rc, counts = _git_out(
                [
                    "git",
                    "-C",
                    str(inspect),
                    "rev-list",
                    "--left-right",
                    "--count",
                    f"{branch}...@{{u}}",
                ]
            )
            if rc == 0 and counts.strip():
                ahead_str, _ = counts.split()
                if int(ahead_str) > 0:
                    annotations.append("diverged")

    pr = pr_index.get(branch) if pr_index is not None else None
    default_ref = f"{cfg.remote}/{default_branch}"
    report_path = worktree_path

    if pr and pr.get("state") == "OPEN":
        checks = _checks_glyph(pr.get("statusCheckState"))
        review = pr.get("reviewDecision") or ""
        draft_glyph = "\U0001f4dd " if pr.get("isDraft") else ""
        detail_parts = [f"{draft_glyph}{checks}"]
        if review and review != "NONE":
            detail_parts.append(f"review={review}")
        return WorktreeStatus(
            report_path, branch, State.OPEN_PR, "  ".join(detail_parts), pr, annotations
        )

    if pr and pr.get("state") == "MERGED":
        return WorktreeStatus(report_path, branch, State.MERGED, "squash/merged", pr, annotations)

    if pr and pr.get("state") == "CLOSED":
        return WorktreeStatus(
            report_path, branch, State.CLOSED_PR, "closed without merge", pr, annotations
        )

    is_ancestor = (
        _git_rc(["git", "-C", str(inspect), "merge-base", "--is-ancestor", branch, default_ref])
        == 0
    )
    if is_ancestor:
        _, behind = _git_out(
            ["git", "-C", str(inspect), "rev-list", "--count", f"{branch}..{default_ref}"]
        )
        annotations.append("no-pr")
        return WorktreeStatus(
            report_path,
            branch,
            State.MERGED,
            f"ancestor of default, {behind.strip()} behind",
            pr,
            annotations,
        )

    _, behind = _git_out(
        ["git", "-C", str(inspect), "rev-list", "--count", f"{branch}..{default_ref}"]
    )
    _, ahead = _git_out(
        ["git", "-C", str(inspect), "rev-list", "--count", f"{default_ref}..{branch}"]
    )
    _, age = _git_out(["git", "-C", str(inspect), "log", "-1", "--format=%cr", branch])
    behind_n = int(behind.strip() or "0")
    ahead_n = int(ahead.strip() or "0")
    age_s = age.strip()
    if behind_n > 0:
        return WorktreeStatus(
            report_path,
            branch,
            State.STALE,
            f"{ahead_n} ahead, {behind_n} behind, last commit {age_s}",
            pr,
            annotations,
        )
    return WorktreeStatus(
        report_path, branch, State.ACTIVE, f"{ahead_n} ahead, last commit {age_s}", pr, annotations
    )


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------


def _is_deletable(
    status: WorktreeStatus, *, exclude_dirty: bool, exclude_diverged: bool
) -> tuple[bool, str]:
    if "protected" in status.annotations:
        return False, "protected (operator-managed worktree)"
    if exclude_dirty and "dirty" in status.annotations:
        return False, "dirty (excluded by --exclude-dirty)"
    if exclude_diverged and "diverged" in status.annotations:
        return False, "has unpushed commits (excluded by --exclude-diverged)"
    return True, ""


def _delete_paths(
    cfg: OrgConfig,
    repo: str,
    statuses: list[WorktreeStatus],
    *,
    dry: bool,
) -> None:
    rd = worktrees.repo_dir(cfg, repo)
    for s in statuses:
        if s.path is None or not s.path.exists():
            log.info(f"no checkout for {s.branch} ({s.state.value}); skipping rm")
            continue
        if not worktrees.is_inside_repo(cfg, s.path, repo):
            log.error(f"refusing to rmtree path outside {rd}: {s.path}")
            continue
        if dry:
            log.log(f"rm -rf {s.path}  # {s.branch} ({s.state.value})", "dry")
            continue
        log.info(f"removing {s.branch} ({s.state.value}) at {s.path}")
        rmtree(s.path, onerror=_rmtree_onerror)


def _rmtree_onerror(func, path, exc_info) -> None:
    """Best-effort: chmod +w and retry once; otherwise log and continue."""
    import os
    import stat

    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
        func(path)
    except OSError as e:
        log.warn(f"rmtree failed at {path}: {e}")


def _delete_branches(statuses: list[WorktreeStatus], bare: Path, *, dry: bool) -> None:
    for s in statuses:
        if s.branch.startswith("(detached"):
            continue
        sh.run(
            ["git", "-C", str(bare), "branch", "-D", s.branch],
            dry=dry,
            check=False,
        )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

_STATE_COLOR = {
    State.MERGED: "\x1b[32m",
    State.STALE: "\x1b[33m",
    State.OPEN_PR: "\x1b[36m",
    State.CLOSED_PR: "\x1b[35m",
    State.ACTIVE: "\x1b[37m",
}
_RESET = "\x1b[0m"
_ANNOTATION_COLOR = {
    "dirty": "\x1b[31m",
    "diverged": "\x1b[38;5;208m",
    "no-pr": "\x1b[34m",
    "prunable": "\x1b[38;5;245m",
    "protected": "\x1b[36m",
    "cycle": "\x1b[91m",
}
_LOCATION_TAG_COLOR = "\x1b[35m"
_GREEN = "\x1b[32m"


def _colorize_annotations(annotations: list[str]) -> str:
    parts = []
    for a in annotations:
        if a.startswith("at:"):
            parts.append(f"{_LOCATION_TAG_COLOR}[{a}]{_RESET}")
        else:
            parts.append(f"{_ANNOTATION_COLOR.get(a, '')}[{a}]{_RESET}")
    return "".join(parts)


def _osc8(url: str, text: str) -> str:
    if not url:
        return text
    return f"\x1b]8;;{url}\x1b\\{text}\x1b]8;;\x1b\\"


def _build_graph(
    statuses: list[WorktreeStatus], default_branch: str
) -> tuple[dict[str, list[str]], dict[str, WorktreeStatus]]:
    by_branch = {s.branch: s for s in statuses}
    children: dict[str, list[str]] = {default_branch: []}
    for b in by_branch:
        children[b] = []
    for s in statuses:
        parent = default_branch
        if s.pr:
            base = s.pr.get("baseRefName") or ""
            if base in by_branch and base != s.branch:
                parent = base
        children[parent].append(s.branch)
    return children, by_branch


def _print_report(
    repo: str,
    default_branch: str,
    default_ci: str | None,
    statuses: list[WorktreeStatus],
) -> None:
    _ = default_ci  # consumed by _print_ci_warning later
    typer.echo(f"\n=== {repo} (default: {default_branch}) ===\n")

    if not statuses:
        typer.echo("  (no branches)")
        return

    children, by_branch = _build_graph(statuses, default_branch)
    trunk_kids = children[default_branch]
    stacked = sorted(b for b in trunk_kids if children.get(b))
    loose = sorted(b for b in trunk_kids if not children.get(b))
    ordered_trunk = stacked + loose

    rows: list[tuple[str, WorktreeStatus]] = []
    visited: set[str] = set()

    def walk(name: str, prefix: str, is_last: bool) -> None:
        if name in visited:
            return
        visited.add(name)
        connector = "\u2570\u2500\u25cf" if is_last else "\u251c\u2500\u25cf"
        rows.append((prefix + connector + " ", by_branch[name]))
        kids = sorted(children.get(name, []))
        cont = prefix + ("  " if is_last else "\u2502 ")
        for i, k in enumerate(kids):
            walk(k, cont, i == len(kids) - 1)

    for i, name in enumerate(ordered_trunk):
        walk(name, "", i == len(ordered_trunk) - 1)

    leftovers = sorted(set(by_branch) - visited)
    for i, name in enumerate(leftovers):
        s = by_branch[name]
        if "cycle" not in s.annotations:
            s.annotations.append("cycle")
        connector = "\u2570\u2500\u25cf" if i == len(leftovers) - 1 else "\u251c\u2500\u25cf"
        rows.append((connector + " ", s))

    def name_visible(prefix: str, s: WorktreeStatus) -> str:
        ann = (" " + s.annotation_str) if s.annotations else ""
        return prefix + s.branch + ann

    name_width = max(len(name_visible(p, s)) for p, s in rows)
    state_width = max((len(s.state.value) for _, s in rows), default=len("OPEN PR"))
    pr_width = max(
        (len(f"#{s.pr['number']}") if s.pr else len("--") for _, s in rows),
        default=2,
    )

    typer.echo(f"  {_GREEN}*{_RESET} {default_branch}")

    for prefix, s in rows:
        color = _STATE_COLOR[s.state]
        annot = (" " + _colorize_annotations(s.annotations)) if s.annotations else ""
        visible = name_visible(prefix, s)
        pad = " " * (name_width - len(visible))
        pr_num = f"#{s.pr['number']}" if s.pr else "--"
        pr_url = (s.pr.get("url") or "") if s.pr else ""
        pr_cell = _osc8(pr_url, pr_num)
        pr_pad = " " * (pr_width - len(pr_num))
        detail = s.detail
        if s.state is State.OPEN_PR and s.pr:
            base = s.pr.get("baseRefName") or ""
            if base and base != default_branch and base not in by_branch:
                detail = f"base={base}  {detail}".rstrip()
        typer.echo(
            f"  {_GREEN}{prefix}{_RESET}{color}{s.branch}{_RESET}{annot}{pad}  "
            f"{color}{s.state.value:<{state_width}}{_RESET}  "
            f"{pr_cell}{pr_pad}  {detail}"
        )


def _print_ci_warning(cfg: OrgConfig, default_ci: str | None, default_branch: str) -> None:
    if default_ci not in {"FAILURE", "ERROR"}:
        return
    red = "\x1b[1;31m"
    typer.echo(
        f"\n  {red}\u26a0\ufe0f  CI IS FAILING ON "
        f"{cfg.remote}/{default_branch}  \u26a0\ufe0f{_RESET}"
    )


# ---------------------------------------------------------------------------
# Per-repo orchestration
# ---------------------------------------------------------------------------


def _collect_statuses(
    cfg: OrgConfig, repo: str
) -> tuple[str, str | None, list[WorktreeStatus]] | None:
    rd = worktrees.repo_dir(cfg, repo)
    bare = worktrees.bare_dir(cfg, repo)
    if not bare.is_dir():
        log.warn(f"{bare} missing. Skipping (run `ok sync` first).")
        return None

    default_branch = worktrees.default_branch_of(cfg, repo)
    if default_branch is None:
        log.warn(f"Could not determine default branch for {repo}. Skipping.")
        return None

    log.info(f"fetching {repo}")
    sh.run(["git", "-C", str(bare), "fetch", "--all", "--prune"], check=False)

    branches = worktrees.local_branches(bare, exclude={default_branch})
    pr_index, default_ci = _load_prs(repo, branches, default_branch)

    statuses: list[WorktreeStatus] = []
    wts = worktrees.list_worktrees(bare)
    for branch in branches:
        wt_path, prunable = wts.get(branch, (None, False))
        statuses.append(
            _classify(cfg, repo, branch, wt_path, prunable, bare, rd, default_branch, pr_index)
        )

    return default_branch, default_ci, statuses


def _apply_deletions(
    cfg: OrgConfig,
    repo: str,
    statuses: list[WorktreeStatus],
    *,
    delete_merged: bool,
    delete_stale: bool,
    delete_closed: bool,
    exclude_dirty: bool,
    exclude_diverged: bool,
    dry: bool,
) -> None:
    bare = worktrees.bare_dir(cfg, repo)
    targets: list[WorktreeStatus] = []
    for s in statuses:
        if (
            (s.state is State.MERGED and delete_merged)
            or (s.state is State.STALE and delete_stale)
            or (s.state is State.CLOSED_PR and delete_closed)
        ):
            targets.append(s)

    if not targets:
        return

    typer.echo(f"\n  -- deletions for {repo} --")

    deletable: list[WorktreeStatus] = []
    for status in targets:
        ok, reason = _is_deletable(
            status, exclude_dirty=exclude_dirty, exclude_diverged=exclude_diverged
        )
        if not ok:
            log.warn(f"skipping {status.branch}: {reason}")
            continue
        deletable.append(status)

    if not deletable:
        return

    _delete_paths(cfg, repo, deletable, dry=dry)
    sh.run(["git", "-C", str(bare), "worktree", "prune"], dry=dry, check=False)
    _delete_branches(deletable, bare, dry=dry)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(
    all_repos: bool = typer.Option(
        False, "--all-repos", help="Operate on every configured org repo."
    ),
    repos: list[str] = typer.Option(
        [],
        "--repo",
        help="Operate on the given owner/name repo (repeatable). "
        "Overrides auto-detection; ignored if --all-repos is passed.",
    ),
    delete_merged: bool = typer.Option(
        False, "--delete-merged", help="Delete worktrees classified as MERGED."
    ),
    delete_stale: bool = typer.Option(
        False, "--delete-stale", help="Delete worktrees classified as STALE."
    ),
    delete_closed: bool = typer.Option(
        False, "--delete-closed", help="Delete worktrees whose PR was closed without merging."
    ),
    exclude_dirty: bool = typer.Option(
        False, "--exclude-dirty", help="Skip deletion of worktrees with uncommitted changes."
    ),
    exclude_diverged: bool = typer.Option(
        False, "--exclude-diverged", help="Skip deletion of worktrees with unpushed local commits."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be deleted without touching the filesystem."
    ),
) -> None:
    """Classify worktrees; optionally delete by category.

    With no scope flags, only the metarepo containing the current working
    directory is processed. Use ``--repo owner/name`` (repeatable) or
    ``--all-repos`` to broaden the scope.
    """
    cfg = load_config()

    if all_repos:
        scope = repos_mod.load(cfg)
    elif repos:
        scope = list(repos)
    else:
        current = repos_mod.detect_current(cfg)
        if current is None:
            log.error(
                "could not detect current metarepo from cwd; pass --repo owner/name or --all-repos"
            )
            raise typer.Exit(code=1)
        scope = [current]

    for repo in scope:
        collected = _collect_statuses(cfg, repo)
        if collected is None:
            continue
        default_branch, default_ci, statuses = collected
        _print_report(repo, default_branch, default_ci, statuses)

        if delete_merged or delete_stale or delete_closed:
            _apply_deletions(
                cfg,
                repo,
                statuses,
                delete_merged=delete_merged,
                delete_stale=delete_stale,
                delete_closed=delete_closed,
                exclude_dirty=exclude_dirty,
                exclude_diverged=exclude_diverged,
                dry=dry_run,
            )

        _print_ci_warning(cfg, default_ci, default_branch)
