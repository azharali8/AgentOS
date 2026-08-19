"""
AgentOS Phase 2 — API Unit & Integration Tests
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.db.database import get_db_session
from backend.app.db.models import TaskModel, ApprovalModel, ExecutionModel, EventModel
from backend.app.main import app
from backend.app.models.task import TaskRequest, TaskStatus
from backend.app.services.task_service import TaskService


client = TestClient(app)


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


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_endpoint():
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"] == "ok"
    assert data["checks"]["config"] == "ok"


def test_metrics_endpoint():
    response = client.get("/api/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "tasks_total" in data
    assert "approvals_requested" in data
    assert "tool_calls_total" in data


def test_list_tasks_pagination():
    # Create 5 tasks
    for i in range(5):
        TaskService.create_task(TaskRequest(instruction=f"Pagination task {i}"))

    # Limit 2 offset 0
    resp1 = client.get("/api/tasks?limit=2&offset=0")
    assert resp1.status_code == 200
    assert len(resp1.json()) == 2

    # Limit 2 offset 2
    resp2 = client.get("/api/tasks?limit=2&offset=2")
    assert resp2.status_code == 200
    assert len(resp2.json()) == 2

    # Invalid pagination
    resp_invalid = client.get("/api/tasks?limit=0")
    assert resp_invalid.status_code == 422


def test_cancel_task_api():
    task = TaskService.create_task(TaskRequest(instruction="Task to cancel via API"))
    t_id = task.task_id

    resp = client.post(f"/api/tasks/{t_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"

    # Verify task status is cancelled
    get_resp = client.get(f"/api/tasks/{t_id}")
    assert get_resp.json()["status"] == "CANCELLED"


def test_task_history_api():
    from backend.app.services.event_service import EventService
    task = TaskService.create_task(TaskRequest(instruction="Task for history API"))
    t_id = task.task_id

    EventService.record_event(task_id=t_id, event_type="TASK_CREATED", payload={"foo": "bar"})
    EventService.record_event(task_id=t_id, event_type="TASK_STARTED")

    resp = client.get(f"/api/tasks/{t_id}/history")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 2
    assert events[0]["event_type"] == "TASK_CREATED"
    assert events[1]["event_type"] == "TASK_STARTED"
