"""
SecurityManager: central permission-checking entry point for AgentOS.

All tools must call `SecurityManager.is_allowed()` before execution.
`requires_approval()` determines whether a human must explicitly approve the
operation before it proceeds.

Sensitive-file protection is enforced here so that no individual tool needs to
duplicate the logic.  Any tool that exposes file content (code.read,
code.search, filesystem.read …) should pass the target path to is_allowed()
via the `file_path` keyword so that the sensitive-file gate can block it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from backend.app.config.settings import settings
from backend.app.models.tool import RiskLevel
from backend.app.security.policies import get_policy
from backend.app.security.sensitive_files import is_sensitive_path, sensitive_file_reason


class SecurityManager:
    # -----------------------------------------------------------------------
    # Approval / allow checks
    # -----------------------------------------------------------------------

    @staticmethod
    def requires_approval(tool_name: str, operation: str) -> bool:
        """Return True when the operation must be explicitly approved by a human."""
        if not settings.REQUIRE_APPROVAL_FOR_DANGEROUS_ACTIONS:
            return False
        risk = get_policy(tool_name, operation)
        return risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    @staticmethod
    def is_allowed(
        tool_name: str,
        operation: str,
        *,
        file_path: Optional[str | Path] = None,
    ) -> bool:
        """Return True when the operation is permitted to proceed.

        Rules (in order):
        1. Unknown tool/operation combinations are CRITICAL → denied.
        2. If a file_path is supplied, it is checked against the
           sensitive-file policy.  A match → denied regardless of base risk.
        3. CRITICAL base risk → denied.
        4. Everything else is permitted (though HIGH risk still requires
           approval before the executor will run it).
        """
        base_risk = get_policy(tool_name, operation)

        # Rule 1 – explicitly CRITICAL in policy table
        if base_risk == RiskLevel.CRITICAL:
            return False

        # Rule 2 – sensitive file gate
        if file_path is not None and is_sensitive_path(file_path):
            return False

        return True

    @staticmethod
    def sensitive_file_denial_reason(file_path: str | Path) -> str:
        """Return a human-readable reason string for a denied sensitive file."""
        return sensitive_file_reason(file_path)
