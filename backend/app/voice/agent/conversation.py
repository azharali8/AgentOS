"""
AgentOS Voice Agent — Conversation State.

Lightweight, in-process, session-scoped conversation memory.
Used only for short multi-turn clarifications within a single voice session
(e.g., the agent asks for a project name and waits for the user's response).

This is NOT a persistent memory system. It does NOT replace the Supervisor
or duplicate task state. It is discarded when the session ends.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_DEFAULT_TTL_SECONDS = 300  # 5 minutes before conversation context expires


@dataclass
class ConversationTurn:
    """A single turn (user message or agent question) in the conversation."""
    role: str          # 'user' or 'agent'
    text: str
    timestamp: float = field(default_factory=time.time)


class ConversationState:
    """
    Short-term conversation state for a single voice session.

    Keeps track of:
    - The conversation history (recent turns)
    - Any pending question the agent has asked (awaiting user reply)
    - Partial intent context carried between turns
    - Active referenced project or task ID
    """

    def __init__(self, session_id: str = "default-session", ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self.session_id = session_id
        self.ttl_seconds = ttl_seconds
        self._turns: List[ConversationTurn] = []
        self._pending_question: Optional[str] = None
        self._pending_context: Dict[str, Any] = {}
        self._last_activity = time.time()
        self.active_task_id: Optional[str] = None
        self.active_project_path: Optional[str] = None

    def is_expired(self) -> bool:
        """Returns True if the conversation context has timed out."""
        return (time.time() - self._last_activity) > self.ttl_seconds

    def touch(self) -> None:
        """Update last activity timestamp to extend TTL."""
        self._last_activity = time.time()

    def add_user_turn(self, text: str) -> None:
        """Record a user utterance."""
        self._turns.append(ConversationTurn(role="user", text=text))
        self.touch()

    def add_agent_turn(self, text: str) -> None:
        """Record an agent response or question."""
        self._turns.append(ConversationTurn(role="agent", text=text))
        self.touch()

    def recent_turns(self, n: int = 6) -> List[ConversationTurn]:
        """Return the N most recent turns."""
        return self._turns[-n:]

    def set_pending_question(self, question: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Record that the Voice Agent has asked the user a clarifying question."""
        self._pending_question = question
        self._pending_context = context or {}
        self.touch()

    def has_pending_question(self) -> bool:
        """Returns True if the agent is waiting for a clarifying answer."""
        return self._pending_question is not None

    def consume_pending_question(self) -> tuple[Optional[str], Dict[str, Any]]:
        """
        Consume and return the pending question + context.
        Clears the pending state after retrieval.
        """
        q = self._pending_question
        ctx = dict(self._pending_context)
        self._pending_question = None
        self._pending_context = {}
        return q, ctx

    def clear(self) -> None:
        """Reset conversation state."""
        self._turns.clear()
        self._pending_question = None
        self._pending_context.clear()
        self.touch()

    def summary(self) -> str:
        """Human-readable summary of the conversation state."""
        lines = [f"[ConversationState session={self.session_id}]"]
        for t in self.recent_turns():
            lines.append(f"  {t.role.upper()}: {t.text[:80]}")
        if self._pending_question:
            lines.append(f"  [PENDING QUESTION]: {self._pending_question}")
        return "\n".join(lines)
