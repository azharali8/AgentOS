"""
AgentOS Phase 7 — Plan Quality Scoring.

Scores proposed plans before execution using coverage, dependency correctness,
capability matching, security compatibility, and historical success.
Score is advisory unless deterministic policy rejects the plan.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.app.config.settings import settings
from backend.app.intelligence.performance_store import PerformanceStore
from backend.app.intelligence.task_history import TaskHistoryService
from backend.app.models.multi_agent import AgentType, SubTask
from backend.app.security.agent_permissions import AgentPermissionManager
from backend.app.services.event_service import EventService
from backend.app.services.task_decomposer import TaskDecomposer
from pydantic import BaseModel, Field

logger = logging.getLogger("agentos.intelligence.plan_scorer")


class PlanScore(BaseModel):
    task_id: str
    score: float = Field(ge=0.0, le=1.0)
    task_coverage: float = Field(ge=0.0, le=1.0)
    dependency_correctness: float = Field(ge=0.0, le=1.0)
    capability_matching: float = Field(ge=0.0, le=1.0)
    security_compatibility: float = Field(ge=0.0, le=1.0)
    resource_cost: float = Field(ge=0.0, le=1.0)
    historical_success: float = Field(ge=0.0, le=1.0)
    unnecessary_complexity: float = Field(ge=0.0, le=1.0)
    rejected: bool = False
    rejection_reason: Optional[str] = None


class PlanScorer:
    """Deterministic plan quality scoring with policy rejection."""

    @classmethod
    def score_plan(
        cls,
        task_id: str,
        instruction: str,
        subtasks: List[SubTask],
        task_category: str = "general",
    ) -> PlanScore:
        """Score a proposed execution plan."""
        # Hard rejections
        if len(subtasks) > settings.MAX_SUBTASKS:
            score = PlanScore(
                task_id=task_id, score=0.0,
                task_coverage=0.0, dependency_correctness=0.0,
                capability_matching=0.0, security_compatibility=0.0,
                resource_cost=0.0, historical_success=0.0, unnecessary_complexity=1.0,
                rejected=True, rejection_reason=f"Exceeds MAX_SUBTASKS ({settings.MAX_SUBTASKS})",
            )
            cls._record_score(task_id, score)
            return score

        # Validate DAG
        try:
            TaskDecomposer.detect_cycles(subtasks)
            dep_score = 1.0
        except ValueError:
            dep_score = 0.0

        # Capability matching
        cap_score = cls._score_capabilities(subtasks)

        # Security compatibility
        sec_score = cls._score_security(subtasks)

        # Task coverage heuristic
        coverage = min(1.0, len(subtasks) / max(1, cls._expected_subtask_count(instruction)))

        # Resource cost (fewer subtasks = lower cost = higher score)
        resource = max(0.3, 1.0 - (len(subtasks) / settings.MAX_SUBTASKS))

        # Historical success
        hist_strategy = TaskHistoryService.get_recommended_strategy(task_category)
        hist_score = 0.8 if hist_strategy else 0.6

        # Unnecessary complexity penalty
        expected = cls._expected_subtask_count(instruction)
        complexity_penalty = max(0.0, (len(subtasks) - expected * 2) / settings.MAX_SUBTASKS)

        overall = round(
            (coverage * 0.2 + dep_score * 0.2 + cap_score * 0.15 + sec_score * 0.2
             + resource * 0.1 + hist_score * 0.1 + (1.0 - complexity_penalty) * 0.05),
            3,
        )

        score = PlanScore(
            task_id=task_id,
            score=min(1.0, overall),
            task_coverage=round(coverage, 3),
            dependency_correctness=round(dep_score, 3),
            capability_matching=round(cap_score, 3),
            security_compatibility=round(sec_score, 3),
            resource_cost=round(resource, 3),
            historical_success=round(hist_score, 3),
            unnecessary_complexity=round(complexity_penalty, 3),
        )

        cls._record_score(task_id, score)
        return score

    @classmethod
    def _score_capabilities(cls, subtasks: List[SubTask]) -> float:
        if not subtasks:
            return 0.0
        matched = 0
        for st in subtasks:
            if st.assigned_agent != AgentType.SUPERVISOR:
                matched += 1
        return matched / len(subtasks)

    @classmethod
    def _score_security(cls, subtasks: List[SubTask]) -> float:
        """Verify coding subtasks have permission and security review exists."""
        has_coding = any(st.assigned_agent == AgentType.CODING for st in subtasks)
        has_security = any(st.assigned_agent == AgentType.SECURITY for st in subtasks)
        has_reviewer = any(st.assigned_agent == AgentType.REVIEWER for st in subtasks)

        if has_coding:
            if not AgentPermissionManager.can_modify_code(AgentType.CODING):
                return 0.0
            if not (has_security or has_reviewer):
                return 0.7  # Advisory: should have review
        return 1.0

    @classmethod
    def _expected_subtask_count(cls, instruction: str) -> int:
        inst = instruction.lower()
        if any(kw in inst for kw in ("fix", "bug", "test", "debug")):
            return 4
        if any(kw in inst for kw in ("document", "readme", "report")):
            return 2
        return 2

    @classmethod
    def _record_score(cls, task_id: str, score: PlanScore) -> None:
        EventService.record_event(
            task_id=task_id,
            event_type="PLAN_SCORED",
            payload=score.model_dump(mode="json"),
        )
        PerformanceStore.save_plan_evaluation(task_id, score.model_dump(mode="json"))
