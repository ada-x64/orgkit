from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orgkit import hooks
from orgkit.config import OrgConfig


@pytest.fixture(autouse=True)
def _reset_hooks():
    hooks.reset_for_tests()
    yield
    hooks.reset_for_tests()


def _cfg(tmp_path: Path) -> OrgConfig:
    return OrgConfig(path=tmp_path / ".ok.toml", root=tmp_path)


def test_run_post_sync_repo_no_hooks_is_noop(tmp_path: Path) -> None:
    hooks.run_post_sync_repo(_cfg(tmp_path), "o/r", tmp_path, dry=True)
    assert hooks.take_errors() == []


def test_run_post_sync_repo_collects_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = MagicMock()
    bad = MagicMock(side_effect=RuntimeError("boom"))

    monkeypatch.setattr(hooks, "_load_hooks", lambda name: (good, bad))

    hooks.run_post_sync_repo(_cfg(tmp_path), "o/r", tmp_path, dry=False)
    good.assert_called_once()
    bad.assert_called_once()
    errs = hooks.take_errors()
    assert len(errs) == 1
    assert errs[0][0] == "post_sync_repo"
    assert errs[0][1] == "o/r"
    assert isinstance(errs[0][2], RuntimeError)


def test_take_errors_drains(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad = MagicMock(side_effect=ValueError("x"))
    monkeypatch.setattr(hooks, "_load_hooks", lambda name: (bad,))
    hooks.run_post_sync_repo(_cfg(tmp_path), "o/r", tmp_path, dry=False)
    assert len(hooks.take_errors()) == 1
    assert hooks.take_errors() == []
