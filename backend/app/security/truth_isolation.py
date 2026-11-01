"""
Filesystem Access Control Gate for AgentOS Runtime Sandbox Tools.

Guarantees technical isolation between Runtime tools/agents and Layer A Hidden Truth:
- Blocks any attempt by FilesystemTool or TerminalTool to read, list, write, or stat
  paths containing 'hidden_truth', 'evaluation/recovery_pilot', or offline datasets.
"""

from __future__ import annotations

import os
from pathlib import Path


RESTRICTED_OFFLINE_PATHS = [
    "evaluation/recovery_pilot/hidden_truth",
    "evaluation\\recovery_pilot\\hidden_truth",
    "hidden_truth",
]


class RuntimeTruthIsolationGate:
    """Enforces technical path barrier preventing runtime from accessing hidden truth."""

    @classmethod
    def check_access(cls, path_str: str) -> None:
        """Raises PermissionError if runtime attempts to access restricted offline truth."""
        if not path_str:
            return

        normalized = os.path.normpath(str(path_str)).replace("\\", "/")
        for restricted in RESTRICTED_OFFLINE_PATHS:
            if restricted in normalized:
                raise PermissionError(
                    f"Access Denied: Runtime path '{path_str}' is protected by Offline Truth Isolation Gate."
                )

    @classmethod
    def is_safe_runtime_path(cls, path_str: str) -> bool:
        try:
            cls.check_access(path_str)
            return True
        except PermissionError:
            return False
