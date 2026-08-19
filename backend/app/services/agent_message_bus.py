"""
AgentOS Phase 5 — Structured Multi-Agent Message Bus.

Enables secure, structured, task-scoped communication between agents:
- Pydantic validated AgentMessage models
- Correlation ID tracking
- In-memory dispatch and EventService audit trail
- Prevents unvalidated inter-agent communications
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from backend.app.models.multi_agent import AgentMessage, AgentType
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.message_bus")


class AgentMessageBus:
    """Task-scoped structured message bus for multi-agent coordination."""

    # In-memory storage: task_id -> list of AgentMessage
    _messages: Dict[str, List[AgentMessage]] = defaultdict(list)

    @classmethod
    def send(cls, message: AgentMessage) -> str:
        """
        Send a validated message to the target recipient.
        Records an append-only event to the audit trail.
        """
        if not message.message_id:
            message.message_id = f"msg-{uuid.uuid4().hex[:8]}"

        cls._messages[message.task_id].append(message)
        logger.info(
            "Agent message sent [%s -> %s] (task: %s, type: %s)",
            message.sender_agent.value,
            message.recipient_agent.value,
            message.task_id,
            message.message_type,
        )

        EventService.record_event(
            task_id=message.task_id,
            event_type="AGENT_MESSAGE_SENT",
            payload={
                "message_id": message.message_id,
                "sender": message.sender_agent.value,
                "recipient": message.recipient_agent.value,
                "message_type": message.message_type,
                "correlation_id": message.correlation_id,
            },
        )
        return message.message_id

    @classmethod
    def broadcast(cls, task_id: str, sender: AgentType, message_type: str, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> List[str]:
        """Broadcast a message from one agent to all other active agent types."""
        message_ids = []
        for agent_type in AgentType:
            if agent_type == sender:
                continue
            msg = AgentMessage(
                message_id=f"msg-{uuid.uuid4().hex[:8]}",
                task_id=task_id,
                sender_agent=sender,
                recipient_agent=agent_type,
                message_type=message_type,
                payload=payload,
                correlation_id=correlation_id,
            )
            cls.send(msg)
            message_ids.append(msg.message_id)
        return message_ids

    @classmethod
    def receive(cls, task_id: str, recipient: AgentType, unread_only: bool = False) -> List[AgentMessage]:
        """Retrieve messages addressed to a specific agent within a task."""
        all_msgs = cls._messages.get(task_id, [])
        matching = [m for m in all_msgs if m.recipient_agent == recipient]
        for m in matching:
            EventService.record_event(
                task_id=task_id,
                event_type="AGENT_MESSAGE_RECEIVED",
                payload={"message_id": m.message_id, "recipient": recipient.value},
            )
        return matching

    @classmethod
    def get_history(cls, task_id: str) -> List[AgentMessage]:
        """Retrieve full chronological communication history for a task."""
        return list(cls._messages.get(task_id, []))

    @classmethod
    def clear(cls, task_id: Optional[str] = None) -> None:
        """Clear message history (used primarily in test suites)."""
        if task_id:
            cls._messages.pop(task_id, None)
        else:
            cls._messages.clear()
