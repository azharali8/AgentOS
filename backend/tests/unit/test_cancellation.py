"""
AgentOS Phase 2 — Cancellation Unit Tests
"""

import pytest
from backend.app.db.database import get_db_session
from backend.app.db.models import TaskModel, ApprovalModel, ExecutionModel, EventModel
from backend.app.models.task import TaskRequest, TaskStatus
from backend.app.services.event_service import EventService
from backend.app.services.execution_manager import ExecutionManager
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


def test_cancel_pending_task():
    req = TaskRequest(instruction="Cancel test pending")
    task = TaskService.create_task(req)
    t_id = task.task_id

    cancelled = TaskService.cancel_task(t_id)
    assert cancelled is True

    updated = TaskService.get_task(t_id)
    assert updated.status == TaskStatus.CANCELLED


def test_cancel_waiting_approval_task():
    req = TaskRequest(instruction="Cancel test waiting approval")
    task = TaskService.create_task(req)
    t_id = task.task_id
    TaskService.set_pending_approval(t_id, "app-test")

    cancelled = TaskService.cancel_task(t_id)
    assert cancelled is True

    updated = TaskService.get_task(t_id)
    assert updated.status == TaskStatus.CANCELLED


def test_cancel_executing_task_records_event():
    req = TaskRequest(instruction="Cancel executing task")
    task = TaskService.create_task(req)
    t_id = task.task_id
    TaskService.update_task_status(t_id, TaskStatus.EXECUTING)

    cancelled = TaskService.cancel_task(t_id)
    assert cancelled is True

    assert ExecutionManager.is_cancelled(t_id) is True

    updated = TaskService.get_task(t_id)
    assert updated.status == TaskStatus.CANCELLED

    # Check cancellation event recorded
    events = EventService.list_events(t_id)
    cancelled_events = [e for e in events if e["event_type"] == "TASK_CANCELLED"]
    assert len(cancelled_events) >= 1
