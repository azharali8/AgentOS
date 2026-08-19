"""
AgentOS Phase 8 - Experience Retrieval.

Retrieves bounded, ranked historical experiences for advisory learning. The
retriever always returns a top-K subset and treats all historical data as
untrusted evidence.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.config.settings import settings
from backend.app.evaluation.adaptive_metrics import AdaptiveMetricsCollector
from backend.app.intelligence.experience_models import ExecutionExperience, RetrievedExperience, hash_task_description
from backend.app.intelligence.experience_store import ExperienceStore
from backend.app.memory.experience import ExperienceMemory
from backend.app.models.experience import ExperienceRecord, FailureCategory
from backend.app.observability.redaction import redact_secrets


def _legacy_to_experience(record: ExperienceRecord) -> ExecutionExperience:
    summary = record.instruction_summary or "legacy experience"
    task_hash = hash_task_description(summary or record.task_id)
    failure_pattern = record.failure_category.value if record.failure_category else None
    return ExecutionExperience(
        experience_id=record.experience_id,
        task_id=record.task_id,
        task_type=record.task_type or record.task_classification or "general",
        task_description_hash=task_hash,
        task_complexity=record.task_classification or "medium",
        project_type=record.project_type or "python",
        framework=record.learning_metadata.get("framework") if hasattr(record, "learning_metadata") else None,
        selected_strategy=record.strategy or "DIRECT",
        selected_model=record.learning_metadata.get("selected_model") if hasattr(record, "learning_metadata") else None,
        selected_agents=[str(agent) for agent in record.agents_used],
        decomposition_summary=[str(item) for item in record.decomposition_summary],
        plan_score=float(record.learning_metadata.get("plan_score", 0.0)) if hasattr(record, "learning_metadata") else 0.0,
        resource_budget=dict(record.learning_metadata.get("resource_budget", {})) if hasattr(record, "learning_metadata") else {},
        execution_duration=float(record.duration_seconds),
        tool_call_count=int(record.learning_metadata.get("tool_call_count", len(record.tools_used))) if hasattr(record, "learning_metadata") else len(record.tools_used),
        token_usage=int(record.token_usage),
        success=bool(record.success),
        failure_type=record.failure_category.value if record.failure_category else None,
        failure_pattern=failure_pattern,
        regression_detected=bool(record.regression_detected),
        approval_required=bool(record.approval_required),
        approval_outcome=record.learning_metadata.get("approval_outcome") if hasattr(record, "learning_metadata") else None,
        security_events=[str(item) for item in record.learning_metadata.get("security_events", [])] if hasattr(record, "learning_metadata") else [],
        evaluation_score=float(record.learning_metadata.get("evaluation_score", 0.0)) if hasattr(record, "learning_metadata") else 0.0,
        final_outcome=record.outcome or ("SUCCESS" if record.success else "FAILED"),
        evidence_ids=[str(item) for item in record.learning_metadata.get("evidence_ids", [])] if hasattr(record, "learning_metadata") else [],
        task_summary=summary[:500],
        learning_metadata=redact_secrets({
            "legacy": True,
            "iterations": record.iterations,
            "retries": record.retries,
            "estimated_cost": record.estimated_cost,
            "lessons": record.lessons_learned,
        }),
        timestamp=record.created_at,
    )


class ExperienceRetriever:
    """Deterministic evidence retriever for long-term learning."""

    @classmethod
    def retrieve_relevant_experiences(
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
        selected_agents: Optional[List[str]] = None,
        failure_pattern: Optional[str] = None,
        failure_type: Optional[str] = None,
        success: Optional[bool] = None,
        limit: int = 5,
    ) -> List[RetrievedExperience]:
        """Return a bounded, relevance-ranked subset of historical experience."""
        bounded_limit = max(1, min(limit, int(getattr(settings, "MAX_LEARNING_RETRIEVAL_TOP_K", 5))))
        candidates = cls._load_candidates(bounded_limit * 4)

        query_hash = task_description_hash
        if not query_hash and instruction:
            query_hash = hash_task_description(redact_secrets(instruction))

        ranked: List[RetrievedExperience] = []
        for experience in candidates:
            relevance, matched = cls._score_experience(
                experience,
                task_type=task_type,
                task_complexity=task_complexity,
                project_type=project_type,
                framework=framework,
                selected_strategy=selected_strategy,
                selected_agents=selected_agents or [],
                failure_pattern=failure_pattern,
                failure_type=failure_type,
                query_hash=query_hash,
                success=success,
            )
            if relevance <= 0.0:
                continue

            confidence = cls._confidence_from_score(relevance, experience)
            ranked.append(
                RetrievedExperience(
                    experience=experience,
                    relevance_score=round(min(1.0, relevance), 3),
                    confidence=confidence,
                    matched_signals=matched,
                    rationale=cls._rationale(matched, experience),
                )
            )

        ranked.sort(key=lambda item: (item.relevance_score, item.confidence, item.experience.timestamp), reverse=True)
        AdaptiveMetricsCollector.record_experience_retrieved()
        return ranked[:bounded_limit]

    @classmethod
    def summarize_retrieval(cls, retrieved: List[RetrievedExperience]) -> Dict[str, Any]:
        if not retrieved:
            return {
                "experience_count": 0,
                "success_rate": 0.0,
                "failure_rate": 0.0,
                "average_confidence": 0.0,
                "recommended_strategy": None,
                "recommended_model": None,
                "recommended_agents": [],
                "failure_patterns": [],
                "strategy_scores": {},
                "agent_scores": {},
                "model_scores": {},
                "resource_profile": {},
            }

        experiences = [item.experience for item in retrieved]
        weighted_total = sum(max(item.relevance_score, 0.01) for item in retrieved)

        def _weighted_counter(values: List[str]) -> Dict[str, float]:
            counter: Dict[str, float] = defaultdict(float)
            for item in retrieved:
                weight = max(item.relevance_score, 0.01)
                for value in values_for(item.experience, values):
                    counter[value] += weight * (1.0 if item.experience.success else 0.6)
            return dict(sorted(counter.items(), key=lambda kv: kv[1], reverse=True))

        strategy_scores = defaultdict(float)
        agent_scores = defaultdict(float)
        model_scores = defaultdict(float)
        provider_scores = defaultdict(float)
        failure_patterns = Counter()
        resource_tokens = 0.0
        resource_tool_calls = 0.0
        resource_duration = 0.0

        for item in retrieved:
            exp = item.experience
            weight = max(item.relevance_score, 0.01) * (1.0 if exp.success else 0.75)
            strategy_scores[exp.selected_strategy] += weight
            if exp.selected_model:
                model_scores[exp.selected_model] += weight
            provider = str(exp.learning_metadata.get("provider", "")).strip()
            if provider:
                provider_scores[provider] += weight
            for agent in exp.selected_agents:
                agent_scores[agent] += weight
            if exp.failure_pattern:
                failure_patterns[exp.failure_pattern] += 1
            resource_tokens += exp.token_usage * weight
            resource_tool_calls += exp.tool_call_count * weight
            resource_duration += exp.execution_duration * weight

        recommended_strategy = max(strategy_scores, key=strategy_scores.get) if strategy_scores else None
        recommended_model = max(model_scores, key=model_scores.get) if model_scores else None
        recommended_agents = [agent for agent, _ in sorted(agent_scores.items(), key=lambda kv: kv[1], reverse=True)[:3]]
        success_rate = sum(1.0 for exp in experiences if exp.success) / len(experiences)
        confidence = sum(item.confidence for item in retrieved) / len(retrieved)

        resource_profile = {
            "average_tokens": round(resource_tokens / max(1.0, weighted_total), 2),
            "average_tool_calls": round(resource_tool_calls / max(1.0, weighted_total), 2),
            "average_duration_seconds": round(resource_duration / max(1.0, weighted_total), 3),
        }

        return {
            "experience_count": len(retrieved),
            "success_rate": round(success_rate, 3),
            "failure_rate": round(1.0 - success_rate, 3),
            "average_confidence": round(confidence, 3),
            "recommended_strategy": recommended_strategy,
            "recommended_model": recommended_model,
            "recommended_agents": recommended_agents,
            "failure_patterns": [name for name, _ in failure_patterns.most_common()],
            "failure_pattern_counts": dict(failure_patterns),
            "strategy_scores": dict(sorted(strategy_scores.items(), key=lambda kv: kv[1], reverse=True)),
            "agent_scores": dict(sorted(agent_scores.items(), key=lambda kv: kv[1], reverse=True)),
            "model_scores": dict(sorted(model_scores.items(), key=lambda kv: kv[1], reverse=True)),
            "provider_scores": dict(sorted(provider_scores.items(), key=lambda kv: kv[1], reverse=True)),
            "resource_profile": resource_profile,
        }

    @classmethod
    def summarize_strategy_preferences(cls, retrieved: List[RetrievedExperience]) -> Dict[str, float]:
        summary = cls.summarize_retrieval(retrieved)
        return {str(key): float(value) for key, value in summary.get("strategy_scores", {}).items()}

    @classmethod
    def summarize_agent_preferences(cls, retrieved: List[RetrievedExperience]) -> Dict[str, float]:
        summary = cls.summarize_retrieval(retrieved)
        return {str(key): float(value) for key, value in summary.get("agent_scores", {}).items()}

    @classmethod
    def summarize_model_preferences(cls, retrieved: List[RetrievedExperience]) -> Dict[str, float]:
        summary = cls.summarize_retrieval(retrieved)
        return {str(key): float(value) for key, value in summary.get("model_scores", {}).items()}

    @classmethod
    def summarize_failure_patterns(cls, retrieved: List[RetrievedExperience]) -> Dict[str, int]:
        counter: Counter[str] = Counter()
        for item in retrieved:
            if item.experience.failure_pattern:
                counter[item.experience.failure_pattern] += 1
        return dict(counter)

    @classmethod
    def summarize_resource_profile(cls, retrieved: List[RetrievedExperience]) -> Dict[str, Any]:
        return cls.summarize_retrieval(retrieved).get("resource_profile", {})

    @classmethod
    def _load_candidates(cls, limit: int) -> List[ExecutionExperience]:
        current = ExperienceStore.list_experiences(limit=limit)
        legacy = [_legacy_to_experience(record) for record in ExperienceMemory.list_all(limit=limit)]

        by_id: Dict[str, ExecutionExperience] = {exp.experience_id: exp for exp in current}
        for exp in legacy:
            by_id.setdefault(exp.experience_id, exp)
        # Preserve recency from the persistent store when available.
        return sorted(by_id.values(), key=lambda exp: exp.timestamp, reverse=True)

    @staticmethod
    def _score_experience(
        experience: ExecutionExperience,
        *,
        task_type: str,
        task_complexity: str,
        project_type: str,
        framework: Optional[str],
        selected_strategy: Optional[str],
        selected_agents: List[str],
        failure_pattern: Optional[str],
        failure_type: Optional[str],
        query_hash: Optional[str],
        success: Optional[bool],
    ) -> tuple[float, List[str]]:
        matched: List[str] = []
        score = 0.0

        if experience.task_type == task_type:
            score += 0.26
            matched.append("task_type")
        if experience.task_complexity == task_complexity:
            score += 0.14
            matched.append("complexity")
        if experience.project_type == project_type:
            score += 0.1
            matched.append("project_type")
        if framework and experience.framework == framework:
            score += 0.08
            matched.append("framework")
        if selected_strategy and experience.selected_strategy == selected_strategy:
            score += 0.14
            matched.append("strategy")
        if query_hash and experience.task_description_hash == query_hash:
            score += 0.18
            matched.append("description_hash")
        if success is not None and experience.success == success:
            score += 0.08
            matched.append("success_match")
        if failure_pattern and experience.failure_pattern == failure_pattern:
            score += 0.14
            matched.append("failure_pattern")
        if failure_type and experience.failure_type == failure_type:
            score += 0.1
            matched.append("failure_type")

        if selected_agents:
            overlap = len(set(selected_agents) & set(experience.selected_agents))
            if overlap:
                score += min(0.14, overlap / max(1, len(selected_agents)) * 0.14)
                matched.append("agent_overlap")

        age_seconds = max(0.0, (datetime.now(timezone.utc) - experience.timestamp).total_seconds())
        recency = 1.0 / (1.0 + (age_seconds / (7 * 24 * 3600)))
        score += recency * 0.14
        score += max(0.0, min(0.08, experience.evaluation_score * 0.08))
        if experience.success:
            score += 0.04
        if experience.regression_detected:
            score += 0.02

        return min(1.0, score), matched

    @staticmethod
    def _confidence_from_score(score: float, experience: ExecutionExperience) -> float:
        base = 0.3 + (score * 0.65)
        if experience.success:
            base += 0.03
        return max(0.0, min(1.0, round(base, 3)))

    @staticmethod
    def _rationale(matched: List[str], experience: ExecutionExperience) -> str:
        if not matched:
            return "Recency-only advisory evidence."
        return f"Matched signals: {', '.join(matched[:5])}"


def values_for(experience: ExecutionExperience, keys: List[str]) -> List[str]:
    """Compatibility helper retained for deterministic summary generation."""
    values: List[str] = []
    for key in keys:
        if key == "selected_strategy":
            values.append(experience.selected_strategy)
        elif key == "selected_model" and experience.selected_model:
            values.append(experience.selected_model)
        elif key == "project_type":
            values.append(experience.project_type)
    return values
