"""
AgentOS Phase 15 — Distributed Task Leasing.
"""


from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from backend.app.db.database import get_db_session
from backend.app.db.models import QueueEntryModel, TaskLeaseModel, TaskModel
from backend.app.services.database_health import with_db_retry
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.task_lease")


class LeaseStatus:
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    RELEASED = "RELEASED"
    REVOKED = "REVOKED"


class FencingTokenMismatchError(Exception):
    """Raised when a worker attempts an operation with a stale fencing token."""
    pass


class LeaseAcquisitionError(Exception):
    """Raised when a task lease cannot be acquired."""
    pass


class TaskLeaseDTO(BaseModel):
    lease_id: str
    task_id: str
    worker_id: str
    fencing_token: int
    lease_started_at: Optional[datetime.datetime] = None
    lease_expires_at: Optional[datetime.datetime] = None
    last_renewed_at: Optional[datetime.datetime] = None
    status: str
    renew_count: int = 0


def _to_lease_dto(m: TaskLeaseModel) -> TaskLeaseDTO:
    return TaskLeaseDTO(
        lease_id=m.lease_id,
        task_id=m.task_id,
        worker_id=m.worker_id,
        fencing_token=m.fencing_token,
        lease_started_at=m.lease_started_at,
        lease_expires_at=m.lease_expires_at,
        last_renewed_at=m.last_renewed_at,
        status=m.status,
        renew_count=m.renew_count,
    )


class TaskLeaseService:
    """Manages distributed task lease acquisition, renewal, and monotonic fencing tokens."""

    DEFAULT_LEASE_TTL_SECONDS = 30

    @classmethod
    @with_db_retry(max_retries=3)
    def acquire_lease(
        cls,
        task_id: str,
        worker_id: str,
        ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    ) -> TaskLeaseDTO:
        """Atomically acquire or re-acquire a lease for a task, assigning an incremented monotonic fencing token."""
        now = datetime.datetime.now(datetime.timezone.utc)
        expires_at = now + datetime.timedelta(seconds=ttl_seconds)

        with get_db_session() as session:
            existing = (
                session.query(TaskLeaseModel)
                .filter(TaskLeaseModel.task_id == task_id)
                .order_by(TaskLeaseModel.fencing_token.desc())
                .first()
            )

            next_fencing_token = 1
            if existing:
                exp_utc = existing.lease_expires_at.replace(tzinfo=datetime.timezone.utc) if existing.lease_expires_at.tzinfo is None else existing.lease_expires_at
                is_active = (existing.status == LeaseStatus.ACTIVE) and (exp_utc > now)

                if is_active and existing.worker_id != worker_id:
                    raise LeaseAcquisitionError(
                        f"Task '{task_id}' is already actively leased by worker '{existing.worker_id}' until {exp_utc.isoformat()}."
                    )

                if existing.status == LeaseStatus.ACTIVE:
                    existing.status = LeaseStatus.REVOKED

                next_fencing_token = existing.fencing_token + 1

            lease_id = f"lease-{uuid.uuid4().hex[:12]}"
            lease = TaskLeaseModel(
                lease_id=lease_id,
                task_id=task_id,
                worker_id=worker_id,
                fencing_token=next_fencing_token,
                lease_started_at=now,
                lease_expires_at=expires_at,
                last_renewed_at=now,
                status=LeaseStatus.ACTIVE,
                renew_count=0,
            )
            session.add(lease)

            queue_entry = session.query(QueueEntryModel).filter_by(task_id=task_id).first()
            if queue_entry:
                queue_entry.assigned_worker_id = worker_id
                queue_entry.current_fencing_token = next_fencing_token
                queue_entry.status = "RUNNING"

            session.commit()
            session.refresh(lease)

            EventService.record_event(
                task_id=task_id,
                event_type="TASK_LEASE_ACQUIRED",
                payload={
                    "lease_id": lease_id,
                    "worker_id": worker_id,
                    "fencing_token": next_fencing_token,
                    "expires_at": expires_at.isoformat(),
                },
            )
            return _to_lease_dto(lease)

    @classmethod
    @with_db_retry(max_retries=3)
    def renew_lease(
        cls,
        lease_id: str,
        worker_id: str,
        fencing_token: int,
        ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    ) -> TaskLeaseDTO:
        """Renew an active lease."""
        now = datetime.datetime.now(datetime.timezone.utc)
        expires_at = now + datetime.timedelta(seconds=ttl_seconds)

        with get_db_session() as session:
            lease = session.query(TaskLeaseModel).filter_by(lease_id=lease_id).first()
            if not lease:
                raise LeaseAcquisitionError(f"Lease '{lease_id}' not found.")

            if lease.worker_id != worker_id:
                raise LeaseAcquisitionError(f"Worker '{worker_id}' does not own lease '{lease_id}'.")

            if lease.fencing_token != fencing_token:
                raise FencingTokenMismatchError(
                    f"Fencing token mismatch: presented {fencing_token}, active {lease.fencing_token}."
                )

            if lease.status != LeaseStatus.ACTIVE:
                raise LeaseAcquisitionError(f"Cannot renew lease with status '{lease.status}'.")

            lease.lease_expires_at = expires_at
            lease.last_renewed_at = now
            lease.renew_count += 1
            session.commit()
            session.refresh(lease)
            return _to_lease_dto(lease)

    @classmethod
    @with_db_retry(max_retries=3)
    def release_lease(
        cls,
        lease_id: str,
        worker_id: str,
        fencing_token: int,
    ) -> bool:
        """Release a lease upon normal task completion."""
        with get_db_session() as session:
            lease = session.query(TaskLeaseModel).filter_by(lease_id=lease_id).first()
            if not lease:
                return False

            if lease.worker_id != worker_id or lease.fencing_token != fencing_token:
                return False

            lease.status = LeaseStatus.RELEASED
            session.commit()
            return True

    @classmethod
    @with_db_retry(max_retries=3)
    def verify_fencing_token(cls, task_id: str, fencing_token: int, worker_id: Optional[str] = None) -> bool:
        """Authoritative validation before any state or artifact mutation."""
        with get_db_session() as session:
            active_lease = (
                session.query(TaskLeaseModel)
                .filter(TaskLeaseModel.task_id == task_id, TaskLeaseModel.status == LeaseStatus.ACTIVE)
                .order_by(TaskLeaseModel.fencing_token.desc())
                .first()
            )
            if not active_lease:
                q = session.query(QueueEntryModel).filter_by(task_id=task_id).first()
                if q and q.current_fencing_token and q.current_fencing_token != fencing_token:
                    raise FencingTokenMismatchError(
                        f"Stale fencing token {fencing_token} for task {task_id} (current {q.current_fencing_token})"
                    )
                return True

            if active_lease.fencing_token != fencing_token:
                raise FencingTokenMismatchError(
                    f"Stale fencing token {fencing_token} for task {task_id} (authoritative is {active_lease.fencing_token})"
                )

            if worker_id and active_lease.worker_id != worker_id:
                raise FencingTokenMismatchError(
                    f"Worker {worker_id} is not the current lease holder ({active_lease.worker_id})"
                )

            return True

    @classmethod
    @with_db_retry(max_retries=3)
    def get_expired_leases(cls) -> List[TaskLeaseDTO]:
        """Find all active leases that have passed their expiration timestamp."""
        now = datetime.datetime.now(datetime.timezone.utc)
        with get_db_session() as session:
            leases = (
                session.query(TaskLeaseModel)
                .filter(TaskLeaseModel.status == LeaseStatus.ACTIVE)
                .all()
            )
            expired = []
            for l in leases:
                exp_utc = l.lease_expires_at.replace(tzinfo=datetime.timezone.utc) if l.lease_expires_at.tzinfo is None else l.lease_expires_at
                if exp_utc < now:
                    expired.append(_to_lease_dto(l))
            return expired

    @classmethod
    @with_db_retry(max_retries=3)
    def expire_lease(cls, lease_id: str) -> bool:
        """Mark an expired lease as EXPIRED and record audit event."""
        with get_db_session() as session:
            lease = session.query(TaskLeaseModel).filter_by(lease_id=lease_id).first()
            if not lease:
                return False
            lease.status = LeaseStatus.EXPIRED
            session.commit()

            EventService.record_event(
                task_id=lease.task_id,
                event_type="TASK_LEASE_EXPIRED",
                payload={"lease_id": lease.lease_id, "worker_id": lease.worker_id, "fencing_token": lease.fencing_token},
            )
            return True

    @classmethod
    @with_db_retry(max_retries=3)
    def get_active_lease(cls, task_id: str) -> Optional[Dict[str, Any]]:
        """Get currently active lease information for a task."""
        with get_db_session() as session:
            lease = (
                session.query(TaskLeaseModel)
                .filter(TaskLeaseModel.task_id == task_id, TaskLeaseModel.status == LeaseStatus.ACTIVE)
                .order_by(TaskLeaseModel.fencing_token.desc())
                .first()
            )
            if not lease:
                return None
            return {
                "lease_id": lease.lease_id,
                "task_id": lease.task_id,
                "worker_id": lease.worker_id,
                "fencing_token": lease.fencing_token,
                "lease_started_at": lease.lease_started_at.isoformat() if lease.lease_started_at else None,
                "lease_expires_at": lease.lease_expires_at.isoformat() if lease.lease_expires_at else None,
                "renew_count": lease.renew_count,
                "status": lease.status,
            }
