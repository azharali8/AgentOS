"""
AgentOS Phase 7 - Adaptive Metrics Collector.

Tracks adaptive intelligence counters without weakening the Phase 6 metrics
collector. The Phase 6 metrics remain authoritative for platform health.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Dict, Optional

from backend.app.evaluation.metrics import MetricsCollector


class AdaptiveMetricsCollector:
    """In-memory counters for adaptive runtime decisions."""

    _strategy_selections: int = 0
    _model_routes: int = 0
    _plan_scores: int = 0
    _evaluations: int = 0
    _failure_patterns: int = 0
    _adaptive_tasks_completed: int = 0
    _adaptive_replans: int = 0
    _experience_records: int = 0
    _experience_retrievals: int = 0
    _learning_recommendations: int = 0
    _learning_recommendations_applied: int = 0
    _learning_recommendations_successful: int = 0
    _learning_recommendations_rejected: int = 0
    _learning_loop_preventions: int = 0
    _learning_latency_total: float = 0.0
    _learning_latency_samples: int = 0
    _confidence_total: float = 0.0
    _confidence_samples: int = 0
    _events: Dict[str, int] = defaultdict(int)
    _start_time: float = time.time()

    @classmethod
    def record_strategy_selected(cls) -> None:
        cls._strategy_selections += 1
        cls._events["strategy_selected"] += 1

    @classmethod
    def record_model_routed(cls) -> None:
        cls._model_routes += 1
        cls._events["model_routed"] += 1

    @classmethod
    def record_plan_scored(cls) -> None:
        cls._plan_scores += 1
        cls._events["plan_scored"] += 1

    @classmethod
    def record_evaluation(cls) -> None:
        cls._evaluations += 1
        cls._events["evaluations"] += 1

    @classmethod
    def record_failure_pattern(cls) -> None:
        cls._failure_patterns += 1
        cls._events["failure_patterns"] += 1

    @classmethod
    def record_adaptive_task_completed(cls) -> None:
        cls._adaptive_tasks_completed += 1
        cls._events["adaptive_completed"] += 1

    @classmethod
    def record_replan(cls) -> None:
        cls._adaptive_replans += 1
        cls._events["replans"] += 1

    @classmethod
    def record_experience_recorded(cls) -> None:
        cls._experience_records += 1
        cls._events["experience_recorded"] += 1

    @classmethod
    def record_experience_retrieved(cls, count: int = 1) -> None:
        cls._experience_retrievals += max(1, count)
        cls._events["experience_retrieved"] += max(1, count)

    @classmethod
    def record_learning_recommendation(cls, count: int = 1, average_confidence: Optional[float] = None) -> None:
        increment = max(1, count)
        cls._learning_recommendations += increment
        cls._events["learning_recommendation"] += increment
        if average_confidence is not None:
            cls._confidence_total += max(0.0, float(average_confidence)) * increment
            cls._confidence_samples += increment

    @classmethod
    def record_learning_recommendation_applied(cls, success: bool = False) -> None:
        cls._learning_recommendations_applied += 1
        cls._events["learning_recommendation_applied"] += 1
        if success:
            cls._learning_recommendations_successful += 1
            cls._events["learning_recommendation_successful"] += 1

    @classmethod
    def record_learning_recommendation_rejected(cls) -> None:
        cls._learning_recommendations_rejected += 1
        cls._events["learning_recommendation_rejected"] += 1

    @classmethod
    def record_learning_loop_prevented(cls) -> None:
        cls._learning_loop_preventions += 1
        cls._events["learning_loop_prevented"] += 1

    @classmethod
    def record_learning_latency(cls, seconds: float) -> None:
        cls._learning_latency_total += max(0.0, float(seconds))
        cls._learning_latency_samples += 1

    @classmethod
    def get_metrics_snapshot(cls) -> Dict[str, Any]:
        base = MetricsCollector.get_metrics_snapshot()
        adaptive_total = (
            cls._strategy_selections
            + cls._model_routes
            + cls._plan_scores
            + cls._evaluations
            + cls._failure_patterns
            + cls._adaptive_tasks_completed
            + cls._adaptive_replans
            + cls._experience_records
            + cls._experience_retrievals
            + cls._learning_recommendations
            + cls._learning_recommendations_applied
            + cls._learning_recommendations_rejected
            + cls._learning_loop_preventions
        )
        recommendation_rate = cls._learning_recommendations_applied / max(1, cls._learning_recommendations)
        success_rate = cls._learning_recommendations_successful / max(1, cls._learning_recommendations_applied)
        false_rate = cls._learning_recommendations_rejected / max(1, cls._learning_recommendations)
        average_confidence = cls._confidence_total / max(1, cls._confidence_samples)
        average_latency = cls._learning_latency_total / max(1, cls._learning_latency_samples)
        return {
            **base,
            "adaptive": {
                "uptime_seconds": round(time.time() - cls._start_time, 2),
                "strategy_selections": cls._strategy_selections,
                "model_routes": cls._model_routes,
                "plan_scores": cls._plan_scores,
                "evaluations": cls._evaluations,
                "failure_patterns": cls._failure_patterns,
                "adaptive_tasks_completed": cls._adaptive_tasks_completed,
                "replans": cls._adaptive_replans,
                "events": dict(cls._events),
                "total_events": adaptive_total,
            },
            "learning": {
                "experience_count": cls._experience_records,
                "retrieval_count": cls._experience_retrievals,
                "recommendation_count": cls._learning_recommendations,
                "recommendation_acceptance_rate": round(recommendation_rate, 3),
                "recommendation_success_rate": round(success_rate, 3),
                "false_recommendation_rate": round(false_rate, 3),
                "average_confidence": round(average_confidence, 3),
                "learning_latency_seconds": round(average_latency, 4),
                "memory_growth": cls._experience_records,
                "loop_preventions": cls._learning_loop_preventions,
            },
        }

    @classmethod
    def reset(cls) -> None:
        cls._strategy_selections = 0
        cls._model_routes = 0
        cls._plan_scores = 0
        cls._evaluations = 0
        cls._failure_patterns = 0
        cls._adaptive_tasks_completed = 0
        cls._adaptive_replans = 0
        cls._experience_records = 0
        cls._experience_retrievals = 0
        cls._learning_recommendations = 0
        cls._learning_recommendations_applied = 0
        cls._learning_recommendations_successful = 0
        cls._learning_recommendations_rejected = 0
        cls._learning_loop_preventions = 0
        cls._learning_latency_total = 0.0
        cls._learning_latency_samples = 0
        cls._confidence_total = 0.0
        cls._confidence_samples = 0
        cls._events.clear()
        cls._start_time = time.time()
