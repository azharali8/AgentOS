"""
AgentOS Phase 7 — Historical Task Intelligence Service.

Stores structured execution metadata for learning from previous runs.
Never stores secrets, API keys, tokens, or sensitive file contents.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.app.intelligence.performance_store import PerformanceStore
from backend.app.memory.experience import ExperienceMemory
from backend.app.models.experience import FailureCategory
from backend.app.intelligence.experience_store import ExperienceStore
from backend.app.observability.redaction import redact_secrets
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.intelligence.task_history")


class TaskHistoryService:
    """Records and retrieves structured task execution history."""

    @classmethod
    def record_execution(
        cls,
        task_id: str,
        task_category: str,
        strategy_used: str,
        agents_involved: List[str],
        success: bool,
        duration_seconds: float = 0.0,
        iterations: int = 1,
        tools_used: Optional[List[str]] = None,
        failure_category: Optional[FailureCategory] = None,
        resource_consumption: Optional[Dict[str, Any]] = None,
        **experience_metadata: Any,
    ) -> str:
        """Persist structured task history metadata."""
        record = redact_secrets({
            "task_category": task_category,
            "strategy_used": strategy_used,
            "agents_involved": agents_involved,
            "success": success,
            "duration_seconds": duration_seconds,
            "iterations": iterations,
            "tools_used": tools_used or [],
            "failure_category": failure_category.value if failure_category else None,
            "resource_consumption": resource_consumption or {},
        })

        history_id = PerformanceStore.save_task_history(task_id, record)

        # Also store in experience memory for fast retrieval
        ExperienceStore.record_experience(
            ExperienceStore.build_experience(
                task_id=task_id,
                task_type=task_category,
                task_description=experience_metadata.get("task_description")
                or experience_metadata.get("task_summary")
                or experience_metadata.get("instruction_summary")
                or task_category,
                task_description_hash=experience_metadata.get("task_description_hash"),
                task_complexity=experience_metadata.get("task_complexity", "medium"),
                project_type=experience_metadata.get("project_type", "python"),
                framework=experience_metadata.get("framework"),
                selected_strategy=strategy_used,
                selected_model=experience_metadata.get("selected_model"),
                selected_agents=experience_metadata.get("selected_agents", agents_involved),
                decomposition_summary=experience_metadata.get("decomposition_summary", []),
                plan_score=float(experience_metadata.get("plan_score", 0.0)),
                resource_budget=experience_metadata.get("resource_budget", resource_consumption or {}),
                execution_duration=duration_seconds,
                tool_call_count=int(experience_metadata.get("tool_call_count", len(tools_used or []))),
                token_usage=int((resource_consumption or {}).get("tokens_used", experience_metadata.get("token_usage", 0))),
                success=success,
                failure_type=experience_metadata.get("failure_type") or (failure_category.value if failure_category else None),
                failure_pattern=experience_metadata.get("failure_pattern"),
                regression_detected=bool(experience_metadata.get("regression_detected", False)),
                approval_required=bool(experience_metadata.get("approval_required", False)),
                approval_outcome=experience_metadata.get("approval_outcome"),
                security_events=experience_metadata.get("security_events", []),
                evaluation_score=float(experience_metadata.get("evaluation_score", 0.0)),
                final_outcome=experience_metadata.get("final_outcome", "SUCCESS" if success else "FAILED"),
                parent_task_id=experience_metadata.get("parent_task_id"),
                evidence_ids=experience_metadata.get("evidence_ids", []),
                task_summary=experience_metadata.get("task_summary") or experience_metadata.get("instruction_summary") or task_category,
                learning_metadata={
                    "iterations": iterations,
                    "retries": experience_metadata.get("retries", 0),
                    "estimated_cost": experience_metadata.get("estimated_cost", 0.0),
                    "tools_used": tools_used or [],
                    "resource_consumption": resource_consumption or {},
                    "lessons": experience_metadata.get("lessons", []),
                    "provider": experience_metadata.get("selected_provider"),
                    "model": experience_metadata.get("selected_model"),
                    "history_id": history_id,
                },
                experience_id=experience_metadata.get("experience_id", history_id),
            )
        )

        EventService.record_event(
            task_id=task_id,
            event_type="HISTORICAL_CONTEXT_RETRIEVED",
            payload={"history_id": history_id, "strategy": strategy_used},
        )
        return history_id

    @classmethod
    def get_history(cls, task_id: str) -> Optional[Dict[str, Any]]:
        return PerformanceStore.get_task_history(task_id)

    @classmethod
    def get_recommended_strategy(cls, task_category: str) -> Optional[str]:
        """Return historically successful strategy for a task category."""
        strategies = ExperienceMemory.get_successful_strategies(task_category)
        return strategies[0] if strategies else None

    @classmethod
    def get_similar_executions(cls, task_category: str, limit: int = 5) -> List[ExperienceRecord]:
        return ExperienceMemory.search_similar(task_type=task_category, only_successful=True, limit=limit)

    @classmethod
    def get_failure_history(cls, category: Optional[FailureCategory] = None) -> List[ExperienceRecord]:
        return ExperienceMemory.get_failure_patterns(failure_category=category)
