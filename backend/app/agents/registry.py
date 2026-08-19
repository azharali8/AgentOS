"""
AgentOS Phase 5 — Agent Registry.

Maintains registry of all specialized agents, declaring:
- Identity, type, and capabilities
- Allowlisted tool operations
- Concurrency and runtime bounds
Rejects duplicate identities and validates capability matching.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from backend.app.models.multi_agent import AgentCapability, AgentDefinition, AgentType

logger = logging.getLogger("agentos.agent_registry")


class AgentRegistry:
    """Central registry of all specialized agents in AgentOS."""

    _agents: Dict[str, AgentDefinition] = {}

    @classmethod
    def register(cls, agent_def: AgentDefinition) -> None:
        """Register a new specialized agent definition. Rejects duplicates."""
        if agent_def.name in cls._agents:
            raise ValueError(f"Agent '{agent_def.name}' is already registered.")
        cls._agents[agent_def.name] = agent_def
        logger.info("Registered agent: %s (%s)", agent_def.name, agent_def.agent_type.value)

    @classmethod
    def unregister(cls, name: str) -> None:
        """Unregister an agent definition."""
        if name in cls._agents:
            del cls._agents[name]
            logger.info("Unregistered agent: %s", name)

    @classmethod
    def get(cls, name: str) -> Optional[AgentDefinition]:
        """Lookup an agent definition by name."""
        return cls._agents.get(name)

    @classmethod
    def get_by_type(cls, agent_type: AgentType) -> Optional[AgentDefinition]:
        """Find the default registered agent for a specific AgentType."""
        for agent in cls._agents.values():
            if agent.agent_type == agent_type:
                return agent
        return None

    @classmethod
    def list_agents(cls) -> List[AgentDefinition]:
        """List all currently registered agent definitions."""
        return list(cls._agents.values())

    @classmethod
    def resolve_by_capability(cls, capability: AgentCapability) -> List[AgentDefinition]:
        """Query all agents possessing a specific capability."""
        return [
            agent for agent in cls._agents.values()
            if capability in agent.capabilities
        ]

    @classmethod
    def reset(cls) -> None:
        """Reset and re-populate the standard Phase 5 agent catalog."""
        cls._agents.clear()
        cls._register_defaults()

    @classmethod
    def _register_defaults(cls) -> None:
        """Initialize standard Phase 5 specialized agents."""
        # 1. Supervisor
        cls.register(AgentDefinition(
            name="supervisor",
            agent_type=AgentType.SUPERVISOR,
            description="Decomposes user tasks, plans DAG execution, supervises specialized agents, and merges findings.",
            capabilities=[
                AgentCapability.DECOMPOSITION,
                AgentCapability.DELEGATION,
                AgentCapability.SUPERVISION,
            ],
            allowed_tools=[],  # Supervisor does not execute tools directly
            risk_level="LOW",
            max_concurrency=1,
            max_execution_time=300,
        ))

        # 2. Research
        cls.register(AgentDefinition(
            name="research",
            agent_type=AgentType.RESEARCH,
            description="Explores codebases, parses AST symbols, scans repository structure, and inspects Git history.",
            capabilities=[
                AgentCapability.CODE_SEARCH,
                AgentCapability.CODE_READ,
                AgentCapability.CODE_SYMBOLS,
                AgentCapability.GIT_READ,
            ],
            allowed_tools=[
                "code.search",
                "code.read",
                "code.symbols",
                "code.scan",
                "git.status",
                "git.diff",
                "git.log",
                "git.show",
                "filesystem.list",
                "filesystem.read",
            ],
            risk_level="LOW",
            max_concurrency=4,
            max_execution_time=120,
        ))

        # 3. Coding
        cls.register(AgentDefinition(
            name="coding",
            agent_type=AgentType.CODING,
            description="Generates, validates, and securely applies patches to resolve bugs or implement changes.",
            capabilities=[
                AgentCapability.CODE_SEARCH,
                AgentCapability.CODE_READ,
                AgentCapability.CODE_SYMBOLS,
                AgentCapability.PATCH_APPLY,
            ],
            allowed_tools=[
                "code.search",
                "code.read",
                "code.symbols",
                "patch.apply",
                "patch.rollback",
            ],
            risk_level="HIGH",
            max_concurrency=2,
            max_execution_time=180,
        ))

        # 4. Debugger
        cls.register(AgentDefinition(
            name="debugger",
            agent_type=AgentType.DEBUGGER,
            description="Diagnoses test failures, identifies root causes, and validates bug fixes via test runner.",
            capabilities=[
                AgentCapability.TEST_RUN,
                AgentCapability.CODE_SEARCH,
                AgentCapability.CODE_READ,
                AgentCapability.CODE_SYMBOLS,
            ],
            allowed_tools=[
                "test.run",
                "code.search",
                "code.read",
                "code.symbols",
            ],
            risk_level="MEDIUM",
            max_concurrency=2,
            max_execution_time=180,
        ))

        # 5. Reviewer
        cls.register(AgentDefinition(
            name="reviewer",
            agent_type=AgentType.REVIEWER,
            description="Evaluates execution results, completeness, regressions, and safety invariants.",
            capabilities=[
                AgentCapability.REVIEW,
            ],
            allowed_tools=[],
            risk_level="LOW",
            max_concurrency=2,
            max_execution_time=60,
        ))

        # 6. Documentation
        cls.register(AgentDefinition(
            name="documentation",
            agent_type=AgentType.DOCUMENTATION,
            description="Inspects code and produces structured markdown reports, guides, and engineering logs.",
            capabilities=[
                AgentCapability.CODE_READ,
                AgentCapability.CODE_SEARCH,
                AgentCapability.DOCUMENTATION,
            ],
            allowed_tools=[
                "code.read",
                "code.search",
                "filesystem.read",
                "filesystem.list",
            ],
            risk_level="LOW",
            max_concurrency=2,
            max_execution_time=90,
        ))

        # 7. Security
        cls.register(AgentDefinition(
            name="security",
            agent_type=AgentType.SECURITY,
            description="Performs advisory risk analysis, inspects sensitive files, and reviews proposed code patches.",
            capabilities=[
                AgentCapability.SECURITY_INSPECTION,
                AgentCapability.POLICY_EVALUATION,
            ],
            allowed_tools=[
                "code.search",
                "code.read",
            ],
            risk_level="LOW",
            max_concurrency=2,
            max_execution_time=60,
        ))


# Initialize defaults upon module load
AgentRegistry.reset()
