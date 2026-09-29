"""Verified Ollama pool. No generation polling, inferred balances, or local fallback."""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

import httpx

from backend.app.config.settings import settings
from backend.app.llm.base import BaseLLMProvider
from backend.app.llm.ollama import OllamaProvider

AUTO = "AGENTOS_AUTO"
logger = logging.getLogger("agentos.model_router")


class CloudPoolExhausted(RuntimeError):
    code = "CLOUD_POOL_EXHAUSTED"

    def __init__(self):
        super().__init__("CLOUD_POOL_EXHAUSTED: AgentOS cloud capacity is currently unavailable. Select a local model to continue or retry cloud later.")


def verification():
    """Account-specific verification is local configuration, never a shipped healthy list."""
    try:
        data = json.loads(Path(settings.MODEL_VERIFICATION_FILE).read_text(encoding="utf-8"))
        if data["endpoint"] != settings.OLLAMA_BASE_URL.rstrip("/") or time.time() - data["checked_at"] > 7 * 86400:
            return []
        return data["models"]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def provider_failure(exc):
    """Structured HTTP status first; body text only disambiguates provider quota messages."""
    cause = exc
    while cause is not None:
        if isinstance(cause, httpx.HTTPStatusError):
            response = cause.response
            status = response.status_code
            try:
                body = response.json()
                code = body.get("code", "")
                message = str(body.get("error", "")).lower()
            except (ValueError, AttributeError):
                code, message = "", ""
            quota = code in ("quota_exceeded", "insufficient_quota", "usage_limit_exceeded") or any(
                phrase in message for phrase in ("quota exceeded", "quota exhausted", "reached your usage limit", "reached your weekly", "allowance exhausted", "credits exhausted"))
            if status in (402, 429) and quota:
                return "QUOTA_EXHAUSTED", None
            if status == 429:
                try:
                    cooldown = max(1, min(86400, float(response.headers.get("Retry-After", "60"))))
                except ValueError:
                    cooldown = 60
                return "RATE_LIMITED", cooldown
            if status in (401, 402, 403, 404, 410):
                return "UNAVAILABLE", None
            if status >= 500:
                return "UNAVAILABLE", 60
            return None
        if isinstance(cause, (httpx.TimeoutException, httpx.TransportError)):
            return "UNAVAILABLE", 60
        cause = cause.__cause__
    return None


class CloudModelPool:
    def __init__(self, records=None, clock=time.time):
        self.records = records
        self.clock = clock
        self.lock = threading.RLock()
        self.health = {}

    def candidates(self):
        rows = self.records if self.records is not None else verification()
        rows = sorted((r for r in rows if r.get("cloud") and r.get("status") == "HEALTHY"), key=lambda r: r["latency_seconds"])
        with self.lock:
            return [r["model"] for r in rows if r["model"] not in self.health or
                    (self.health[r["model"]][1] is not None and self.clock() >= self.health[r["model"]][1])]

    def failed(self, model, classification):
        status, cooldown = classification
        with self.lock:
            self.health[model] = (status, self.clock() + cooldown if cooldown is not None else None)

    def succeeded(self, model):
        with self.lock:
            self.health.pop(model, None)


pool = CloudModelPool()


class AutoCloudProvider(BaseLLMProvider):
    model = AUTO

    def __init__(self, task_id=None, model_pool=None, provider_factory=OllamaProvider):
        self.task_id = task_id
        self.pool = model_pool or pool
        self.provider_factory = provider_factory
        self.current = None
        self.lock = threading.RLock()

    def record(self, event, **payload):
        logger.info("%s %s", event, payload)
        if self.task_id:
            from backend.app.services.event_service import EventService
            EventService.record_event(self.task_id, event, payload={"mode": "AUTO_CLOUD", **payload})

    def check_available(self):
        if not self.pool.candidates():
            raise CloudPoolExhausted()

    def generate(self, prompt, **kwargs):
        # A provider instance belongs to one task/node; concurrent sibling calls are serialized.
        with self.lock:
            candidates = self.pool.candidates()
            if self.current in candidates:
                candidates.remove(self.current)
                candidates.insert(0, self.current)
            previous, reason = None, None
            for model in candidates:
                if previous:
                    self.record("MODEL_FAILOVER", from_model=previous, to_model=model, reason=reason)
                self.record("MODEL_SELECTED", model=model)
                try:
                    result = self.provider_factory(model=model).generate(prompt, **kwargs)
                except Exception as exc:
                    classification = provider_failure(exc)
                    if classification is None:
                        raise  # Invalid output/code/tests are not provider availability failures.
                    self.pool.failed(model, classification)
                    previous, reason = model, classification[0]
                    self.record("MODEL_RATE_LIMITED" if reason == "RATE_LIMITED" else "MODEL_PROVIDER_FAILURE", model=model, reason=reason)
                    continue
                self.pool.succeeded(model)
                self.current = model
                return result
            self.record("MODEL_POOL_EXHAUSTED", reason="CLOUD_POOL_EXHAUSTED")
            raise CloudPoolExhausted()

    def generate_chat(self, messages, **kwargs):
        return self.generate("\n".join(f"{m['role']}: {m['content']}" for m in messages), **kwargs)
