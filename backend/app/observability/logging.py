"""
AgentOS Phase 6 — Structured JSON Logging Formatter.

Formats log records as structured JSON including timestamps, log levels,
correlation context, and automated secret scrubbing.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from backend.app.observability.context import get_correlation_context
from backend.app.observability.redaction import redact_secrets


class StructuredJsonFormatter(logging.Formatter):
    """Custom logging Formatter that outputs JSON lines with correlation context and secret redaction."""

    def format(self, record: logging.LogRecord) -> str:
        ctx = get_correlation_context()
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_secrets(record.getMessage()),
            "request_id": ctx.get("request_id"),
            "task_id": ctx.get("task_id"),
            "agent_id": ctx.get("agent_id"),
            "correlation_id": ctx.get("correlation_id"),
        }
        if record.exc_info:
            log_obj["exception"] = redact_secrets(self.formatException(record.exc_info))
        return json.dumps(log_obj)


def configure_logging(level: str = "INFO") -> None:
    """Setup root logger with StructuredJsonFormatter."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Replace existing handlers with structured formatter
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredJsonFormatter())
    root_logger.handlers = [handler]
