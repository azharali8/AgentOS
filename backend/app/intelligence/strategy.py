"""
AgentOS Phase 7 — Execution Strategy Engine.

Deterministic strategy selection based on task classification, complexity,
risk level, historical success, and resource budget.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from backend.app.intelligence.task_history import TaskHistoryService
from backend.app.models.multi_agent import AgentType
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.intelligence.strategy")


class ExecutionStrategy(str, Enum):
    DIRECT = "DIRECT"
    SEQUENTIAL = "SEQUENTIAL"
    PARALLEL = "PARALLEL"
    RESEARCH_THEN_CODE = "RESEARCH_THEN_CODE"
    DEBUG_THEN_PATCH = "DEBUG_THEN_PATCH"
    SECURITY_FIRST = "SECURITY_FIRST"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    ITERATIVE_DEBUG = "ITERATIVE_DEBUG"


# Strategy -> ordered agent pipeline
STRATEGY_AGENTS: Dict[ExecutionStrategy, List[AgentType]] = {
    ExecutionStrategy.DIRECT: [AgentType.CODING],
    ExecutionStrategy.SEQUENTIAL: [AgentType.RESEARCH, AgentType.CODING, AgentType.REVIEWER],
    ExecutionStrategy.PARALLEL: [AgentType.RESEARCH, AgentType.DEBUGGER],
    ExecutionStrategy.RESEARCH_THEN_CODE: [AgentType.RESEARCH, AgentType.CODING, AgentType.REVIEWER],
    ExecutionStrategy.DEBUG_THEN_PATCH: [AgentType.DEBUGGER, AgentType.CODING, AgentType.REVIEWER],
    ExecutionStrategy.SECURITY_FIRST: [AgentType.SECURITY, AgentType.CODING, AgentType.REVIEWER],
    ExecutionStrategy.REVIEW_REQUIRED: [AgentType.CODING, AgentType.SECURITY, AgentType.REVIEWER],
    ExecutionStrategy.ITERATIVE_DEBUG: [AgentType.RESEARCH, AgentType.DEBUGGER, AgentType.CODING, AgentType.REVIEWER],
}


class StrategySelector:
    """Deterministic strategy selection with historical advisory input."""

    _STRATEGY_RANK: Dict[ExecutionStrategy, int] = {
        ExecutionStrategy.DIRECT: 1,
        ExecutionStrategy.PARALLEL: 2,
        ExecutionStrategy.SEQUENTIAL: 2,
        ExecutionStrategy.RESEARCH_THEN_CODE: 3,
        ExecutionStrategy.DEBUG_THEN_PATCH: 4,
        ExecutionStrategy.ITERATIVE_DEBUG: 5,
        ExecutionStrategy.REVIEW_REQUIRED: 6,
        ExecutionStrategy.SECURITY_FIRST: 7,
    }

    @classmethod
    def select_strategy(
        cls,
        task_id: str,
        task_category: str,
        complexity: str = "medium",
        risk_level: str = "low",
        has_security_concerns: bool = False,
        learning_summary: Optional[Dict[str, Any]] = None,
        learning_recommendations: Optional[List[Dict[str, Any]]] = None,
    ) -> ExecutionStrategy:
        """Select execution strategy using deterministic policy."""
        EventService.record_event(task_id, "ADAPTIVE_TASK_STARTED", payload={"category": task_category})

        # Check historical success for advisory override
        historical = TaskHistoryService.get_recommended_strategy(task_category)

        strategy: ExecutionStrategy

        if has_security_concerns or risk_level == "high":
            strategy = ExecutionStrategy.SECURITY_FIRST
        elif complexity == "simple":
            strategy = ExecutionStrategy.DIRECT
        elif task_category in ("bug_fix", "debugging", "test_failure"):
            strategy = ExecutionStrategy.DEBUG_THEN_PATCH
        elif task_category in ("analysis", "investigation", "architecture"):
            strategy = ExecutionStrategy.RESEARCH_THEN_CODE
        elif complexity == "complex":
            strategy = ExecutionStrategy.ITERATIVE_DEBUG
        elif task_category in ("documentation", "report"):
            strategy = ExecutionStrategy.SEQUENTIAL
        else:
            strategy = ExecutionStrategy.RESEARCH_THEN_CODE

        # Historical advisory: prefer a historically successful strategy only
        # when it does not reduce the current security posture.
        if historical:
            try:
                hist_strategy = ExecutionStrategy(historical)
                if (
                    hist_strategy != strategy
                    and complexity != "simple"
                    and not has_security_concerns
                    and risk_level != "high"
                    and strategy not in (ExecutionStrategy.SECURITY_FIRST, ExecutionStrategy.REVIEW_REQUIRED)
                ):
                    strategy = hist_strategy
            except ValueError:
                pass

        learning_choice = cls._learning_strategy_choice(
            baseline=strategy,
            learning_summary=learning_summary,
            learning_recommendations=learning_recommendations,
            has_security_concerns=has_security_concerns,
            risk_level=risk_level,
            complexity=complexity,
        )
        if learning_choice and learning_choice != strategy:
            strategy = learning_choice
            EventService.record_event(
                task_id=task_id,
                event_type="LEARNING_STRATEGY_OVERRIDE",
                payload={
                    "strategy": strategy.value,
                    "learning_signal": learning_summary.get("recommended_strategy") if learning_summary else None,
                },
            )

        EventService.record_event(
            task_id=task_id,
            event_type="STRATEGY_SELECTED",
            payload={
                "strategy": strategy.value,
                "complexity": complexity,
                "risk_level": risk_level,
                "learning_override": learning_choice.value if learning_choice else None,
            },
        )
        return strategy

    @classmethod
    def get_agent_pipeline(cls, strategy: ExecutionStrategy) -> List[AgentType]:
        return STRATEGY_AGENTS.get(strategy, [AgentType.RESEARCH, AgentType.CODING])

    @classmethod
    def estimate_resource_cost(cls, strategy: ExecutionStrategy) -> Dict[str, int]:
        """Estimate relative resource cost for a strategy."""
        agents = cls.get_agent_pipeline(strategy)
        return {
            "estimated_agents": len(agents),
            "estimated_tool_calls": len(agents) * 5,
            "estimated_tokens": len(agents) * 2000,
        }

    @classmethod
    def _learning_strategy_choice(
        cls,
        *,
        baseline: ExecutionStrategy,
        learning_summary: Optional[Dict[str, Any]],
        learning_recommendations: Optional[List[Dict[str, Any]]],
        has_security_concerns: bool,
        risk_level: str,
        complexity: str,
    ) -> Optional[ExecutionStrategy]:
        if has_security_concerns or risk_level == "high":
            return None

        candidates: List[tuple[ExecutionStrategy, float, float]] = []

        if learning_summary and learning_summary.get("recommended_strategy"):
            try:
                candidate = ExecutionStrategy(str(learning_summary["recommended_strategy"]))
                confidence = float(learning_summary.get("average_confidence", 0.0))
                success_rate = float(learning_summary.get("success_rate", 0.0))
                candidates.append((candidate, confidence, success_rate))
            except ValueError:
                pass

        for recommendation in learning_recommendations or []:
            if not isinstance(recommendation, dict):
                continue
            if recommendation.get("recommendation_type") not in {"strategy", "failure_recovery", "reinforcement"}:
                continue
            target = recommendation.get("target_strategy")
            if not target:
                continue
            try:
                candidate = ExecutionStrategy(str(target))
            except ValueError:
                continue
            confidence = float(recommendation.get("confidence", 0.0))
            evidence_count = float(recommendation.get("evidence_count", 0))
            candidates.append((candidate, confidence, evidence_count))

        if not candidates:
            return None

        current_rank = cls._STRATEGY_RANK.get(baseline, 0)
        best_candidate: Optional[ExecutionStrategy] = None
        best_score = -1.0

        for candidate, confidence, evidence_strength in candidates:
            candidate_rank = cls._STRATEGY_RANK.get(candidate, 0)
            if candidate_rank < current_rank:
                continue
            score = (confidence * 0.7) + (min(1.0, evidence_strength / 5.0) * 0.3)
            if complexity == "simple" and candidate in (ExecutionStrategy.DEBUG_THEN_PATCH, ExecutionStrategy.ITERATIVE_DEBUG, ExecutionStrategy.RESEARCH_THEN_CODE):
                score += 0.1
            if score > best_score:
                best_score = score
                best_candidate = candidate

        if best_candidate and best_candidate != baseline and best_score >= 0.45:
            return best_candidate
        return None
