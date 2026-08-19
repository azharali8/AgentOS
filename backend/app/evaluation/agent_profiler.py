"""
AgentOS Phase 7 — Agent Performance Profiler.

Maintains empirical performance profiles for each specialized agent:
- Success rate
- Average latency
- Average token consumption
- Retry & failure statistics
- Task-type specialization scores
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Optional

from backend.app.models.experience import AgentPerformanceProfile
from backend.app.models.multi_agent import AgentType
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.agent_profiler")


class AgentProfiler:
    """Calculates and maintains empirical performance profiles for agents."""

    _profiles: Dict[AgentType, AgentPerformanceProfile] = {}

    @classmethod
    def get_profile(cls, agent_type: AgentType) -> AgentPerformanceProfile:
        """Retrieve profile or generate default initialized profile."""
        if agent_type not in cls._profiles:
            cls._profiles[agent_type] = AgentPerformanceProfile(agent_type=agent_type)
        return cls._profiles[agent_type]

    @classmethod
    def record_execution(
        cls,
        agent_type: AgentType,
        success: bool,
        duration_seconds: float = 0.0,
        tokens_used: int = 0,
        tool_calls: int = 0,
        task_type: str = "general",
    ) -> AgentPerformanceProfile:
        """Update empirical metrics for an agent after a subtask run."""
        prof = cls.get_profile(agent_type)
        prof.task_count += 1
        if success:
            prof.successful_tasks += 1
        else:
            prof.failed_tasks += 1

        prof.success_rate = round(prof.successful_tasks / max(1, prof.task_count), 3)

        # Running average updates
        n = prof.task_count
        prof.avg_runtime_seconds = round(((prof.avg_runtime_seconds * (n - 1)) + duration_seconds) / n, 3)
        prof.avg_tokens = round(((prof.avg_tokens * (n - 1)) + tokens_used) / n, 1)
        prof.avg_tool_calls = round(((prof.avg_tool_calls * (n - 1)) + tool_calls) / n, 1)

        cls._profiles[agent_type] = prof

        EventService.record_event(
            task_id="system",
            event_type="AGENT_PROFILE_UPDATED",
            payload={
                "agent_type": agent_type.value,
                "task_count": prof.task_count,
                "success_rate": prof.success_rate,
            },
        )
        return prof

    @classmethod
    def list_profiles(cls) -> List[AgentPerformanceProfile]:
        # Ensure all types exist
        for at in AgentType:
            cls.get_profile(at)
        return list(cls._profiles.values())

    @classmethod
    def reset(cls) -> None:
        cls._profiles.clear()
