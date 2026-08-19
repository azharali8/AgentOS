"""
AgentOS Phase 7 — Adaptive Intelligence Memory Layer.

Extends Phase 5 memory with controlled intelligence categories:
successful/failed strategies, agent specialization, project patterns,
recurring bugs, test patterns, architecture observations, benchmark results.

Includes TTL/retention, size limits, secret filtering, task/project isolation.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from enum import Enum
from typing import Any, Dict, List, Optional

from backend.app.config.settings import settings
from backend.app.memory.experience import ExperienceMemory
from backend.app.observability.redaction import redact_secrets
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.intelligence.memory")


class MemoryCategory(str, Enum):
    SUCCESSFUL_STRATEGY = "successful_strategy"
    FAILED_STRATEGY = "failed_strategy"
    AGENT_SPECIALIZATION = "agent_specialization"
    PROJECT_PATTERN = "project_pattern"
    RECURRING_BUG = "recurring_bug"
    TEST_PATTERN = "test_pattern"
    ARCHITECTURE = "architecture"
    BENCHMARK = "benchmark"


# Default TTL in seconds (7 days)
_DEFAULT_TTL = 7 * 24 * 3600


class IntelligenceMemory:
    """Controlled intelligence memory with isolation and retention."""

    _store: Dict[str, Dict[str, Any]] = {}
    _by_category: Dict[MemoryCategory, List[str]] = defaultdict(list)
    _by_task: Dict[str, List[str]] = defaultdict(list)
    _by_project: Dict[str, List[str]] = defaultdict(list)

    @classmethod
    def store(
        cls,
        category: MemoryCategory,
        key: str,
        value: Any,
        task_id: Optional[str] = None,
        project_id: str = "default",
        ttl_seconds: int = _DEFAULT_TTL,
    ) -> str:
        """Store an intelligence memory entry with secret filtering."""
        if len(cls._store) >= settings.MAX_MEMORY_ITEMS:
            cls._evict_oldest()

        memory_id = f"mem-{category.value}-{len(cls._store)}"
        entry = redact_secrets({
            "memory_id": memory_id,
            "category": category.value,
            "key": key,
            "value": value,
            "task_id": task_id,
            "project_id": project_id,
            "created_at": time.time(),
            "expires_at": time.time() + ttl_seconds,
        })

        cls._store[memory_id] = entry
        cls._by_category[category].append(memory_id)
        if task_id:
            cls._by_task[task_id].append(memory_id)
        cls._by_project[project_id].append(memory_id)

        EventService.record_event(
            task_id=task_id or "system",
            event_type="MEMORY_UPDATED",
            payload={"memory_id": memory_id, "category": category.value},
        )
        return memory_id

    @classmethod
    def retrieve(
        cls,
        category: MemoryCategory,
        task_id: Optional[str] = None,
        project_id: str = "default",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Retrieve memory entries with task/project isolation."""
        cls._purge_expired()
        results = []
        for mid in cls._by_category.get(category, []):
            entry = cls._store.get(mid)
            if not entry:
                continue
            # Task isolation: only return entries for this task or global (no task_id)
            if task_id and entry.get("task_id") and entry["task_id"] != task_id:
                continue
            # Project isolation
            if entry.get("project_id") != project_id:
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results

    @classmethod
    def get_successful_strategies(cls, task_type: str) -> List[str]:
        return ExperienceMemory.get_successful_strategies(task_type)

    @classmethod
    def _purge_expired(cls) -> None:
        now = time.time()
        expired = [mid for mid, entry in cls._store.items() if entry.get("expires_at", 0) < now]
        for mid in expired:
            cls._remove(mid)

    @classmethod
    def _evict_oldest(cls) -> None:
        if not cls._store:
            return
        oldest = min(cls._store.items(), key=lambda x: x[1].get("created_at", 0))
        cls._remove(oldest[0])

    @classmethod
    def _remove(cls, memory_id: str) -> None:
        entry = cls._store.pop(memory_id, None)
        if not entry:
            return
        cat = MemoryCategory(entry["category"]) if entry.get("category") else None
        if cat and memory_id in cls._by_category.get(cat, []):
            cls._by_category[cat].remove(memory_id)

    @classmethod
    def reset(cls) -> None:
        cls._store.clear()
        cls._by_category.clear()
        cls._by_task.clear()
        cls._by_project.clear()
