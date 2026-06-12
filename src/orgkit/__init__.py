"""orgkit — multi-repo workspace toolkit.

Public API for plugin authors:

    from orgkit import config, log, sh
    from orgkit.config import OrgConfig, load_config
"""

from __future__ import annotations

from orgkit import config, log, sh

__all__ = ["config", "log", "sh"]
__version__ = "0.1.0"
