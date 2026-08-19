"""
AgentOS Phase 7 - Adaptive Model Routing.

Selects a provider/model pair using task context, historical success, and
current budget constraints. Historical data remains advisory only.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from backend.app.config.settings import settings
from backend.app.intelligence.performance_store import PerformanceStore
from backend.app.observability.redaction import redact_secrets
from backend.app.services.event_service import EventService

_PROVIDER_MODELS: Dict[str, str] = {
    "mock": "mock",
    "ollama": settings.OLLAMA_MODEL,
    "openai": "gpt-4o-mini",
    "colab": "colab-default",
}

_PROVIDER_BASE_COST: Dict[str, float] = {
    "mock": 0.0,
    "ollama": 0.0015,
    "openai": 0.01,
    "colab": 0.004,
}

_PROVIDER_BASE_LATENCY: Dict[str, float] = {
    "mock": 5.0,
    "ollama": 300.0,
    "openai": 450.0,
    "colab": 250.0,
}


class ModelRoutingDecision(BaseModel):
    task_id: str
    task_category: str
    complexity: str
    provider: str
    model: str
    reason: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    estimated_cost: float = 0.0
    estimated_latency_ms: float = 0.0
    fallback_used: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ModelRouter:
    """Deterministic provider/model routing with bounded fallback behavior."""

    @classmethod
    def route(
        cls,
        task_id: str,
        task_category: str,
        complexity: str = "medium",
        token_budget: Optional[int] = None,
        provider_availability: Optional[Dict[str, bool]] = None,
        historical_success: Optional[Dict[str, float]] = None,
        failure_history: Optional[Dict[str, int]] = None,
    ) -> ModelRoutingDecision:
        configured_provider = settings.LLM_PROVIDER.lower()
        candidate_providers = [configured_provider, "ollama", "openai", "mock"]
        available_providers = []

        for provider in candidate_providers:
            if provider in available_providers:
                continue
            if provider_availability is None or provider_availability.get(provider, True):
                available_providers.append(provider)

        if not available_providers:
            available_providers = [configured_provider]

        def provider_score(provider: str) -> float:
            score = 0.5
            if provider == configured_provider:
                score += 0.15
            if complexity in ("complex", "critical") and provider == "openai":
                score += 0.2
            if complexity == "simple" and provider == "mock":
                score += 0.15
            if token_budget is not None and token_budget <= settings.TASK_TOKEN_LIMIT and provider == "mock":
                score += 0.1
            if task_category in ("bug_fix", "test_failure") and provider == "ollama":
                score += 0.1

            if historical_success:
                score += float(historical_success.get(provider, 0.0)) * 0.2
            if failure_history:
                score -= min(0.3, float(failure_history.get(provider, 0)) * 0.05)
            return score

        chosen_provider = max(available_providers, key=provider_score)
        fallback_used = chosen_provider != configured_provider
        model = _PROVIDER_MODELS.get(chosen_provider, settings.OLLAMA_MODEL)
        base_cost = _PROVIDER_BASE_COST.get(chosen_provider, 0.002)
        base_latency = _PROVIDER_BASE_LATENCY.get(chosen_provider, 250.0)

        complexity_multiplier = {
            "simple": 0.75,
            "medium": 1.0,
            "complex": 1.6,
            "critical": 2.0,
        }.get(complexity, 1.0)

        estimated_cost = round(base_cost * complexity_multiplier, 4)
        estimated_latency = round(base_latency * complexity_multiplier, 1)
        confidence = round(min(1.0, 0.55 + provider_score(chosen_provider) / 2), 3)
        reason = (
            f"Selected {chosen_provider}/{model} for {task_category} "
            f"at {complexity} complexity using configured heuristics."
        )

        decision = ModelRoutingDecision(
            task_id=task_id,
            task_category=task_category,
            complexity=complexity,
            provider=chosen_provider,
            model=model,
            reason=reason,
            confidence=confidence,
            estimated_cost=estimated_cost,
            estimated_latency_ms=estimated_latency,
            fallback_used=fallback_used,
            metadata=redact_secrets({
                "configured_provider": configured_provider,
                "available_providers": available_providers,
                "token_budget": token_budget,
            }),
        )

        PerformanceStore.save_routing_decision(task_id, decision.model_dump(mode="json"))
        EventService.record_event(task_id, "MODEL_ROUTED", payload=decision.model_dump(mode="json"))
        return decision
