"""
Security risk-level policies for AgentOS tools.

All tools not listed here default to CRITICAL (unconditional deny).

For code operations, the risk level may be escalated to CRITICAL by
SecurityManager when the target file matches the sensitive-file policy —
this is NOT handled here; it is handled at the SecurityManager layer to keep
a single enforcement point.
"""

from backend.app.models.tool import RiskLevel

DEFAULT_POLICIES: dict[str, RiskLevel] = {
    # -----------------------------------------------------------------------
    # Filesystem
    # -----------------------------------------------------------------------
    "filesystem.read":   RiskLevel.LOW,
    "filesystem.list":   RiskLevel.LOW,
    "filesystem.create": RiskLevel.MEDIUM,

    # -----------------------------------------------------------------------
    # Terminal
    # -----------------------------------------------------------------------
    "terminal.execute":  RiskLevel.MEDIUM,

    # -----------------------------------------------------------------------
    # Git — read-only structured operations only
    # -----------------------------------------------------------------------
    "git.status":  RiskLevel.LOW,
    "git.branch":  RiskLevel.LOW,
    "git.log":     RiskLevel.LOW,
    "git.diff":    RiskLevel.LOW,
    "git.show":    RiskLevel.LOW,

    # -----------------------------------------------------------------------
    # Process
    # -----------------------------------------------------------------------
    "process.info": RiskLevel.LOW,

    # -----------------------------------------------------------------------
    # Code intelligence — Phase 3A
    # All operations are read-only; actual sensitive-file enforcement is
    # performed dynamically by SecurityManager._check_sensitive_file().
    # -----------------------------------------------------------------------
    "code.scan":    RiskLevel.LOW,
    "code.search":  RiskLevel.LOW,
    "code.read":    RiskLevel.LOW,   # may be escalated to CRITICAL if sensitive
    "code.symbols": RiskLevel.LOW,

    # -----------------------------------------------------------------------
    # Patch — Phase 3B — mutations REQUIRE human approval (HIGH)
    # -----------------------------------------------------------------------
    "patch.apply":    RiskLevel.HIGH,
    "patch.rollback": RiskLevel.HIGH,

    # -----------------------------------------------------------------------
    # Test runner — Phase 3C
    # -----------------------------------------------------------------------
    "test.run": RiskLevel.MEDIUM,
}


def get_policy(tool_name: str, operation: str) -> RiskLevel:
    """Return the base risk level for a tool/operation pair.

    Unknown combinations default to CRITICAL (deny).
    """
    key = f"{tool_name}.{operation}"
    return DEFAULT_POLICIES.get(key, RiskLevel.CRITICAL)
