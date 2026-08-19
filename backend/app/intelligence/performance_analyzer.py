"""
AgentOS Phase 7 - Performance Intelligence Analyzer.

Builds bounded performance profiles from persisted execution history, agent
profiling data, and routing decisions. Historical data is advisory only.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.app.config.settings import settings
from backend.app.evaluation.agent_profiler import AgentProfiler
from backend.app.intelligence.performance_store import PerformanceStore
from backend.app.models.multi_agent import AgentType


class PerformanceProfile(BaseModel):
    task_type: str
    agent_type: str
    model: str
    average_latency: float = 0.0
    success_rate: float = 0.0
    average_tokens: float = 0.0
    failure_rate: float = 0.0
    retry_rate: float = 0.0
    average_tool_latency: float = 0.0
    average_approval_latency: float = 0.0
    sample_size: int = 0
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class PerformanceAnalyzer:
    """Derives structured performance profiles from historical execution data."""

    @classmethod
    def analyze(
        cls,
        task_type: Optional[str] = None,
        agent_type: Optional[AgentType | str] = None,
        model: Optional[str] = None,
        limit: int = 50,
    ) -> List[PerformanceProfile]:
        histories = PerformanceStore.list_task_histories(limit=limit)
        routing_decisions = PerformanceStore.list_routing_decisions(limit=limit)
        agent_profiles = AgentProfiler.list_profiles()

        selected_task_types = [task_type] if task_type else sorted(
            {row.get("task_category", "general") for row in histories} or {"general"}
        )

        selected_agent_types: List[AgentType] = []
        if agent_type is None:
            selected_agent_types = [profile.agent_type for profile in agent_profiles]
        else:
            try:
                selected_agent_types = [agent_type if isinstance(agent_type, AgentType) else AgentType(str(agent_type))]
            except ValueError:
                selected_agent_types = [AgentType.RESEARCH]

        default_model = model or (
            routing_decisions[0]["model"] if routing_decisions else settings.OLLAMA_MODEL
        )

        profiles: List[PerformanceProfile] = []
        for task_name in selected_task_types:
            task_histories = [row for row in histories if row.get("task_category", "general") == task_name]
            for agent in selected_agent_types:
                prof = AgentProfiler.get_profile(agent)
                if task_name not in prof.task_type_success and not task_histories:
                    sample_size = prof.task_count
                else:
                    sample_size = max(prof.task_count, len(task_histories))

                average_latency = prof.avg_runtime_seconds
                success_rate = prof.task_type_success.get(task_name, prof.success_rate)
                failure_rate = round(1.0 - success_rate, 3)
                confidence = min(1.0, round(0.35 + (sample_size / max(1, sample_size + 5)), 3))

                profiles.append(
                    PerformanceProfile(
                        task_type=task_name,
                        agent_type=agent.value,
                        model=default_model,
                        average_latency=round(average_latency, 3),
                        success_rate=round(success_rate, 3),
                        average_tokens=round(prof.avg_tokens, 1),
                        failure_rate=round(failure_rate, 3),
                        retry_rate=round(prof.retry_rate, 3),
                        average_tool_latency=round(prof.avg_tool_calls * 0.2, 3),
                        average_approval_latency=0.0,
                        sample_size=sample_size,
                        confidence=confidence,
                    )
                )

        if profiles:
            from backend.app.services.event_service import EventService

            EventService.record_event(
                task_id="system",
                event_type="PERFORMANCE_PROFILE_CREATED",
                payload={"profile_count": len(profiles), "task_type": task_type or "mixed"},
            )

        return profiles

    @classmethod
    def summarize(cls, task_type: Optional[str] = None) -> Dict[str, Any]:
        profiles = cls.analyze(task_type=task_type)
        if not profiles:
            return {
                "task_type": task_type or "general",
                "profile_count": 0,
                "average_success_rate": 0.0,
                "average_latency": 0.0,
                "average_tokens": 0.0,
            }

        return {
            "task_type": task_type or profiles[0].task_type,
            "profile_count": len(profiles),
            "average_success_rate": round(sum(p.success_rate for p in profiles) / len(profiles), 3),
            "average_latency": round(sum(p.average_latency for p in profiles) / len(profiles), 3),
            "average_tokens": round(sum(p.average_tokens for p in profiles) / len(profiles), 1),
        }
