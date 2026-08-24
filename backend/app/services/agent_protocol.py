"""
AgentOS Phase 13 — Structured Agent Communication Protocol.

Replaces informal string-based messaging with strongly typed, auditable Pydantic contracts:
- TaskAssignmentMessage
- DiagnosisReportMessage
- PatchProposalMessage
- TestReportMessage
- ReviewVerdictMessage
- SecurityFindingsMessage
- RecoveryRequestMessage
- CompletionReportMessage
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.app.models.engineering_workflow import (
    CodeChangesPayload,
    DiagnosisReport,
    ReplanningDecision,
    ReviewVerdictPayload,
    TestExecutionReport,
)
from backend.app.models.multi_agent import AgentType
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.agent_protocol")


class MessageType(str, Enum):
    TASK_ASSIGNMENT = "TASK_ASSIGNMENT"
    DIAGNOSIS_REPORT = "DIAGNOSIS_REPORT"
    PATCH_PROPOSAL = "PATCH_PROPOSAL"
    TEST_REPORT = "TEST_REPORT"
    REVIEW_VERDICT = "REVIEW_VERDICT"
    SECURITY_FINDINGS = "SECURITY_FINDINGS"
    RECOVERY_REQUEST = "RECOVERY_REQUEST"
    COMPLETION_REPORT = "COMPLETION_REPORT"


class ProtocolEnvelope(BaseModel):
    message_id: str
    task_id: str
    subtask_id: Optional[str] = None
    sender: str
    recipient: str
    message_type: MessageType
    payload: Dict[str, Any]
    correlation_id: Optional[str] = None
    timestamp: datetime


class AgentProtocol:
    """Strongly-typed inter-agent message validation and dispatching layer."""

    _message_history: Dict[str, List[ProtocolEnvelope]] = {}

    @classmethod
    def send(
        cls,
        task_id: str,
        sender: AgentType,
        recipient: AgentType,
        message_type: MessageType,
        payload: Dict[str, Any],
        subtask_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> ProtocolEnvelope:
        """Validate and dispatch typed message envelope."""
        envelope = ProtocolEnvelope(
            message_id=str(uuid.uuid4()),
            task_id=task_id,
            subtask_id=subtask_id,
            sender=sender.value if hasattr(sender, "value") else str(sender),
            recipient=recipient.value if hasattr(recipient, "value") else str(recipient),
            message_type=message_type,
            payload=payload,
            correlation_id=correlation_id,
            timestamp=datetime.now(timezone.utc),
        )

        if task_id not in cls._message_history:
            cls._message_history[task_id] = []
        cls._message_history[task_id].append(envelope)

        # Audit as structured event
        EventService.record_event(
            task_id=task_id,
            event_type="AGENT_PROTOCOL_MESSAGE",
            step_id=subtask_id,
            payload={
                "message_id": envelope.message_id,
                "sender": envelope.sender,
                "recipient": envelope.recipient,
                "message_type": envelope.message_type.value,
                "correlation_id": envelope.correlation_id,
            },
        )

        logger.info(
            "PROTOCOL MESSAGE: [%s -> %s] type=%s task=%s subtask=%s",
            envelope.sender, envelope.recipient, envelope.message_type.value, task_id, subtask_id
        )
        return envelope

    @classmethod
    def get_task_history(cls, task_id: str) -> List[ProtocolEnvelope]:
        """Fetch all inter-agent protocol messages for auditing."""
        return cls._message_history.get(task_id, [])
