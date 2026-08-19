"""
AgentOS Phase 5 — Per-Agent Permission & Authorization System.

Enforces strict least-privilege access:
- Default: DENY
- Agent can ONLY use tools declared in its AgentPermission
- Delegation is permitted ONLY for SupervisorAgent
- Sensitive file access is strictly blocked by SecurityManager
- Code modification and test execution require explicit authorization
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from backend.app.models.multi_agent import AgentPermission, AgentType
from backend.app.security.permissions import SecurityManager

logger = logging.getLogger("agentos.agent_permissions")


class AgentPermissionManager:
    """Manages and enforces per-agent authorization policies."""

    _permissions: Dict[AgentType, AgentPermission] = {}

    @classmethod
    def register_permission(cls, perm: AgentPermission) -> None:
        """Register or update an agent's explicit permissions."""
        cls._permissions[perm.agent_type] = perm

    @classmethod
    def get_permission(cls, agent_type: AgentType) -> Optional[AgentPermission]:
        """Retrieve the permission configuration for an agent."""
        return cls._permissions.get(agent_type)

    @classmethod
    def can_use_tool(cls, agent_type: AgentType, tool_name: str, operation: str = "") -> bool:
        """
        Determine if an agent is authorized to invoke a tool operation.
        Must satisfy:
        1. Agent exists in permission matrix.
        2. Tool (or tool.operation) is explicitly allowlisted for that agent.
        3. SecurityManager allows the base tool operation.
        """
        perm = cls.get_permission(agent_type)
        if not perm:
            return False

        if "." in tool_name and not operation:
            parts = tool_name.split(".", 1)
            t_name, op = parts[0], parts[1]
            op_name = tool_name
        else:
            t_name, op = tool_name, operation
            op_name = f"{t_name}.{op}" if op else t_name

        is_tool_allowed = (
            t_name in perm.allowed_tools
            or op_name in perm.allowed_tools
            or f"{t_name}.*" in perm.allowed_tools
        )
        if not is_tool_allowed:
            logger.warning("Agent %s denied tool %s (not in agent allowlist)", agent_type.value, op_name)
            return False

        # Must also pass SecurityManager base check
        return SecurityManager.is_allowed(t_name, op)

    @classmethod
    def can_delegate(cls, agent_type: AgentType) -> bool:
        """Only SUPERVISOR is permitted to decompose and delegate tasks."""
        perm = cls.get_permission(agent_type)
        return bool(perm and perm.can_delegate and agent_type == AgentType.SUPERVISOR)

    @classmethod
    def can_modify_code(cls, agent_type: AgentType) -> bool:
        """Check whether agent has permission to propose or apply patches."""
        perm = cls.get_permission(agent_type)
        return bool(perm and perm.can_modify_code)

    @classmethod
    def can_execute_tests(cls, agent_type: AgentType) -> bool:
        """Check whether agent has permission to invoke test runners."""
        perm = cls.get_permission(agent_type)
        return bool(perm and perm.can_execute_tests)

    @classmethod
    def can_access_memory(cls, agent_type: AgentType, category: str) -> bool:
        """Check whether agent is authorized for a specific memory category."""
        perm = cls.get_permission(agent_type)
        if not perm:
            return False
        return category in perm.allowed_memory_categories

    @classmethod
    def reset(cls) -> None:
        """Reset permissions to standard Phase 5 defaults."""
        cls._permissions.clear()
        cls._setup_defaults()

    @classmethod
    def _setup_defaults(cls) -> None:
        """Initialize default least-privilege matrix for Phase 5."""
        # 1. SUPERVISOR
        cls.register_permission(AgentPermission(
            agent_type=AgentType.SUPERVISOR,
            allowed_tools=[],  # No direct tool invocation
            can_delegate=True,
            can_modify_code=False,
            can_execute_tests=False,
            allowed_memory_categories=["short_term", "conversation", "project", "semantic"],
        ))

        # 2. RESEARCH
        cls.register_permission(AgentPermission(
            agent_type=AgentType.RESEARCH,
            allowed_tools=[
                "code.search", "code.read", "code.symbols", "code.scan",
                "git.status", "git.diff", "git.log", "git.show",
                "filesystem.list", "filesystem.read",
            ],
            can_delegate=False,
            can_modify_code=False,
            can_execute_tests=False,
            allowed_memory_categories=["short_term", "project", "semantic"],
        ))

        # 3. CODING
        cls.register_permission(AgentPermission(
            agent_type=AgentType.CODING,
            allowed_tools=[
                "code.search", "code.read", "code.symbols",
                "patch.apply", "patch.rollback",
            ],
            can_delegate=False,
            can_modify_code=True,
            can_execute_tests=False,
            allowed_memory_categories=["short_term", "project"],
        ))

        # 4. DEBUGGER
        cls.register_permission(AgentPermission(
            agent_type=AgentType.DEBUGGER,
            allowed_tools=[
                "test.run", "code.search", "code.read", "code.symbols",
            ],
            can_delegate=False,
            can_modify_code=False,
            can_execute_tests=True,
            allowed_memory_categories=["short_term", "project"],
        ))

        # 5. REVIEWER
        cls.register_permission(AgentPermission(
            agent_type=AgentType.REVIEWER,
            allowed_tools=[],
            can_delegate=False,
            can_modify_code=False,
            can_execute_tests=False,
            allowed_memory_categories=["short_term", "project"],
        ))

        # 6. DOCUMENTATION
        cls.register_permission(AgentPermission(
            agent_type=AgentType.DOCUMENTATION,
            allowed_tools=[
                "code.read", "code.search", "filesystem.read", "filesystem.list",
            ],
            can_delegate=False,
            can_modify_code=False,
            can_execute_tests=False,
            allowed_memory_categories=["short_term", "project"],
        ))

        # 7. SECURITY
        cls.register_permission(AgentPermission(
            agent_type=AgentType.SECURITY,
            allowed_tools=["code.search", "code.read"],
            can_delegate=False,
            can_modify_code=False,
            can_execute_tests=False,
            allowed_memory_categories=["short_term", "project", "semantic"],
        ))


# Initialize defaults
AgentPermissionManager.reset()
