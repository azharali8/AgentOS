"""
AgentOS Phase 2 — Idempotency Unit Tests
"""

import pytest
from backend.app.db.database import get_db_session
from backend.app.db.models import TaskModel, ApprovalModel, ExecutionModel, EventModel
from backend.app.models.task import TaskRequest, TaskStatus
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


def test_idempotent_task_creation_same_request():
    req = TaskRequest(instruction="Perform idempotent action")
    key = "unique-key-12345"

    task1 = TaskService.create_task(req, idempotency_key=key)
    task2 = TaskService.create_task(req, idempotency_key=key)

    assert task1.task_id == task2.task_id
    assert task1.user_request == task2.user_request


def test_idempotent_task_creation_different_request_fails():
    req1 = TaskRequest(instruction="Action A")
    req2 = TaskRequest(instruction="Action B")
    key = "unique-key-conflict"

    TaskService.create_task(req1, idempotency_key=key)

    with pytest.raises(ValueError, match="Idempotency key mismatch"):
        TaskService.create_task(req2, idempotency_key=key)
