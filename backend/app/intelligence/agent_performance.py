"""
AgentOS Phase 7 — Agent Performance Tracking Subsystem.

Tracks per-agent metrics: tasks assigned/completed/failed, success rate,
execution time, tool calls, token usage, approval frequency, and specialization.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.app.evaluation.agent_profiler import AgentProfiler
from backend.app.intelligence.performance_store import PerformanceStore
from backend.app.models.experience import AgentPerformanceProfile
from backend.app.models.multi_agent import AgentType
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.intelligence.performance")


class AgentPerformanceTracker:
    """Unified agent performance tracking with in-memory profiler + SQLite persistence."""

    @classmethod
    def record_execution(
        cls,
        agent_type: AgentType,
        success: bool,
        duration_seconds: float = 0.0,
        tokens_used: int = 0,
        tool_calls: int = 0,
        task_type: str = "general",
        approval_required: bool = False,
        retry_count: int = 0,
        regression_detected: bool = False,
        security_violations_prevented: int = 0,
    ) -> AgentPerformanceProfile:
        """Record agent execution and persist performance snapshot."""
        prof = AgentProfiler.record_execution(
            agent_type=agent_type,
            success=success,
            duration_seconds=duration_seconds,
            tokens_used=tokens_used,
            tool_calls=tool_calls,
            task_type=task_type,
        )

        # Update task-type specialization
        tt_key = task_type.lower()
        if tt_key not in prof.task_type_success:
            prof.task_type_success[tt_key] = 1.0 if success else 0.0
        else:
            prev = prof.task_type_success[tt_key]
            prof.task_type_success[tt_key] = round((prev + (1.0 if success else 0.0)) / 2, 3)

        if retry_count > 0:
            prof.retry_rate = round(prof.retry_rate + (1.0 / max(1, prof.task_count)), 3)
        if regression_detected:
            prof.regression_rate = round(prof.regression_rate + (1.0 / max(1, prof.task_count)), 3)

        metrics = {
            "tasks_assigned": prof.task_count,
            "tasks_completed": prof.successful_tasks,
            "tasks_failed": prof.failed_tasks,
            "success_rate": prof.success_rate,
            "avg_execution_time": prof.avg_runtime_seconds,
            "avg_tool_calls": prof.avg_tool_calls,
            "avg_token_usage": prof.avg_tokens,
            "approval_frequency": 1 if approval_required else 0,
            "retry_frequency": retry_count,
            "regression_frequency": 1 if regression_detected else 0,
            "task_type_success": prof.task_type_success,
            "security_violations_prevented": security_violations_prevented,
            "task_type": task_type,
        }

        PerformanceStore.save_agent_performance(agent_type.value, metrics)

        EventService.record_event(
            task_id="system",
            event_type="AGENT_PERFORMANCE_UPDATED",
            payload={"agent_type": agent_type.value, "success_rate": prof.success_rate},
        )
        return prof

    @classmethod
    def get_profile(cls, agent_type: AgentType) -> AgentPerformanceProfile:
        return AgentProfiler.get_profile(agent_type)

    @classmethod
    def list_profiles(cls) -> List[AgentPerformanceProfile]:
        return AgentProfiler.list_profiles()

    @classmethod
    def get_specialization_score(cls, agent_type: AgentType, task_type: str) -> float:
        """Return historical success rate for agent on a specific task type."""
        prof = cls.get_profile(agent_type)
        return prof.task_type_success.get(task_type.lower(), prof.success_rate)

    @classmethod
    def reset(cls) -> None:
        AgentProfiler.reset()
