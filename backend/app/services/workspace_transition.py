"""Single-process coordination for the shared AgentOS workspace.

The engine still has one mutable ``WORKSPACE_ROOT``.  A task must therefore be
*admitted* while the same lock that protects a root transition is held.  The
admission is deliberately separate from a TaskModel's PENDING status: merely
creating a task must not pin the workspace forever, while a task handed to a
worker must be visible to a concurrent connect/disconnect immediately.
"""

from functools import wraps
from threading import RLock
from inspect import signature
from typing import Set
from datetime import datetime, timezone

from fastapi import HTTPException

workspace_transition_lock = RLock()
_admitted_task_ids: Set[str] = set()


def admit_workspace_task(task_id: str) -> None:
    """Reserve the shared workspace for a task before its worker is started.

    Callers must hold ``workspace_transition_lock``.  Keeping that contract
    explicit prevents a future admission path from recreating the original
    create-thread-versus-connect race.
    """
    _admitted_task_ids.add(task_id)


def release_workspace_task(task_id: str) -> None:
    """Release an in-process reservation after a terminal worker failure."""
    with workspace_transition_lock:
        _admitted_task_ids.discard(task_id)


def blocking_workspace_task_ids() -> list[str]:
    """Return tasks that can still use the process-global workspace.

    Historical PENDING rows are intentionally not blockers.  A PENDING row is
    a blocker only after this process has admitted it, or when the persistent
    queue/lease/execution records prove it can run.  Approval, pause and
    recovery states remain blockers because their checkpoint can be resumed
    against the currently selected root.
    """
    from backend.app.db.database import get_db_session
    from backend.app.db.models import ApprovalModel, ExecutionModel, QueueEntryModel, TaskLeaseModel, TaskModel
    from backend.app.models.task import TaskStatus

    blocking_statuses = {
        TaskStatus.PLANNING.value,
        TaskStatus.EXECUTING.value,
        TaskStatus.REVIEWING.value,
        TaskStatus.CANCELLING.value,
        TaskStatus.WAITING_APPROVAL.value,
        TaskStatus.PAUSED.value,
        TaskStatus.RECOVERY_REQUIRED.value,
    }
    queue_blocking = {"QUEUED", "DISPATCHED", "RUNNING", "PAUSED", "CANCELLING", "RECOVERY_REQUIRED"}
    terminal_statuses = [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]
    now = datetime.now(timezone.utc)
    with get_db_session() as db:
        ids = {row[0] for row in db.query(TaskModel.task_id).filter(TaskModel.status.in_(blocking_statuses)).all()}
        ids.update(row[0] for row in db.query(QueueEntryModel.task_id).join(TaskModel).filter(
            QueueEntryModel.status.in_(queue_blocking), ~TaskModel.status.in_(terminal_statuses)).all())
        for task_id, expiry in db.query(TaskLeaseModel.task_id, TaskLeaseModel.lease_expires_at).join(TaskModel).filter(
            TaskLeaseModel.status == "ACTIVE", ~TaskModel.status.in_(terminal_statuses)).all():
            expiry_utc = expiry.replace(tzinfo=timezone.utc) if expiry and expiry.tzinfo is None else expiry
            if expiry_utc and expiry_utc > now:
                ids.add(task_id)
        ids.update(row[0] for row in db.query(ExecutionModel.task_id).join(TaskModel).filter(
            ExecutionModel.status == "RUNNING", ~TaskModel.status.in_(terminal_statuses)).all())
        # An unresolved approval is a durable checkpoint even if a legacy
        # caller has left the task status stale.
        ids.update(row[0] for row in db.query(ApprovalModel.task_id).join(TaskModel).filter(
            ApprovalModel.status == "PENDING", ~TaskModel.status.in_(terminal_statuses)).all())
        terminal = {row[0] for row in db.query(TaskModel.task_id).filter(TaskModel.status.in_([
            *terminal_statuses,
        ])).all()}
    # A terminal task cannot retain an in-memory admission after a worker error.
    _admitted_task_ids.difference_update(terminal)
    ids.update(_admitted_task_ids - terminal)
    return sorted(ids)


def require_idle_workspace() -> None:
    if blocking_workspace_task_ids():
        raise HTTPException(409, "Finish or cancel active tasks and pending approvals before changing projects.")


def workspace_transition(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with workspace_transition_lock:
            return function(*args, **kwargs)
    wrapped.__signature__ = signature(function, eval_str=True)
    return wrapped
