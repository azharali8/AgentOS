"""
AgentOS Phase 5 — Multi-Tier Agent Memory System.

Includes:
1. Short-Term Execution Memory (ephemeral per subtask)
2. Conversation Memory (multi-turn dialog)
3. Semantic Memory (key-value / symbol index)
4. Project Memory (frameworks, build config, architecture)
5. AgentMemoryManager (central coordinator with secret scrubbing)
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from backend.app.config.settings import settings
from backend.app.models.multi_agent import AgentType
from backend.app.security.sensitive_files import is_sensitive_path
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.memory")


# Secret & credential regex patterns for automatic memory sanitization
_SECRET_REGEXES = [
    re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token|auth|bearer)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{8,})['\"]?"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    re.compile(r"sk-[a-zA-Z0-9]{32,}"),
]


def sanitize_memory_content(data: Any) -> Any:
    """Recursively scrub secrets and sensitive patterns from memory objects."""
    if isinstance(data, str):
        cleaned = data
        for pattern in _SECRET_REGEXES:
            cleaned = pattern.sub("[REDACTED_SECRET]", cleaned)
        return cleaned
    elif isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            # Check key names
            if any(term in k.lower() for term in ("password", "secret", "token", "key", "credential")):
                sanitized[k] = "[REDACTED_KEY]"
            else:
                sanitized[k] = sanitize_memory_content(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_memory_content(item) for item in data]
    return data


class ShortTermMemory:
    """Ephemeral scratchpad for an active subtask execution."""

    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._store[key] = sanitize_memory_content(value)

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def all(self) -> Dict[str, Any]:
        return dict(self._store)

    def clear(self) -> None:
        self._store.clear()


class ConversationMemory:
    """Tracks multi-turn agent/supervisor messages and explanations."""

    def __init__(self) -> None:
        self._turns: List[Dict[str, Any]] = []

    def add_turn(self, role: str, message: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self._turns.append({
            "role": role,
            "message": sanitize_memory_content(message),
            "metadata": sanitize_memory_content(metadata or {}),
        })

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._turns[-limit:]

    def clear(self) -> None:
        self._turns.clear()


class SemanticMemory:
    """Indexed key-concept and symbol mappings for fast lookup."""

    def __init__(self) -> None:
        self._concepts: Dict[str, Any] = {}

    def store_concept(self, concept_key: str, data: Any) -> None:
        self._concepts[concept_key] = sanitize_memory_content(data)

    def lookup_concept(self, concept_key: str) -> Optional[Any]:
        return self._concepts.get(concept_key)

    def all(self) -> Dict[str, Any]:
        return dict(self._concepts)

    def clear(self) -> None:
        self._concepts.clear()


class ProjectMemory:
    """Persistent metadata on workspace structure, tests, and architecture."""

    def __init__(self) -> None:
        self._meta: Dict[str, Any] = {}

    def record_metadata(self, key: str, value: Any) -> None:
        self._meta[key] = sanitize_memory_content(value)

    def get_metadata(self, key: str, default: Any = None) -> Any:
        return self._meta.get(key, default)

    def all(self) -> Dict[str, Any]:
        return dict(self._meta)

    def clear(self) -> None:
        self._meta.clear()


class AgentMemoryManager:
    """Central coordinator for multi-tier agent memory."""

    _short_term: Dict[str, ShortTermMemory] = defaultdict(ShortTermMemory)
    _conversation: Dict[str, ConversationMemory] = defaultdict(ConversationMemory)
    _semantic: Dict[str, SemanticMemory] = defaultdict(SemanticMemory)
    _project: Dict[str, ProjectMemory] = defaultdict(ProjectMemory)
    _audit_trail: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    @classmethod
    def get_short_term(cls, task_id: str) -> ShortTermMemory:
        return cls._short_term[task_id]

    @classmethod
    def get_conversation(cls, task_id: str) -> ConversationMemory:
        return cls._conversation[task_id]

    @classmethod
    def get_semantic(cls, task_id: str) -> SemanticMemory:
        return cls._semantic[task_id]

    @classmethod
    def get_project(cls, task_id: str) -> ProjectMemory:
        return cls._project[task_id]

    @classmethod
    def write(cls, task_id: str, category: str, key: str, value: Any, agent: AgentType = AgentType.SUPERVISOR) -> None:
        """Write to a designated memory category with secret filtering and audit logging."""
        cleaned_val = sanitize_memory_content(value)
        if category == "short_term":
            cls.get_short_term(task_id).set(key, cleaned_val)
        elif category == "semantic":
            cls.get_semantic(task_id).store_concept(key, cleaned_val)
        elif category == "project":
            cls.get_project(task_id).record_metadata(key, cleaned_val)
        elif category == "conversation":
            cls.get_conversation(task_id).add_turn(role=agent.value, message=str(cleaned_val))

        cls._audit_trail[task_id].append({
            "task_id": task_id,
            "category": category,
            "key": key,
            "value": cleaned_val,
            "agent": agent.value,
            "timestamp": time.time(),
        })

        EventService.record_event(
            task_id=task_id,
            event_type="AGENT_MEMORY_WRITTEN",
            payload={"category": category, "key": key, "agent": agent.value},
        )

    @classmethod
    def read(cls, task_id: str, category: str, key: Optional[str] = None, agent: AgentType = AgentType.SUPERVISOR) -> Any:
        """Read from memory category with audit logging."""
        res = None
        if category == "short_term":
            res = cls.get_short_term(task_id).get(key) if key else cls.get_short_term(task_id).all()
        elif category == "semantic":
            res = cls.get_semantic(task_id).lookup_concept(key) if key else cls.get_semantic(task_id).all()
        elif category == "project":
            res = cls.get_project(task_id).get_metadata(key) if key else cls.get_project(task_id).all()
        elif category == "conversation":
            res = cls.get_conversation(task_id).get_history()

        EventService.record_event(
            task_id=task_id,
            event_type="AGENT_MEMORY_READ",
            payload={"category": category, "key": key, "agent": agent.value},
        )
        return res

    @classmethod
    def retrieve_ranked(
        cls,
        task_id: str,
        category: str,
        query: Optional[str] = None,
        limit: int = 10,
        agent: AgentType = AgentType.SUPERVISOR,
    ) -> List[Dict[str, Any]]:
        """Return ranked memory entries using relevance and recency.

        The ranking is deterministic and bounded.  It uses the audit trail
        instead of exposing raw internal state so the existing memory layout
        remains unchanged.
        """
        query_text = (query or "").lower().strip()
        entries = [entry for entry in cls._audit_trail.get(task_id, []) if entry.get("category") == category]
        ranked: List[Dict[str, Any]] = []

        total = len(entries)
        for idx, entry in enumerate(entries):
            score = 0.0
            if entry.get("task_id") == task_id:
                score += 0.3
            if entry.get("agent") == agent.value:
                score += 0.1

            key_text = str(entry.get("key", "")).lower()
            value_text = str(entry.get("value", "")).lower()
            if query_text and (query_text in key_text or query_text in value_text):
                score += 0.4
            elif query_text:
                for term in query_text.split():
                    if term and (term in key_text or term in value_text):
                        score += 0.1

            # Prefer newer entries when relevance is similar.
            recency_boost = 0.0 if total == 0 else ((idx + 1) / total) * 0.2
            score += recency_boost

            ranked.append({
                "task_id": entry.get("task_id"),
                "category": entry.get("category"),
                "key": entry.get("key"),
                "value": entry.get("value"),
                "agent": entry.get("agent"),
                "timestamp": entry.get("timestamp"),
                "score": round(score, 3),
            })

        ranked.sort(key=lambda item: (item["score"], item["timestamp"]), reverse=True)
        EventService.record_event(
            task_id=task_id,
            event_type="ADAPTIVE_MEMORY_RETRIEVED",
            payload={"category": category, "query": query, "limit": limit, "agent": agent.value},
        )
        return ranked[:limit]

    @classmethod
    def clear(cls, task_id: Optional[str] = None) -> None:
        """Clear memory structures."""
        if task_id:
            cls._short_term.pop(task_id, None)
            cls._conversation.pop(task_id, None)
            cls._semantic.pop(task_id, None)
            cls._project.pop(task_id, None)
            cls._audit_trail.pop(task_id, None)
        else:
            cls._short_term.clear()
            cls._conversation.clear()
            cls._semantic.clear()
            cls._project.clear()
            cls._audit_trail.clear()
