"""
AgentOS Phase 2 — Recovery Unit Tests
"""

import pytest
import datetime
from backend.app.db.database import get_db_session
from backend.app.db.models import TaskModel, ApprovalModel, ExecutionModel, EventModel
from backend.app.models.task import TaskRequest, TaskStatus
from backend.app.services.recovery_service import RecoveryService
from backend.app.services.task_service import TaskService


@pytest.fixture(autouse=True)
def clean_db():
    with get_db_session() as session:
        session.query(EventModel).delete()
        session.query(ExecutionModel).delete()
        session.query(ApprovalModel).delete()
        session.query(TaskModel).delete()
    yield
    with get_db_session() as session:
        session.query(EventModel).delete()
        session.query(ExecutionModel).delete()
        session.query(ApprovalModel).delete()
        session.query(TaskModel).delete()


def test_recovery_waiting_approval_remains_waiting():
    task = TaskService.create_task(TaskRequest(instruction="Approval task waiting"))
    t_id = task.task_id
    TaskService.set_pending_approval(t_id, "app-rec-1")

    res = RecoveryService.recover_tasks_on_startup()
    assert t_id in res["waiting_approval"]

    # Verify status unchanged
    assert TaskService.get_task(t_id).status == TaskStatus.WAITING_APPROVAL


def test_recovery_unsafe_interrupted_operation_becomes_recovery_required():
    """If task was interrupted during unknown-side-effect operation, mark RECOVERY_REQUIRED."""
    task = TaskService.create_task(TaskRequest(instruction="Dangerous command task"))
    t_id = task.task_id
    TaskService.update_task_status(t_id, TaskStatus.EXECUTING)

    # Simulate in-flight running execution with side effects
    with get_db_session() as session:
        exec_record = ExecutionModel(
            execution_id="exec-rec-unsafe",
            task_id=t_id,
            step_id="step-1",
            tool_name="terminal",
            operation="execute",
            started_at=datetime.datetime.now(datetime.timezone.utc),
            status="RUNNING",
            retry_number=0,
        )
        session.add(exec_record)

    res = RecoveryService.recover_tasks_on_startup()
    assert t_id in res["recovery_required"]

    updated_task = TaskService.get_task(t_id)
    assert updated_task.status == TaskStatus.RECOVERY_REQUIRED


def test_recovery_safe_interrupted_operation():
    """If task was interrupted during safe read-only operation, it is safe to recover."""
    task = TaskService.create_task(TaskRequest(instruction="Read filesystem task"))
    t_id = task.task_id
    TaskService.update_task_status(t_id, TaskStatus.EXECUTING)

    with get_db_session() as session:
        exec_record = ExecutionModel(
            execution_id="exec-rec-safe",
            task_id=t_id,
            step_id="step-1",
            tool_name="filesystem",
            operation="read",
            started_at=datetime.datetime.now(datetime.timezone.utc),
            status="RUNNING",
            retry_number=0,
        )
        session.add(exec_record)

    res = RecoveryService.recover_tasks_on_startup()
    assert t_id in res["recovered"]
