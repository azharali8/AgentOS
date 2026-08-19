"""
AgentOS Phase 6 — LLM Usage & Cost Tracking Service.

Tracks tokens, latencies, provider/model distribution, and estimates financial costs.
Enforces:
- TASK_TOKEN_LIMIT
- AGENT_TOKEN_LIMIT
- GLOBAL_DAILY_TOKEN_LIMIT
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.app.config.settings import settings
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.llm_usage")

# Estimated cost per 1K tokens ($) by model
_MODEL_COST_PER_1K: Dict[str, float] = {
    "llama3": 0.0002,
    "llama3.1": 0.0003,
    "gpt-4o": 0.005,
    "gpt-4o-mini": 0.00015,
    "claude-3-5-sonnet": 0.003,
    "default": 0.0002,
}


class LLMUsageRecord(BaseModel):
    task_id: str
    agent_id: str = "supervisor"
    provider: str = "ollama"
    model: str = "llama3"
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    estimated_cost: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LLMUsageService:
    """Central tracker for LLM token usage and financial cost estimation."""

    _records: List[LLMUsageRecord] = []
    _daily_token_count: int = 0

    @classmethod
    def estimate_cost(cls, model: str, total_tokens: int) -> float:
        """Calculate estimated cost based on token count and model pricing."""
        cost_per_1k = _MODEL_COST_PER_1K.get(model.lower(), _MODEL_COST_PER_1K["default"])
        return round((total_tokens / 1000.0) * cost_per_1k, 6)

    @classmethod
    def record_usage(
        cls,
        task_id: str,
        agent_id: str = "supervisor",
        provider: str = "ollama",
        model: str = "llama3",
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: float = 0.0,
    ) -> LLMUsageRecord:
        """Record usage, check budgets, and emit audit event."""
        total = input_tokens + output_tokens
        cost = cls.estimate_cost(model, total)

        # Budget enforcement
        cls._daily_token_count += total
        if cls._daily_token_count > settings.GLOBAL_DAILY_TOKEN_LIMIT:
            EventService.record_event(task_id, "BUDGET_EXCEEDED", payload={"type": "global_daily", "limit": settings.GLOBAL_DAILY_TOKEN_LIMIT})
            raise RuntimeError(f"Global daily token limit exceeded: {cls._daily_token_count} > {settings.GLOBAL_DAILY_TOKEN_LIMIT}")

        task_usage = cls.get_task_tokens(task_id) + total
        if task_usage > settings.TASK_TOKEN_LIMIT:
            EventService.record_event(task_id, "BUDGET_EXCEEDED", payload={"type": "task", "limit": settings.TASK_TOKEN_LIMIT})
            raise RuntimeError(f"Task token limit exceeded: {task_usage} > {settings.TASK_TOKEN_LIMIT}")

        record = LLMUsageRecord(
            task_id=task_id,
            agent_id=agent_id,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total,
            latency_ms=latency_ms,
            estimated_cost=cost,
        )
        cls._records.append(record)
        return record

    @classmethod
    def get_task_tokens(cls, task_id: str) -> int:
        return sum(r.total_tokens for r in cls._records if r.task_id == task_id)

    @classmethod
    def get_task_usage(cls, task_id: str) -> Dict[str, Any]:
        task_records = [r for r in cls._records if r.task_id == task_id]
        total_tokens = sum(r.total_tokens for r in task_records)
        total_cost = sum(r.estimated_cost for r in task_records)
        return {
            "task_id": task_id,
            "total_tokens": total_tokens,
            "estimated_cost_usd": round(total_cost, 6),
            "invocations_count": len(task_records),
            "records": [r.model_dump() for r in task_records],
        }

    @classmethod
    def get_summary(cls) -> Dict[str, Any]:
        total_tokens = sum(r.total_tokens for r in cls._records)
        total_cost = sum(r.estimated_cost for r in cls._records)
        return {
            "total_tokens_used": total_tokens,
            "total_estimated_cost_usd": round(total_cost, 6),
            "total_invocations": len(cls._records),
            "daily_tokens": cls._daily_token_count,
        }

    @classmethod
    def reset(cls) -> None:
        cls._records.clear()
        cls._daily_token_count = 0
