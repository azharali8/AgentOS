"""
AgentOS Phase 7 — Self-Evaluation Loop.

Evaluates completed tasks across correctness, security, efficiency,
reliability, resource usage, agent selection, and decomposition quality.
Does NOT modify code directly.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.app.agents.reflection import ReflectionEngine
from backend.app.intelligence.experience_models import hash_task_description
from backend.app.intelligence.learning_engine import LearningEngine
from backend.app.intelligence.performance_store import PerformanceStore
from backend.app.models.experience import ReflectionResult
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.intelligence.self_evaluator")


class SelfEvaluator:
    """Post-execution evaluation with multi-dimensional scoring."""

    @classmethod
    def evaluate_task(
        cls,
        task_id: str,
        instruction: str,
        subtask_results: Dict[str, Any],
        success: bool = True,
        iterations: int = 1,
        strategy: str = "DIRECT",
        agents_used: Optional[List[str]] = None,
        resource_usage: Optional[Dict[str, Any]] = None,
    ) -> ReflectionResult:
        """Evaluate task execution and store structured feedback."""
        EventService.record_event(task_id, "TASK_EVALUATED", payload={"success": success, "strategy": strategy})

        base = ReflectionEngine.reflect_on_task(
            task_id=task_id,
            instruction=instruction,
            subtask_results=subtask_results,
            success=success,
            iterations=iterations,
        )

        # Extended evaluation dimensions
        evaluation = {
            "task_id": task_id,
            "correctness": base.overall_quality,
            "security": 1.0 if success else 0.8,
            "efficiency": base.execution_efficiency,
            "reliability": 0.95 if iterations == 1 else 0.75,
            "resource_usage_score": cls._score_resource_usage(resource_usage or {}),
            "agent_selection_score": base.routing_quality,
            "decomposition_quality": base.planning_quality,
            "regression_safety": 1.0 if success else 0.5,
            "strategy": strategy,
            "agents_used": agents_used or [],
            "overall_quality": base.overall_quality,
            "lessons": base.lessons,
            "recommended_strategy": base.recommended_strategy,
        }

        PerformanceStore.save_strategy_evaluation(task_id, evaluation)
        PerformanceStore.save_execution_evaluation(task_id, {
            "success": success,
            "quality_score": base.overall_quality,
            "efficiency_score": base.execution_efficiency,
            "safety_score": 1.0 if success else 0.8,
            "coordination_score": base.routing_quality,
            "recommendations": base.lessons,
        })

        history = PerformanceStore.get_task_history(task_id) or {}
        routing = PerformanceStore.get_task_routing(task_id) or {}
        LearningEngine.update_experience(task_id, {
            "task_type": history.get("task_category", "general"),
            "task_complexity": history.get("metadata", {}).get("task_complexity", "medium"),
            "task_description_hash": hash_task_description(instruction),
            "selected_strategy": strategy,
            "selected_provider": routing.get("provider"),
            "selected_model": routing.get("model"),
            "selected_agents": agents_used or [],
            "plan_score": float(history.get("metadata", {}).get("plan_score", 0.0)),
            "resource_budget": resource_usage or history.get("metadata", {}).get("resource_consumption", {}),
            "execution_duration": float(history.get("duration_seconds", 0.0)),
            "tool_call_count": int((resource_usage or {}).get("tool_calls", 0) or 0),
            "token_usage": int((resource_usage or {}).get("tokens_used", 0) or 0),
            "success": success,
            "failure_type": history.get("metadata", {}).get("failure_category"),
            "failure_pattern": history.get("metadata", {}).get("failure_pattern"),
            "regression_detected": bool(history.get("metadata", {}).get("regression_detected", False)),
            "approval_required": bool(history.get("metadata", {}).get("approval_required", False)),
            "approval_outcome": history.get("metadata", {}).get("approval_outcome"),
            "security_events": history.get("metadata", {}).get("security_events", []),
            "evaluation_score": float(base.overall_quality),
            "final_outcome": "SUCCESS" if success else "FAILED",
            "task_summary": instruction[:500],
            "learning_metadata": {
                "lessons": base.lessons,
                "recommended_strategy": base.recommended_strategy,
                "iterations": iterations,
                "agents_used": agents_used or [],
                "provider": routing.get("provider"),
                "model": routing.get("model"),
                "evaluation": evaluation,
            },
        }, create_if_missing=False)

        EventService.record_event(
            task_id,
            "EXECUTION_EVALUATED",
            payload={
                "success": success,
                "quality_score": base.overall_quality,
                "efficiency_score": base.execution_efficiency,
                "safety_score": 1.0 if success else 0.8,
                "coordination_score": base.routing_quality,
            },
        )

        return base

    @classmethod
    def _score_resource_usage(cls, usage: Dict[str, Any]) -> float:
        tokens = usage.get("tokens_used", 0)
        tool_calls = usage.get("tool_calls", 0)
        if tokens == 0 and tool_calls == 0:
            return 0.9
        # Lower score for high resource consumption
        score = 1.0
        if tokens > 50000:
            score -= 0.2
        if tool_calls > 30:
            score -= 0.2
        return max(0.3, round(score, 2))
