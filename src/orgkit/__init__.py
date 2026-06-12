"""orgkit — multi-repo workspace toolkit.

Public API for plugin authors:

    from orgkit import config, hooks, log, repos, sh, worktrees
    from orgkit.config import OrgConfig, load_config
"""

from __future__ import annotations

from orgkit import config, hooks, log, repos, sh, worktrees

__all__ = ["config", "hooks", "log", "repos", "sh", "worktrees"]
__version__ = "0.1.0"
