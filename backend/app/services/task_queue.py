"""
AgentOS Phase 15 — Distributed Task Queue.
"""


from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from backend.app.db.database import get_db_session
from backend.app.db.models import QueueEntryModel, TaskModel
from backend.app.models.task import TaskPriority, TaskStatus
from backend.app.services.database_health import with_db_retry
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.task_queue")


class QueueStatus:
    QUEUED = "QUEUED"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class QueueEntryDTO(BaseModel):
    queue_id: str
    task_id: str
    priority: int
    status: str
    required_capabilities: List[str]
    assigned_worker_id: Optional[str] = None
    current_fencing_token: int = 0
    enqueued_at: Optional[datetime.datetime] = None
    dispatched_at: Optional[datetime.datetime] = None
    retry_count: int = 0
    retry_limit: int = 3
    idempotency_key: Optional[str] = None
    queue_metadata: Dict[str, Any] = {}


def _to_entry_dto(m: QueueEntryModel) -> QueueEntryDTO:
    priority_map = {"CRITICAL": 0, "HIGH": 1, "NORMAL": 2, "LOW": 3, "critical": 0, "high": 1, "normal": 2, "low": 3}
    if isinstance(m.priority, str) and m.priority in priority_map:
        p_val = priority_map[m.priority]
    else:
        try:
            p_val = int(m.priority)
        except Exception:
            p_val = 2

    return QueueEntryDTO(
        queue_id=m.queue_id,
        task_id=m.task_id,
        priority=p_val,
        status=m.status,
        required_capabilities=m.required_capabilities or [],
        assigned_worker_id=m.assigned_worker_id,
        current_fencing_token=m.current_fencing_token,
        enqueued_at=m.enqueued_at,

        dispatched_at=m.dispatched_at,
        retry_count=m.retry_count,
        retry_limit=m.retry_limit,
        idempotency_key=m.idempotency_key,
        queue_metadata=m.queue_metadata or {},
    )


class TaskQueue:
    """Production persistent task queue with priority, idempotency, and anti-starvation."""

    STARVATION_THRESHOLD_SECONDS = 120

    @classmethod
    def _is_redis_mode(cls) -> bool:
        from backend.app.config.settings import settings
        from backend.app.services.redis_client import is_redis_available
        backend = getattr(settings, "QUEUE_BACKEND", "sqlite")
        return backend == "redis" and is_redis_available()

    @classmethod
    @with_db_retry(max_retries=3)
    def enqueue(
        cls,
        task_id: str,
        priority: int | TaskPriority | str = 2,
        required_capabilities: Optional[List[str]] = None,
        idempotency_key: Optional[str] = None,
        retry_limit: int = 3,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> QueueEntryDTO:
        """Enqueue a task for distributed execution idempotently."""
        if cls._is_redis_mode():
            from backend.app.services.redis_queue import RedisTaskQueue
            p_val = priority.value if hasattr(priority, "value") else priority
            p_int = 2
            priority_map = {"CRITICAL": 0, "HIGH": 1, "NORMAL": 2, "LOW": 3, "critical": 0, "high": 1, "normal": 2, "low": 3}
            if isinstance(p_val, str) and p_val in priority_map:
                p_int = priority_map[p_val]
            else:
                try:
                    p_int = int(p_val)
                except Exception:
                    p_int = 2
            r_dto = RedisTaskQueue.enqueue(
                task_id=task_id,
                priority=p_int,
                required_capabilities=required_capabilities,
                retry_limit=retry_limit,
                idempotency_key=idempotency_key,
                queue_metadata=metadata,
            )
            return QueueEntryDTO(
                queue_id=r_dto.queue_id,
                task_id=r_dto.task_id,
                priority=r_dto.priority,
                status=r_dto.status,
                required_capabilities=r_dto.required_capabilities,
                assigned_worker_id=r_dto.assigned_worker_id,
                current_fencing_token=r_dto.current_fencing_token,
                enqueued_at=r_dto.enqueued_at,
                dispatched_at=r_dto.dispatched_at,
                retry_count=r_dto.retry_count,
                retry_limit=r_dto.retry_limit,
                idempotency_key=r_dto.idempotency_key,
                queue_metadata=r_dto.queue_metadata,
            )

        if hasattr(priority, "value"):
            priority_val = priority.value
        else:
            priority_val = priority

        priority_map = {"CRITICAL": 0, "HIGH": 1, "NORMAL": 2, "LOW": 3, "critical": 0, "high": 1, "normal": 2, "low": 3}
        if isinstance(priority_val, str) and priority_val in priority_map:
            priority_int = priority_map[priority_val]
        else:
            try:
                priority_int = int(priority_val)
            except Exception:
                priority_int = 2

        caps = required_capabilities or ["CODING"]
        meta = metadata or {}

        with get_db_session() as session:
            if idempotency_key:
                existing = session.query(QueueEntryModel).filter_by(idempotency_key=idempotency_key).first()
                if existing:
                    return _to_entry_dto(existing)

            existing_task = session.query(QueueEntryModel).filter_by(task_id=task_id).first()
            if existing_task:
                return _to_entry_dto(existing_task)

            queue_id = f"q-{uuid.uuid4().hex[:12]}"
            entry = QueueEntryModel(
                queue_id=queue_id,
                task_id=task_id,
                priority=priority_int,
                status=QueueStatus.QUEUED,
                required_capabilities=caps,
                enqueued_at=datetime.datetime.now(datetime.timezone.utc),
                retry_limit=retry_limit,
                retry_count=0,
                idempotency_key=idempotency_key,
                queue_metadata=meta,
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)

            EventService.record_event(
                task_id=task_id,
                event_type="TASK_QUEUED",
                payload={
                    "queue_id": queue_id,
                    "priority": priority_int,
                    "required_capabilities": caps,
                    "idempotency_key": idempotency_key,
                },
            )
            return _to_entry_dto(entry)

    @classmethod
    @with_db_retry(max_retries=3)
    def dequeue(
        cls,
        worker_capabilities: Optional[List[str]] = None,
        assigned_worker_id: Optional[str] = None,
    ) -> Optional[QueueEntryDTO]:
        """Fetch the next eligible task from the queue considering priority, anti-starvation, and capability matching."""
        caps = set(worker_capabilities or [])
        now = datetime.datetime.now(datetime.timezone.utc)

        with get_db_session() as session:
            candidates = (
                session.query(QueueEntryModel)
                .filter(QueueEntryModel.status.in_([QueueStatus.QUEUED, QueueStatus.RECOVERY_REQUIRED]))
                .all()
            )

            if not candidates:
                return None

            eligible = []
            for c in candidates:
                req_caps = set(c.required_capabilities or [])
                if not req_caps or (caps and req_caps.issubset(caps)):
                    enq_utc = c.enqueued_at.replace(tzinfo=datetime.timezone.utc) if c.enqueued_at and c.enqueued_at.tzinfo is None else (c.enqueued_at or now)
                    age_seconds = (now - enq_utc).total_seconds()
                    starvation_boost = int(age_seconds // cls.STARVATION_THRESHOLD_SECONDS)
                    p_num = int(c.priority) if isinstance(c.priority, (int, float)) else 2
                    effective_priority = max(0, p_num - starvation_boost)
                    eligible.append((effective_priority, enq_utc, c.queue_id))

            if not eligible:
                return None

            eligible.sort(key=lambda item: (item[0], item[1]))
            chosen_qid = eligible[0][2]

            chosen_entry = session.query(QueueEntryModel).filter_by(queue_id=chosen_qid).first()
            if not chosen_entry:
                return None

            chosen_entry.status = QueueStatus.DISPATCHED
            chosen_entry.dispatched_at = now
            if assigned_worker_id:
                chosen_entry.assigned_worker_id = assigned_worker_id
            session.commit()
            session.refresh(chosen_entry)
            return _to_entry_dto(chosen_entry)

    @classmethod
    @with_db_retry(max_retries=3)
    def get_entry(cls, task_id: str) -> Optional[QueueEntryDTO]:
        """Get queue entry for a task."""
        with get_db_session() as session:
            entry = session.query(QueueEntryModel).filter_by(task_id=task_id).first()
            return _to_entry_dto(entry) if entry else None

    @classmethod
    @with_db_retry(max_retries=3)
    def update_status(
        cls,
        task_id: str,
        status: str,
        worker_id: Optional[str] = None,
        fencing_token: Optional[int] = None,
    ) -> bool:
        """Update queue status for a task."""
        with get_db_session() as session:
            entry = session.query(QueueEntryModel).filter_by(task_id=task_id).first()
            if not entry:
                return False
            entry.status = status
            if worker_id is not None:
                entry.assigned_worker_id = worker_id
            if fencing_token is not None:
                entry.current_fencing_token = fencing_token
            session.commit()
            return True

    @classmethod
    @with_db_retry(max_retries=3)
    def requeue(cls, task_id: str, reason: str = "Worker failure or lease expiration") -> bool:
        """Requeue a task for another worker to pick up, incrementing retry count."""
        with get_db_session() as session:
            entry = session.query(QueueEntryModel).filter_by(task_id=task_id).first()
            if not entry:
                return False

            entry.retry_count += 1
            if entry.retry_count > entry.retry_limit:
                entry.status = QueueStatus.FAILED
                session.commit()
                EventService.record_event(
                    task_id=task_id,
                    event_type="TASK_RETRY_LIMIT_EXCEEDED",
                    payload={"retry_count": entry.retry_count, "limit": entry.retry_limit, "reason": reason},
                )
                return False

            entry.status = QueueStatus.QUEUED
            entry.assigned_worker_id = None
            entry.dispatched_at = None
            session.commit()

            EventService.record_event(
                task_id=task_id,
                event_type="TASK_REQUEUED",
                payload={"retry_count": entry.retry_count, "reason": reason},
            )
            return True

    @classmethod
    @with_db_retry(max_retries=3)
    def cancel(cls, task_id: str) -> bool:
        """Cancel a queued task."""
        with get_db_session() as session:
            entry = session.query(QueueEntryModel).filter_by(task_id=task_id).first()
            if not entry:
                return False
            entry.status = QueueStatus.CANCELLED
            session.commit()
            return True

    @classmethod
    @with_db_retry(max_retries=3)
    def get_stats(cls) -> Dict[str, Any]:
        """Aggregate queue statistics."""
        with get_db_session() as session:
            entries = session.query(QueueEntryModel).all()
            status_counts: Dict[str, int] = {}
            priority_counts: Dict[str, int] = {}
            total = len(entries)

            for e in entries:
                status_counts[e.status] = status_counts.get(e.status, 0) + 1
                p_label = f"P{e.priority}"
                priority_counts[p_label] = priority_counts.get(p_label, 0) + 1

            return {
                "total_tasks": total,
                "queued": status_counts.get(QueueStatus.QUEUED, 0),
                "dispatched": status_counts.get(QueueStatus.DISPATCHED, 0),
                "running": status_counts.get(QueueStatus.RUNNING, 0),
                "completed": status_counts.get(QueueStatus.COMPLETED, 0),
                "failed": status_counts.get(QueueStatus.FAILED, 0),
                "cancelled": status_counts.get(QueueStatus.CANCELLED, 0),
                "by_status": status_counts,
                "by_priority": priority_counts,
            }

    @classmethod
    @with_db_retry(max_retries=3)
    def list_queue(cls, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """List queue entries with details."""
        with get_db_session() as session:
            entries = (
                session.query(QueueEntryModel)
                .order_by(QueueEntryModel.priority.asc(), QueueEntryModel.enqueued_at.asc())
                .limit(limit)
                .offset(offset)
                .all()
            )
            return [
                {
                    "queue_id": e.queue_id,
                    "task_id": e.task_id,
                    "priority": e.priority,
                    "status": e.status,
                    "required_capabilities": e.required_capabilities,
                    "assigned_worker_id": e.assigned_worker_id,
                    "current_fencing_token": e.current_fencing_token,
                    "enqueued_at": e.enqueued_at.isoformat() if e.enqueued_at else None,
                    "dispatched_at": e.dispatched_at.isoformat() if e.dispatched_at else None,
                    "retry_count": e.retry_count,
                }
                for e in entries
            ]
