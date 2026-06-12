from __future__ import annotations

from orgkit.commands import prune


def _mk(branch, state, **kw):
    return prune.WorktreeStatus(
        path=kw.get("path"),
        branch=branch,
        state=state,
        pr=kw.get("pr"),
        annotations=list(kw.get("annotations", [])),
    )


def test_is_deletable_protected_blocks() -> None:
    s = _mk("feat/x", prune.State.MERGED, annotations=["protected"])
    ok, reason = prune._is_deletable(s, exclude_dirty=False, exclude_diverged=False)
    assert ok is False
    assert "protected" in reason


def test_is_deletable_dirty_blocked_when_flag_set() -> None:
    s = _mk("feat/x", prune.State.MERGED, annotations=["dirty"])
    assert prune._is_deletable(s, exclude_dirty=True, exclude_diverged=False)[0] is False
    assert prune._is_deletable(s, exclude_dirty=False, exclude_diverged=False)[0] is True


def test_is_deletable_diverged_blocked_when_flag_set() -> None:
    s = _mk("feat/x", prune.State.MERGED, annotations=["diverged"])
    assert prune._is_deletable(s, exclude_dirty=False, exclude_diverged=True)[0] is False


def test_build_graph_stacks_by_pr_base() -> None:
    statuses = [
        _mk(
            "feat/top",
            prune.State.OPEN_PR,
            pr={
                "baseRefName": "feat/mid",
                "number": 2,
                "state": "OPEN",
                "isDraft": False,
                "reviewDecision": "",
                "statusCheckState": "",
                "url": "",
            },
        ),
        _mk(
            "feat/mid",
            prune.State.OPEN_PR,
            pr={
                "baseRefName": "main",
                "number": 1,
                "state": "OPEN",
                "isDraft": False,
                "reviewDecision": "",
                "statusCheckState": "",
                "url": "",
            },
        ),
        _mk("loose", prune.State.ACTIVE),
    ]
    children, by_branch = prune._build_graph(statuses, "main")
    assert "feat/mid" in children["main"]
    assert "loose" in children["main"]
    assert children["feat/mid"] == ["feat/top"]
    assert set(by_branch) == {"feat/top", "feat/mid", "loose"}


def test_checks_glyph_unknown() -> None:
    assert prune._checks_glyph(None) == "[not checked]"
    assert prune._checks_glyph("") == "[not checked]"


def test_checks_glyph_known() -> None:
    assert prune._checks_glyph("SUCCESS") == "\U0001f7e2"
    assert prune._checks_glyph("FAILURE") == "\U0001f534"


def test_worktree_label_inside_and_outside(tmp_path) -> None:
    repo_dir = tmp_path / "repo"
    inside = repo_dir / "feat-x"
    inside.mkdir(parents=True)
    assert prune._worktree_label(inside, repo_dir) == "at:feat-x"
    assert prune._worktree_label(None, repo_dir) is None
