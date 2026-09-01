"""
AgentOS Phase 15 — Worker Manager.

Manages:
- Worker registration & deregistration
- Worker heartbeats & health status (STARTING, READY, BUSY, DRAINING, UNHEALTHY, OFFLINE)
- Capability and capacity tracking
- Stale worker detection and recovery
"""

from __future__ import annotations

import datetime
import logging
import os
import socket
import uuid
from typing import Any, Dict, List, Optional, Set

from backend.app.db.database import get_db_session
from backend.app.db.models import TaskLeaseModel, WorkerModel
from backend.app.services.database_health import with_db_retry
from backend.app.services.event_service import EventService

logger = logging.getLogger("agentos.worker_manager")


class WorkerStatus:
    STARTING = "STARTING"
    READY = "READY"
    BUSY = "BUSY"
    DRAINING = "DRAINING"
    UNHEALTHY = "UNHEALTHY"
    OFFLINE = "OFFLINE"


class WorkerManager:
    """Central registry and health monitor for distributed workers."""

    HEARTBEAT_TIMEOUT_SECONDS = 30  # Worker considered UNHEALTHY after 30s without heartbeat
    OFFLINE_TIMEOUT_SECONDS = 90    # Worker considered OFFLINE after 90s without heartbeat

    @classmethod
    @with_db_retry(max_retries=3)
    def register_worker(
        cls,
        worker_id: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        max_tasks: int = 2,
        hostname: Optional[str] = None,
        process_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WorkerModel:
        """Register a worker process."""
        wid = worker_id or f"wkr-{uuid.uuid4().hex[:8]}"
        host = hostname or socket.gethostname()
        pid = process_id or os.getpid()
        caps = capabilities or ["CODING", "TESTING", "RESEARCH", "DEBUGGING"]
        meta = metadata or {}
        now = datetime.datetime.now(datetime.timezone.utc)

        with get_db_session() as session:
            existing = session.query(WorkerModel).filter_by(worker_id=wid).first()
            if existing:
                existing.hostname = host
                existing.process_id = pid
                existing.capabilities = caps
                existing.max_tasks = max_tasks
                existing.status = WorkerStatus.READY
                existing.last_heartbeat = now
                existing.worker_metadata = meta
                session.commit()
                session.refresh(existing)
                worker = existing
            else:
                worker = WorkerModel(
                    worker_id=wid,
                    hostname=host,
                    process_id=pid,
                    capabilities=caps,
                    active_tasks=0,
                    max_tasks=max_tasks,
                    status=WorkerStatus.READY,
                    last_heartbeat=now,
                    started_at=now,
                    worker_metadata=meta,
                )
                session.add(worker)
                session.commit()
                session.refresh(worker)

            EventService.record_event(
                task_id=f"sys-{wid}",
                event_type="WORKER_REGISTERED",
                payload={
                    "worker_id": wid,
                    "hostname": host,
                    "process_id": pid,
                    "capabilities": caps,
                    "max_tasks": max_tasks,
                },
            )
            return worker

    @classmethod
    @with_db_retry(max_retries=3)
    def heartbeat(cls, worker_id: str, active_tasks: Optional[int] = None) -> bool:
        """Process a periodic heartbeat from a worker."""
        now = datetime.datetime.now(datetime.timezone.utc)
        with get_db_session() as session:
            worker = session.query(WorkerModel).filter_by(worker_id=worker_id).first()
            if not worker:
                return False

            worker.last_heartbeat = now
            if active_tasks is not None:
                worker.active_tasks = active_tasks

            # If worker was unhealthy/starting and is heartbeating, restore status
            if worker.status in (WorkerStatus.UNHEALTHY, WorkerStatus.STARTING):
                worker.status = WorkerStatus.BUSY if worker.active_tasks >= worker.max_tasks else WorkerStatus.READY

            # Auto-transition between READY and BUSY based on active_tasks
            if worker.status not in (WorkerStatus.DRAINING, WorkerStatus.OFFLINE):
                if worker.active_tasks >= worker.max_tasks:
                    worker.status = WorkerStatus.BUSY
                else:
                    worker.status = WorkerStatus.READY

            session.commit()
            return True

    @classmethod
    @with_db_retry(max_retries=3)
    def drain_worker(cls, worker_id: str) -> bool:
        """Mark worker as DRAINING: accepts no new tasks, finishes existing."""
        with get_db_session() as session:
            worker = session.query(WorkerModel).filter_by(worker_id=worker_id).first()
            if not worker:
                return False
            worker.status = WorkerStatus.DRAINING
            session.commit()

            EventService.record_event(
                task_id=f"sys-{worker_id}",
                event_type="WORKER_DRAINING",
                payload={"worker_id": worker_id},
            )
            return True

    @classmethod
    @with_db_retry(max_retries=3)
    def deregister_worker(cls, worker_id: str) -> bool:
        """Gracefully mark worker as OFFLINE."""
        with get_db_session() as session:
            worker = session.query(WorkerModel).filter_by(worker_id=worker_id).first()
            if not worker:
                return False
            worker.status = WorkerStatus.OFFLINE
            worker.active_tasks = 0
            session.commit()
            return True

    @classmethod
    @with_db_retry(max_retries=3)
    def check_worker_health(cls) -> Dict[str, Any]:
        """
        Sweep all workers, mark dead ones UNHEALTHY/OFFLINE, and return summary.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        unhealthy_workers = []
        offline_workers = []

        with get_db_session() as session:
            workers = session.query(WorkerModel).all()
            for w in workers:
                if w.status == WorkerStatus.OFFLINE:
                    continue

                lh = w.last_heartbeat.replace(tzinfo=datetime.timezone.utc) if w.last_heartbeat.tzinfo is None else w.last_heartbeat
                diff = (now - lh).total_seconds()

                if diff > cls.OFFLINE_TIMEOUT_SECONDS:
                    w.status = WorkerStatus.OFFLINE
                    offline_workers.append(w.worker_id)
                elif diff > cls.HEARTBEAT_TIMEOUT_SECONDS:
                    w.status = WorkerStatus.UNHEALTHY
                    unhealthy_workers.append(w.worker_id)
                    EventService.record_event(
                        task_id=f"sys-{w.worker_id}",
                        event_type="WORKER_UNHEALTHY",
                        payload={"worker_id": w.worker_id, "seconds_since_heartbeat": diff},
                    )
            session.commit()

        return {
            "unhealthy_count": len(unhealthy_workers),
            "unhealthy_workers": unhealthy_workers,
            "offline_count": len(offline_workers),
            "offline_workers": offline_workers,
        }

    @classmethod
    @with_db_retry(max_retries=3)
    def list_workers(cls) -> List[Dict[str, Any]]:
        """List all registered workers."""
        with get_db_session() as session:
            workers = session.query(WorkerModel).all()
            return [
                {
                    "worker_id": w.worker_id,
                    "hostname": w.hostname,
                    "process_id": w.process_id,
                    "capabilities": w.capabilities,
                    "active_tasks": w.active_tasks,
                    "max_tasks": w.max_tasks,
                    "status": w.status,
                    "last_heartbeat": w.last_heartbeat.isoformat() if w.last_heartbeat else None,
                    "started_at": w.started_at.isoformat() if w.started_at else None,
                    "metadata": w.worker_metadata,
                }
                for w in workers
            ]

    @classmethod
    @with_db_retry(max_retries=3)
    def get_worker(cls, worker_id: str) -> Optional[Dict[str, Any]]:
        """Get details for a single worker."""
        with get_db_session() as session:
            w = session.query(WorkerModel).filter_by(worker_id=worker_id).first()
            if not w:
                return None
            return {
                "worker_id": w.worker_id,
                "hostname": w.hostname,
                "process_id": w.process_id,
                "capabilities": w.capabilities,
                "active_tasks": w.active_tasks,
                "max_tasks": w.max_tasks,
                "status": w.status,
                "last_heartbeat": w.last_heartbeat.isoformat() if w.last_heartbeat else None,
                "started_at": w.started_at.isoformat() if w.started_at else None,
                "metadata": w.worker_metadata,
            }

