from typing import Any, Dict, Optional, List
import uuid

from backend.app.db.database import get_db_session
from backend.app.db.models import EventModel
from backend.app.db.repositories.event_repository import EventRepository
from backend.app.observability.redaction import redact_secrets

class EventService:
    @classmethod
    def record_event(
        cls,
        task_id: str,
        event_type: str,
        step_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        worker_id: Optional[str] = None,
        fencing_token: Optional[int] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        """Record an append-only event in the database and optionally stream to Redis EventBus."""
        event_id = str(uuid.uuid4())
        safe_payload = redact_secrets(payload or {})

        from backend.app.config.settings import settings
        event_backend = getattr(settings, "EVENT_BACKEND", "db")

        # 1. DB persistence
        if event_backend in ("db", "both", "sqlite", "redis"):
            with get_db_session() as session:
                repo = EventRepository(session)
                model = EventModel(
                    event_id=event_id,
                    task_id=task_id,
                    event_type=event_type,
                    step_id=step_id,
                    payload=safe_payload,
                )
                repo.create(model)

        # 2. Redis Streams streaming
        if event_backend in ("redis", "both"):
            try:
                from backend.app.services.event_bus import EventBus
                EventBus.publish(
                    event_type=event_type,
                    stream_name="tasks",
                    task_id=task_id,
                    worker_id=worker_id,
                    execution_id=step_id,
                    fencing_token=fencing_token,
                    correlation_id=correlation_id,
                    payload=safe_payload,
                )
            except Exception:
                pass


    @classmethod
    def list_events(cls, task_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        with get_db_session() as session:
            repo = EventRepository(session)
            models = repo.list_by_task(task_id, limit, offset)
            res = []
            for m in models:
                res.append({
                    "event_id": m.event_id,
                    "task_id": m.task_id,
                    "event_type": m.event_type,
                    "timestamp": m.timestamp,
                    "step_id": m.step_id,
                    "payload": redact_secrets(m.payload)
                })
            return res

    @classmethod
    def get_task_events(cls, task_id: str) -> List[Dict[str, Any]]:
        """Alias for list_events returning all events for a given task."""
        return cls.list_events(task_id, limit=500, offset=0)
