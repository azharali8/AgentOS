"""
AgentOS Phase 7 — Adaptive Resource Allocation.

Calculates bounded resource allocations based on task complexity.
Global hard limits remain authoritative — never exceeded.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.app.config.settings import settings
from backend.app.intelligence.strategy import ExecutionStrategy, StrategySelector
from backend.app.models.multi_agent import AgentBudget
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.intelligence.resource_allocator")


# Complexity multipliers (bounded)
_COMPLEXITY_MULTIPLIERS: Dict[str, float] = {
    "simple": 0.5,
    "medium": 1.0,
    "complex": 1.5,
    "critical": 2.0,
}


class AdaptiveResourceAllocator:
    """Computes adaptive budgets within global hard limits."""

    @classmethod
    def allocate_budget(
        cls,
        task_id: str,
        complexity: str = "medium",
        strategy: ExecutionStrategy = ExecutionStrategy.DIRECT,
        security_sensitive: bool = False,
        historical_profile: Optional[Dict[str, Any]] = None,
    ) -> AgentBudget:
        """Calculate bounded resource allocation for a task."""
        multiplier = _COMPLEXITY_MULTIPLIERS.get(complexity, 1.0)
        cost = StrategySelector.estimate_resource_cost(strategy)

        # Base allocation scaled by complexity
        max_tokens = min(
            settings.MAX_AGENT_TOKENS,
            int(settings.MAX_AGENT_TOKENS * multiplier * 0.5),
        )
        max_tool_calls = min(
            settings.MAX_AGENT_TOOL_CALLS,
            int(settings.MAX_AGENT_TOOL_CALLS * multiplier * 0.6),
        )
        max_execution_time = min(
            settings.MAX_AGENT_RUNTIME,
            int(settings.MAX_AGENT_RUNTIME * multiplier),
        )
        max_retries = min(settings.MAX_AGENT_RETRIES, max(1, int(settings.MAX_AGENT_RETRIES * multiplier * 0.5)))
        max_subtasks = min(settings.MAX_SUBTASKS, max(2, int(cost["estimated_agents"] * multiplier)))
        max_depth = min(settings.MAX_AGENT_DEPTH, max(2, int(multiplier + 1)))

        # Security-sensitive tasks get additional review budget
        if security_sensitive:
            max_tool_calls = min(settings.MAX_AGENT_TOOL_CALLS, max_tool_calls + 5)
            max_retries = min(settings.MAX_AGENT_RETRIES, max_retries + 1)

        if historical_profile:
            avg_tokens = float(historical_profile.get("average_tokens", 0.0) or 0.0)
            avg_tool_calls = float(historical_profile.get("average_tool_calls", 0.0) or 0.0)
            avg_duration = float(historical_profile.get("average_duration_seconds", 0.0) or 0.0)

            if avg_tokens > 0:
                max_tokens = min(settings.MAX_AGENT_TOKENS, max(max_tokens, int(avg_tokens * 1.15)))
            if avg_tool_calls > 0:
                max_tool_calls = min(settings.MAX_AGENT_TOOL_CALLS, max(max_tool_calls, int(avg_tool_calls * 1.2)))
            if avg_duration > 0:
                max_execution_time = min(settings.MAX_AGENT_RUNTIME, max(max_execution_time, int(avg_duration * 1.35)))

        budget = AgentBudget(
            max_tokens=max_tokens,
            max_tool_calls=max_tool_calls,
            max_execution_time=max_execution_time,
            max_retries=max_retries,
            max_subtasks=max_subtasks,
            max_depth=max_depth,
        )

        EventService.record_event(
            task_id=task_id,
            event_type="ADAPTIVE_BUDGET_ALLOCATED",
            payload={
                "complexity": complexity,
                "strategy": strategy.value,
                "max_tokens": max_tokens,
                "max_tool_calls": max_tool_calls,
                "max_execution_time": max_execution_time,
            },
        )
        EventService.record_event(
            task_id=task_id,
            event_type="RESOURCES_ALLOCATED",
            payload={
                "complexity": complexity,
                "strategy": strategy.value,
                "tokens": max_tokens,
                "tool_calls": max_tool_calls,
                "runtime": max_execution_time,
                "retries": max_retries,
                "subtasks": max_subtasks,
                "depth": max_depth,
            },
        )
        return budget

    @classmethod
    def validate_within_limits(cls, budget: AgentBudget) -> bool:
        """Verify budget does not exceed global hard limits."""
        return (
            budget.max_tokens <= settings.MAX_AGENT_TOKENS
            and budget.max_tool_calls <= settings.MAX_AGENT_TOOL_CALLS
            and budget.max_execution_time <= settings.MAX_AGENT_RUNTIME
            and budget.max_retries <= settings.MAX_AGENT_RETRIES
            and budget.max_subtasks <= settings.MAX_SUBTASKS
            and budget.max_depth <= settings.MAX_AGENT_DEPTH
        )
