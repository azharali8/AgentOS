"""
AgentOS Phase 8 - Learning Engine.

Analyzes retrieved execution experiences, detects actionable patterns, and
emits bounded advisory recommendations. The engine never executes tools or
modifies policy.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from statistics import mean
from typing import Any, Dict, List, Optional

from backend.app.config.settings import settings
from backend.app.evaluation.adaptive_metrics import AdaptiveMetricsCollector
from backend.app.intelligence.experience_models import ExecutionExperience, LearningAnalysis, LearningRecommendation, RetrievedExperience
from backend.app.intelligence.experience_retriever import ExperienceRetriever
from backend.app.intelligence.experience_store import ExperienceStore
from backend.app.intelligence.failure_patterns import FailurePattern, FailurePatternIntelligence
from backend.app.intelligence.learning_safety_gate import LearningSafetyGate
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.learning.engine")


_FALLBACK_FAILURE_STRATEGIES: Dict[str, str] = {
    "test_failure": "DEBUG_THEN_PATCH",
    "regression": "REVIEW_REQUIRED",
    "dependency_error": "RESEARCH_THEN_CODE",
    "security_block": "SECURITY_FIRST",
    "permission_denied": "SECURITY_FIRST",
    "timeout": "ITERATIVE_DEBUG",
    "agent_timeout": "ITERATIVE_DEBUG",
    "patch_conflict": "DEBUG_THEN_PATCH",
    "approval_rejected": "REVIEW_REQUIRED",
}


class LearningEngine:
    """Deterministic, advisory-only learning coordinator."""

    @classmethod
    def analyze(
        cls,
        *,
        task_id: str,
        task_type: str,
        task_complexity: str = "medium",
        instruction: Optional[str] = None,
        task_description_hash: Optional[str] = None,
        project_type: str = "python",
        framework: Optional[str] = None,
        selected_strategy: Optional[str] = None,
        selected_model: Optional[str] = None,
        selected_agents: Optional[List[str]] = None,
        failure_pattern: Optional[str] = None,
        failure_type: Optional[str] = None,
        success: Optional[bool] = None,
        plan_score: float = 0.0,
        resource_budget: Optional[Dict[str, Any]] = None,
        limit: int = 5,
        retrieved_experiences: Optional[List[RetrievedExperience]] = None,
        retrieval_summary: Optional[Dict[str, Any]] = None,
    ) -> LearningAnalysis:
        start = time.perf_counter()
        retrieved = retrieved_experiences or ExperienceRetriever.retrieve_relevant_experiences(
            task_id=task_id,
            task_type=task_type,
            task_complexity=task_complexity,
            instruction=instruction,
            task_description_hash=task_description_hash,
            project_type=project_type,
            framework=framework,
            selected_strategy=selected_strategy,
            selected_agents=selected_agents,
            failure_pattern=failure_pattern,
            failure_type=failure_type,
            success=success,
            limit=limit,
        )
        summary = retrieval_summary or ExperienceRetriever.summarize_retrieval(retrieved)
        recommendations = cls._build_recommendations(
            task_id=task_id,
            task_type=task_type,
            task_complexity=task_complexity,
            summary=summary,
            retrieved=retrieved,
            current_strategy=selected_strategy,
            current_model=selected_model,
            current_agents=selected_agents or [],
            failure_pattern=failure_pattern,
            failure_type=failure_type,
            plan_score=plan_score,
            resource_budget=resource_budget or {},
        )

        safe_recommendations = LearningSafetyGate.filter_recommendations(
            recommendations,
            task_context={
                "task_type": task_type,
                "task_complexity": task_complexity,
                "project_type": project_type,
                "framework": framework,
                "task_id": task_id,
            },
        )
        rejected_count = max(0, len(recommendations) - len(safe_recommendations))
        if recommendations:
            AdaptiveMetricsCollector.record_learning_recommendation(len(recommendations), average_confidence)
        for _ in range(rejected_count):
            AdaptiveMetricsCollector.record_learning_recommendation_rejected()
        average_confidence = mean([rec.confidence for rec in safe_recommendations]) if safe_recommendations else 0.0

        AdaptiveMetricsCollector.record_learning_latency(time.perf_counter() - start)
        EventService.record_event(
            task_id=task_id,
            event_type="LEARNING_ANALYZED",
            payload={
                "task_type": task_type,
                "retrieved": len(retrieved),
                "recommendations": len(safe_recommendations),
                "average_confidence": round(average_confidence, 3),
            },
        )

        return LearningAnalysis(
            task_id=task_id,
            task_type=task_type,
            retrieved_count=len(retrieved),
            success_rate=float(summary.get("success_rate", 0.0)),
            failure_rate=float(summary.get("failure_rate", 0.0)),
            average_confidence=round(average_confidence, 3),
            recommendations=safe_recommendations,
            retrieved_experiences=retrieved,
            strategy_recommendation=summary.get("recommended_strategy"),
            agent_recommendations=[rec for rec in safe_recommendations if rec.recommendation_type == "agent"],
            model_recommendations=[rec for rec in safe_recommendations if rec.recommendation_type == "model"],
            failure_recommendations=[rec for rec in safe_recommendations if rec.recommendation_type == "failure_recovery"],
            resource_recommendations=[rec for rec in safe_recommendations if rec.recommendation_type == "resource"],
            summary=cls._summarize(summary, safe_recommendations),
        )

    @classmethod
    def analyze_task(cls, **kwargs: Any) -> LearningAnalysis:
        return cls.analyze(**kwargs)

    @classmethod
    def record_experience(cls, experience: ExecutionExperience | Dict[str, Any]) -> ExecutionExperience:
        return ExperienceStore.record_experience(experience)

    @classmethod
    def update_experience(
        cls,
        task_id: str,
        updates: Dict[str, Any],
        *,
        create_if_missing: bool = True,
    ) -> Optional[ExecutionExperience]:
        return ExperienceStore.update_task_experience(task_id, updates, create_if_missing=create_if_missing)

    @classmethod
    def learn_from_task(
        cls,
        *,
        task_id: str,
        task_type: str,
        task_complexity: str = "medium",
        instruction: Optional[str] = None,
        task_description_hash: Optional[str] = None,
        project_type: str = "python",
        framework: Optional[str] = None,
        selected_strategy: Optional[str] = None,
        selected_model: Optional[str] = None,
        selected_agents: Optional[List[str]] = None,
        failure_pattern: Optional[str] = None,
        failure_type: Optional[str] = None,
        success: Optional[bool] = None,
        plan_score: float = 0.0,
        resource_budget: Optional[Dict[str, Any]] = None,
        limit: int = 5,
    ) -> LearningAnalysis:
        """Convenience alias for task-centric learning analysis."""
        return cls.analyze(
            task_id=task_id,
            task_type=task_type,
            task_complexity=task_complexity,
            instruction=instruction,
            task_description_hash=task_description_hash,
            project_type=project_type,
            framework=framework,
            selected_strategy=selected_strategy,
            selected_model=selected_model,
            selected_agents=selected_agents,
            failure_pattern=failure_pattern,
            failure_type=failure_type,
            success=success,
            plan_score=plan_score,
            resource_budget=resource_budget,
            limit=limit,
        )

    @classmethod
    def _build_recommendations(
        cls,
        *,
        task_id: str,
        task_type: str,
        task_complexity: str,
        summary: Dict[str, Any],
        retrieved: List[RetrievedExperience],
        current_strategy: Optional[str],
        current_model: Optional[str],
        current_agents: List[str],
        failure_pattern: Optional[str],
        failure_type: Optional[str],
        plan_score: float,
        resource_budget: Dict[str, Any],
    ) -> List[LearningRecommendation]:
        recommendations: List[LearningRecommendation] = []
        experience_ids = [item.experience.experience_id for item in retrieved]
        strategy_scores = summary.get("strategy_scores", {})
        agent_scores = summary.get("agent_scores", {})
        model_scores = summary.get("model_scores", {})
        resource_profile = summary.get("resource_profile", {})

        top_strategy = summary.get("recommended_strategy")
        top_model = summary.get("recommended_model")
        top_agents = summary.get("recommended_agents", [])
        failure_patterns = summary.get("failure_patterns", [])

        if top_strategy and top_strategy != current_strategy and len(retrieved) >= 1:
            recommendations.append(
                cls._make_recommendation(
                    recommendation_type="strategy",
                    recommendation=f"Prefer {top_strategy} for similar {task_type} tasks because historical evidence shows stronger outcomes.",
                    evidence_count=len(retrieved),
                    confidence=min(1.0, 0.5 + summary.get("average_confidence", 0.0) * 0.5),
                    expected_benefit="Improve future success rate and reduce avoidable replans.",
                    supporting_experience_ids=experience_ids,
                    target_strategy=top_strategy,
                )
            )
        elif top_strategy and current_strategy:
            recommendations.append(
                cls._make_recommendation(
                    recommendation_type="strategy",
                    recommendation=f"Continue using {current_strategy} for {task_type} tasks; it remains the best-supported choice in the current evidence set.",
                    evidence_count=len(retrieved),
                    confidence=min(1.0, 0.45 + summary.get("average_confidence", 0.0) * 0.45),
                    expected_benefit="Preserve a proven strategy when evidence remains consistent.",
                    supporting_experience_ids=experience_ids,
                    target_strategy=current_strategy,
                )
            )

        if top_agents:
            best_agent = top_agents[0]
            if best_agent not in current_agents:
                recommendations.append(
                    cls._make_recommendation(
                        recommendation_type="agent",
                        recommendation=f"Route similar tasks toward {best_agent} because it has the strongest historical signal for this task family.",
                        evidence_count=len(retrieved),
                        confidence=min(1.0, 0.45 + summary.get("average_confidence", 0.0) * 0.45),
                        expected_benefit="Increase specialization match and reduce recovery time.",
                        supporting_experience_ids=experience_ids,
                        target_agent=best_agent,
                    )
                )

        if top_model and top_model != current_model:
            recommendations.append(
                cls._make_recommendation(
                    recommendation_type="model",
                    recommendation=f"Prefer model {top_model} for this task family based on historical routing outcomes.",
                    evidence_count=len(retrieved),
                    confidence=min(1.0, 0.4 + summary.get("average_confidence", 0.0) * 0.4),
                    expected_benefit="Reduce routing fallback and improve consistency.",
                    supporting_experience_ids=experience_ids,
                    target_model=top_model,
                )
            )

        if resource_profile:
            recommended_budget = cls._build_budget_recommendation(resource_budget, resource_profile, task_complexity)
            if recommended_budget:
                recommendations.append(
                    cls._make_recommendation(
                        recommendation_type="resource",
                        recommendation="Adjust the execution budget slightly toward the historical profile while keeping all hard caps enforced.",
                        evidence_count=len(retrieved),
                        confidence=min(1.0, 0.35 + summary.get("average_confidence", 0.0) * 0.45),
                        expected_benefit="Align budget allocation with historical task costs.",
                        supporting_experience_ids=experience_ids,
                        resource_adjustment=recommended_budget,
                    )
                )

        recovery_strategy = cls._failure_recovery_strategy(failure_pattern, failure_type, failure_patterns)
        if recovery_strategy:
            note = cls._failure_recovery_note(failure_pattern or failure_type or "unknown", recovery_strategy)
            recommendations.append(
                cls._make_recommendation(
                    recommendation_type="failure_recovery",
                    recommendation=note,
                    evidence_count=len(retrieved),
                    confidence=min(1.0, 0.55 + summary.get("average_confidence", 0.0) * 0.35),
                    expected_benefit="Improve future failure recovery without weakening safeguards.",
                    supporting_experience_ids=experience_ids,
                    target_strategy=recovery_strategy,
                )
            )

        if plan_score >= 0.8 and current_strategy and current_strategy == top_strategy:
            recommendations.append(
                cls._make_recommendation(
                    recommendation_type="reinforcement",
                    recommendation=f"Keep the current plan structure. Historical evidence and plan quality both support {current_strategy}.",
                    evidence_count=len(retrieved),
                    confidence=min(1.0, 0.4 + summary.get("average_confidence", 0.0) * 0.4),
                    expected_benefit="Preserve an already high-confidence execution path.",
                    supporting_experience_ids=experience_ids,
                    target_strategy=current_strategy,
                )
            )

        # Deduplicate while keeping order and staying bounded.
        seen: set[tuple[str, str, Optional[str], Optional[str]]] = set()
        bounded: List[LearningRecommendation] = []
        for recommendation in recommendations:
            key = (
                recommendation.recommendation_type,
                recommendation.recommendation,
                recommendation.target_strategy,
                recommendation.target_agent,
            )
            if key in seen:
                continue
            seen.add(key)
            bounded.append(recommendation)
            if len(bounded) >= int(getattr(settings, "MAX_LEARNING_RECOMMENDATIONS", 10)):
                break

        return bounded

    @staticmethod
    def _make_recommendation(**kwargs: Any) -> LearningRecommendation:
        recommendation = LearningRecommendation(**kwargs)
        return recommendation

    @staticmethod
    def _build_budget_recommendation(resource_budget: Dict[str, Any], resource_profile: Dict[str, Any], task_complexity: str) -> Dict[str, Any]:
        if not resource_profile:
            return {}

        adjusted: Dict[str, Any] = {}
        avg_tokens = float(resource_profile.get("average_tokens", 0.0) or 0.0)
        avg_tool_calls = float(resource_profile.get("average_tool_calls", 0.0) or 0.0)
        avg_duration = float(resource_profile.get("average_duration_seconds", 0.0) or 0.0)

        if avg_tokens > 0:
            adjusted["max_tokens"] = min(settings.MAX_AGENT_TOKENS, max(1, int(avg_tokens * 1.25)))
        if avg_tool_calls > 0:
            adjusted["max_tool_calls"] = min(settings.MAX_AGENT_TOOL_CALLS, max(1, int(avg_tool_calls * 1.35)))
        if avg_duration > 0:
            adjusted["max_execution_time"] = min(settings.MAX_AGENT_RUNTIME, max(1, int(avg_duration * 1.5)))

        if not adjusted and resource_budget:
            adjusted = {
                key: value
                for key, value in resource_budget.items()
                if key in {"max_tokens", "max_tool_calls", "max_execution_time", "max_retries", "max_subtasks", "max_depth"}
            }
        return adjusted

    @staticmethod
    def _failure_recovery_strategy(
        failure_pattern: Optional[str],
        failure_type: Optional[str],
        failure_patterns: List[str],
    ) -> Optional[str]:
        candidates = [failure_pattern, failure_type] + list(failure_patterns)
        for candidate in candidates:
            if not candidate:
                continue
            normalized = str(candidate).lower()
            if normalized in _FALLBACK_FAILURE_STRATEGIES:
                return _FALLBACK_FAILURE_STRATEGIES[normalized]
            try:
                pattern = FailurePattern(normalized)
                resolved = FailurePatternIntelligence.get_resolutions(pattern)
                if resolved:
                    return str(resolved[0])
            except Exception:
                continue
        return None

    @staticmethod
    def _failure_recovery_note(failure_signal: str, strategy: str) -> str:
        return f"Historical {failure_signal} cases favor {strategy} as a bounded recovery path."

    @staticmethod
    def _summarize(summary: Dict[str, Any], recommendations: List[LearningRecommendation]) -> str:
        if not summary.get("experience_count"):
            return "No sufficient learning evidence yet."
        strategy = summary.get("recommended_strategy") or "unknown"
        agent = summary.get("recommended_agents", [])
        model = summary.get("recommended_model")
        confidence = summary.get("average_confidence", 0.0)
        return (
            f"Retrieved {summary.get('experience_count')} experiences. "
            f"Top strategy={strategy}, top agents={agent[:3]}, top model={model}. "
            f"Generated {len(recommendations)} bounded recommendation(s) at confidence {confidence:.3f}."
        )
