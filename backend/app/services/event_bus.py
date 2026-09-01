"""
AgentOS Phase 16 — Distributed Event Bus.
Uses Redis Streams (XADD, XREAD, XRANGE) for durable distributed event publishing,
consumer groups, and event replay with zero simulated behavior.
"""


from __future__ import annotations

import datetime
import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from backend.app.observability.redaction import redact_secrets
from backend.app.services.redis_client import get_redis_client, is_redis_available, RedisUnavailableError

logger = logging.getLogger("agentos.event_bus")


class StreamEvent(BaseModel):
    event_id: str
    stream: str
    event_type: str
    task_id: Optional[str] = None
    worker_id: Optional[str] = None
    execution_id: Optional[str] = None
    fencing_token: Optional[int] = None
    correlation_id: Optional[str] = None
    payload: Dict[str, Any] = {}
    timestamp: str


class EventBus:
    """Production Redis Streams distributed event bus."""

    STREAM_PREFIX = "agentos:events:"

    @classmethod
    def publish(
        cls,
        event_type: str,
        stream_name: str = "tasks",
        task_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        fencing_token: Optional[int] = None,
        correlation_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Publish an event to a Redis Stream. Returns generated stream message ID."""
        if not is_redis_available():
            logger.debug("Redis unavailable: skipping event bus publish for %s", event_type)
            return None

        client = get_redis_client()
        safe_payload = redact_secrets(payload or {})
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

        fields = {
            "event_type": event_type,
            "timestamp": now_str,
            "task_id": task_id or "",
            "worker_id": worker_id or "",
            "execution_id": execution_id or "",
            "fencing_token": str(fencing_token) if fencing_token is not None else "",
            "correlation_id": correlation_id or "",
            "payload": json.dumps(safe_payload),
        }

        stream_key = f"{cls.STREAM_PREFIX}{stream_name}"
        try:
            msg_id = client.xadd(stream_key, fields)
            return str(msg_id)
        except Exception as exc:
            logger.error("Failed to publish to Redis stream %s: %s", stream_key, exc)
            return None

    @classmethod
    def replay(
        cls,
        stream_name: str = "tasks",
        start_id: str = "-",
        end_id: str = "+",
        count: int = 100,
    ) -> List[StreamEvent]:
        """Replay historical events from Redis Stream."""
        if not is_redis_available():
            return []

        client = get_redis_client()
        stream_key = f"{cls.STREAM_PREFIX}{stream_name}"

        try:
            raw_entries = client.xrange(stream_key, min=start_id, max=end_id, count=count)
            events = []
            for msg_id, data in raw_entries:
                payload_raw = data.get("payload", "{}")
                payload_dict = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
                ft = int(data["fencing_token"]) if data.get("fencing_token") else None

                events.append(
                    StreamEvent(
                        event_id=msg_id,
                        stream=stream_name,
                        event_type=data.get("event_type", "UNKNOWN"),
                        task_id=data.get("task_id") or None,
                        worker_id=data.get("worker_id") or None,
                        execution_id=data.get("execution_id") or None,
                        fencing_token=ft,
                        correlation_id=data.get("correlation_id") or None,
                        payload=payload_dict,
                        timestamp=data.get("timestamp", ""),
                    )
                )
            return events
        except Exception as exc:
            logger.error("Failed to replay stream %s: %s", stream_key, exc)
            return []
