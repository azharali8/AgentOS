"""
AgentOS Voice Agent — Confirmation Gate.

A safety gate for destructive or high-impact operations.
When a potentially dangerous intent is detected, the Voice Agent requires
explicit verbal confirmation before executing or routing the command.

Only used for clearly destructive operations or explicit approval requests.
Most benign engineering tasks (coding, testing, review) proceed directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("agentos.voice.confirmation")

_DESTRUCTIVE_KEYWORDS = [
    "delete",
    "remove all",
    "drop database",
    "wipe",
    "format",
    "destroy",
    "purge",
    "erase",
    "rm -rf",
]

_CONFIRMATION_PHRASES = [
    "yes",
    "confirm",
    "proceed",
    "go ahead",
    "do it",
    "affirmative",
    "yes, proceed",
    "yes, confirm",
    "yes, do it",
    "sure",
    "approved",
]

_REJECTION_PHRASES = [
    "no",
    "cancel",
    "stop",
    "abort",
    "never mind",
    "nope",
    "don't",
    "do not",
    "reject",
]


@dataclass
class ConfirmationRequest:
    """Represents a pending confirmation gate for a dangerous or sensitive operation."""
    operation_description: str
    original_transcript: str
    confirmed: bool = False


class ConfirmationGate:
    """
    Checks whether a transcript requires explicit user confirmation
    and validates confirmation responses.
    """

    @staticmethod
    def requires_confirmation(transcript: str) -> bool:
        """Return True if the transcript describes a potentially destructive operation."""
        lower = transcript.lower()
        return any(kw in lower for kw in _DESTRUCTIVE_KEYWORDS)

    @staticmethod
    def create_request(transcript: str, description: str) -> ConfirmationRequest:
        """Create a ConfirmationRequest for a pending destructive operation."""
        logger.info("Confirmation required for: %s", description[:80])
        return ConfirmationRequest(
            operation_description=description,
            original_transcript=transcript,
        )

    @staticmethod
    def is_confirmed(user_reply: str) -> bool:
        """Return True if the user's reply is a recognized confirmation phrase."""
        lower = user_reply.strip().lower()
        return any(lower.startswith(phrase) or lower == phrase for phrase in _CONFIRMATION_PHRASES)

    @staticmethod
    def is_rejected(user_reply: str) -> bool:
        """Return True if the user explicitly rejected the operation."""
        lower = user_reply.strip().lower()
        return any(lower.startswith(p) or lower == p for p in _REJECTION_PHRASES)
