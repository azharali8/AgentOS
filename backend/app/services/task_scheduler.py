"""
AgentOS Phase 15 — Intelligent Task Scheduler.

Matches queued tasks to available healthy workers based on:
- Priority (CRITICAL > HIGH > NORMAL > LOW)
- Required capabilities vs worker advertised capabilities
- Worker capacity (active_tasks < max_tasks)
- Non-DRAINING / Non-OFFLINE / Non-UNHEALTHY status
- Atomic lease acquisition with incrementing fencing tokens
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple

from backend.app.db.database import get_db_session
from backend.app.db.models import QueueEntryModel, WorkerModel
from backend.app.services.database_health import with_db_retry
from backend.app.services.event_service import EventService
from backend.app.services.task_lease import TaskLeaseService
from backend.app.services.task_queue import QueueStatus, TaskQueue
from backend.app.services.worker_manager import WorkerStatus

logger = logging.getLogger("agentos.task_scheduler")


class TaskScheduler:
    """Intelligent, deterministic scheduler matching tasks to workers."""

    @classmethod
    @with_db_retry(max_retries=3)
    def find_eligible_worker(cls, required_capabilities: List[str]) -> Optional[WorkerModel]:
        """
        Find a healthy worker with spare capacity that matches all required capabilities.
        """
        req_set = set(required_capabilities or [])
        with get_db_session() as session:
            candidates = (
                session.query(WorkerModel)
                .filter(
                    WorkerModel.status.in_([WorkerStatus.READY, WorkerStatus.BUSY]),
                    WorkerModel.active_tasks < WorkerModel.max_tasks,
                )
                .all()
            )

            # Filter candidates by capability match and pick least loaded
            eligible = []
            for w in candidates:
                w_caps = set(w.capabilities or [])
                if not req_set or req_set.issubset(w_caps):
                    spare_capacity = w.max_tasks - w.active_tasks
                    eligible.append((spare_capacity, w))

            if not eligible:
                return None

            # Sort by highest spare capacity first
            eligible.sort(key=lambda item: item[0], reverse=True)
            chosen = eligible[0][1]
            return chosen.worker_id



    @classmethod
    def schedule_next(cls, scheduler_id: Optional[str] = None) -> Optional[Tuple[str, str, int]]:
        """
        Attempt to schedule and dispatch the highest-priority eligible task.
        Guarded by a distributed lock to prevent duplicate concurrent dispatch.
        Returns (task_id, worker_id, fencing_token) if scheduled, else None.
        """
        from backend.app.services.distributed_lock import DistributedLock
        s_id = scheduler_id or "scheduler-default"
        lock_token = DistributedLock.acquire("agentos:scheduler:dispatch", s_id, ttl_seconds=10)

        try:
            with get_db_session() as session:
                # 1. Fetch highest priority queued items and extract fields
                queued_rows = (
                    session.query(QueueEntryModel)
                    .filter(QueueEntryModel.status.in_([QueueStatus.QUEUED, QueueStatus.RECOVERY_REQUIRED]))
                    .order_by(QueueEntryModel.priority.asc(), QueueEntryModel.enqueued_at.asc())
                    .all()
                )

                if not queued_rows:
                    return None

                queued_items = [
                    {
                        "task_id": r.task_id,
                        "required_capabilities": list(r.required_capabilities or []),
                        "priority": r.priority,
                    }
                    for r in queued_rows
                ]

            # 2. Iterate through queued items and find a suitable worker
            for item in queued_items:
                worker_id = cls.find_eligible_worker(item["required_capabilities"])
                if worker_id:
                    task_id = item["task_id"]

                    # 3. Acquire lease atomically
                    try:
                        lease = TaskLeaseService.acquire_lease(task_id, worker_id)
                        fencing_token = lease.fencing_token

                        # 4. Increment worker active tasks
                        with get_db_session() as w_session:
                            w = w_session.query(WorkerModel).filter_by(worker_id=worker_id).first()
                            if w:
                                w.active_tasks += 1
                                if w.active_tasks >= w.max_tasks:
                                    w.status = WorkerStatus.BUSY
                                w_session.commit()

                        # 5. Mark task queue entry DISPATCHED
                        TaskQueue.update_status(task_id, QueueStatus.DISPATCHED, worker_id=worker_id, fencing_token=fencing_token)

                        EventService.record_event(
                            task_id=task_id,
                            event_type="TASK_DISPATCHED",
                            payload={
                                "worker_id": worker_id,
                                "fencing_token": fencing_token,
                                "priority": item["priority"],
                            },
                        )
                        return (task_id, worker_id, fencing_token)
                    except Exception as exc:
                        logger.warning("Failed to schedule task %s on worker %s: %s", task_id, worker_id, exc)
                        continue

            return None
        finally:
            if lock_token:
                DistributedLock.release("agentos:scheduler:dispatch", lock_token)


    @classmethod
    def schedule_all(cls, max_cycles: int = 10) -> List[Tuple[str, str, int]]:
        """Run scheduling loop until no more tasks can be dispatched or max_cycles reached."""
        dispatched = []
        for _ in range(max_cycles):
            res = cls.schedule_next()
            if not res:
                break
            dispatched.append(res)
        return dispatched

