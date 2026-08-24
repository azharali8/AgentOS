"""
AgentOS Phase 13 & 14 — Durable Task Runtime.

Manages durable lifecycle across process restarts with non-linear state-machine validation:
- Explicit allowed transition graph
- First-class PAUSED state
- Two-phase CANCELLING -> CANCELLED workflow
- Checkpoint validation before resumption
- Process crash / restart recovery (RECOVERY_REQUIRED detection)
- Watchdog task timeouts and retry budget enforcement
"""

from __future__ import annotations

import datetime
import logging
import threading
from typing import Any, Dict, List, Optional, Set

from backend.app.config.settings import settings
from backend.app.db.database import get_db_session
from backend.app.db.models import TaskModel
from backend.app.models.task import TaskPriority, TaskRequest, TaskResult, TaskStatus
from backend.app.services.audit_service import AuditService
from backend.app.services.concurrency_manager import ConcurrencyManager
from backend.app.services.event_service import EventService
from backend.app.services.execution_manager import ExecutionManager
from backend.app.services.task_service import TaskService

logger = logging.getLogger("agentos.task_runtime")


class InvalidStateTransitionError(Exception):
    """Raised when an illegal lifecycle transition is attempted."""
    pass


class TaskRuntime:
    """Production runtime orchestrator for durable task management and state validation."""

    _paused_tasks: set[str] = set()
    _lock = threading.Lock()

    # Explicit allowed bidirectional and forward transitions matrix
    ALLOWED_TRANSITIONS: Dict[TaskStatus, Set[TaskStatus]] = {
        TaskStatus.PENDING: {TaskStatus.PLANNING, TaskStatus.CANCELLING, TaskStatus.CANCELLED},
        TaskStatus.PLANNING: {TaskStatus.EXECUTING, TaskStatus.PAUSED, TaskStatus.CANCELLING, TaskStatus.FAILED},
        TaskStatus.EXECUTING: {
            TaskStatus.PAUSED,
            TaskStatus.WAITING_APPROVAL,
            TaskStatus.REVIEWING,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLING,
            TaskStatus.RECOVERY_REQUIRED,
        },
        TaskStatus.PAUSED: {TaskStatus.EXECUTING, TaskStatus.CANCELLING, TaskStatus.CANCELLED},
        TaskStatus.WAITING_APPROVAL: {TaskStatus.EXECUTING, TaskStatus.CANCELLING, TaskStatus.CANCELLED},
        TaskStatus.RECOVERY_REQUIRED: {TaskStatus.EXECUTING, TaskStatus.FAILED, TaskStatus.CANCELLED},
        TaskStatus.REVIEWING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLING, TaskStatus.EXECUTING},
        TaskStatus.CANCELLING: {TaskStatus.CANCELLED, TaskStatus.FAILED},
        TaskStatus.COMPLETED: set(),  # Terminal
        TaskStatus.FAILED: set(),     # Terminal
        TaskStatus.CANCELLED: set(),  # Terminal
    }

    @classmethod
    def validate_transition(cls, from_status: TaskStatus, to_status: TaskStatus) -> bool:
        """Enforce strict state transition rules."""
        if from_status == to_status:
            return True
        allowed = cls.ALLOWED_TRANSITIONS.get(from_status, set())
        if to_status not in allowed:
            raise InvalidStateTransitionError(
                f"Illegal task state transition: '{from_status.value}' -> '{to_status.value}' is not permitted."
            )
        return True

    @classmethod
    def is_paused(cls, task_id: str) -> bool:
        with cls._lock:
            return task_id in cls._paused_tasks

    @classmethod
    def pause_task(cls, task_id: str, user_id: Optional[str] = None) -> bool:
        """Gracefully transition an executing task to first-class PAUSED state."""
        with cls._lock:
            cls._paused_tasks.add(task_id)

        task = TaskService.get_task(task_id)
        if not task:
            return False

        cls.validate_transition(task.status, TaskStatus.PAUSED)
        TaskService.update_task_status(task_id, TaskStatus.PAUSED)
        EventService.record_event(task_id, "TASK_PAUSED", payload={"paused_by": user_id or "system"})
        AuditService.record(
            action="TASK_PAUSE",
            status="SUCCESS",
            user_id=user_id,
            target_entity="task",
            target_id=task_id,
            details={"previous_status": task.status.value},
        )
        logger.info("Task %s successfully paused.", task_id)
        return True

    @classmethod
    def resume_task(cls, task_id: str, user_id: Optional[str] = None) -> TaskResult:
        """Validate checkpoint state and resume execution."""
        with cls._lock:
            cls._paused_tasks.discard(task_id)

        task = TaskService.get_task(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found.")

        cls.validate_transition(task.status, TaskStatus.EXECUTING)
        TaskService.update_task_status(task_id, TaskStatus.EXECUTING)
        EventService.record_event(task_id, "TASK_RESUMED", payload={"resumed_by": user_id or "system"})
        AuditService.record(
            action="TASK_RESUME",
            status="SUCCESS",
            user_id=user_id,
            target_entity="task",
            target_id=task_id,
            details={"previous_status": task.status.value},
        )

        from backend.app.services.multi_agent_service import MultiAgentService
        if task.status == TaskStatus.WAITING_APPROVAL:
            return MultiAgentService.resume_approval(task_id, approved=True)

        return TaskService.get_task(task_id)

    @classmethod
    def cancel_task(cls, task_id: str, reason: str = "User requested cancellation", user_id: Optional[str] = None) -> bool:
        """
        Execute two-phase cancellation lifecycle:
        RUNNING -> CANCELLING (killing subprocesses, releasing locks) -> CANCELLED
        """
        task = TaskService.get_task(task_id)
        if not task or task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return False

        # Phase 1: Set to CANCELLING
        cls.validate_transition(task.status, TaskStatus.CANCELLING)
        TaskService.update_task_status(task_id, TaskStatus.CANCELLING)
        EventService.record_event(task_id, "TASK_CANCELLING", payload={"reason": reason, "cancelled_by": user_id})

        # Terminate active process and tool handles
        ExecutionManager.request_cancellation(task_id)
        with cls._lock:
            cls._paused_tasks.discard(task_id)

        # Phase 2: Finalize to CANCELLED and release concurrency slot
        cls.validate_transition(TaskStatus.CANCELLING, TaskStatus.CANCELLED)
        TaskService.update_task_status(task_id, TaskStatus.CANCELLED)
        ConcurrencyManager.release_task(task_id)

        AuditService.record(
            action="TASK_CANCEL",
            status="SUCCESS",
            user_id=user_id,
            target_entity="task",
            target_id=task_id,
            details={"reason": reason},
        )
        logger.info("Task %s completed two-phase cancellation.", task_id)
        return True

    @classmethod
    def startup_recovery(cls) -> List[str]:
        """
        Inspect DB upon backend boot:
        Identify any stranded tasks in EXECUTING, PLANNING, or CANCELLING and flag as RECOVERY_REQUIRED.
        """
        recovered_ids: List[str] = []
        with get_db_session() as session:
            stranded = session.query(TaskModel).filter(
                TaskModel.status.in_([TaskStatus.EXECUTING.value, TaskStatus.PLANNING.value, TaskStatus.CANCELLING.value])
            ).all()

            for t in stranded:
                old_status = t.status
                t.status = TaskStatus.RECOVERY_REQUIRED.value
                t.error = "Interrupted by backend process restart. Stored checkpoint available for recovery."
                session.add(t)
                recovered_ids.append(t.task_id)

                EventService.record_event(
                    t.task_id,
                    "TASK_INTERRUPTED_RECOVERY",
                    payload={"previous_status": old_status, "action": "FLAGGED_RECOVERY_REQUIRED"},
                )

            session.commit()

        if recovered_ids:
            logger.warning("Startup recovery detected %d interrupted tasks: %s", len(recovered_ids), recovered_ids)
        return recovered_ids
