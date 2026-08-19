"""
AgentOS Phase 2 — Event Store Unit Tests
"""

import pytest
from backend.app.db.database import get_db_session
from backend.app.db.models import TaskModel, ApprovalModel, ExecutionModel, EventModel
from backend.app.models.task import TaskRequest
from backend.app.services.event_service import EventService
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


def test_event_recording_and_chronology():
    req = TaskRequest(instruction="Event tracking test")
    task = TaskService.create_task(req)
    t_id = task.task_id

    EventService.record_event(task_id=t_id, event_type="TASK_CREATED", payload={"instruction": req.instruction})
    EventService.record_event(task_id=t_id, event_type="PLAN_CREATED", payload={"steps": ["s1", "s2"]})
    EventService.record_event(task_id=t_id, event_type="TOOL_STARTED", step_id="s1", payload={"tool": "filesystem"})
    EventService.record_event(task_id=t_id, event_type="TOOL_COMPLETED", step_id="s1", payload={"success": True})
    EventService.record_event(task_id=t_id, event_type="TASK_COMPLETED", payload={"final": "Done"})

    events = EventService.list_events(t_id)
    assert len(events) == 5

    event_types = [e["event_type"] for e in events]
    assert event_types == [
        "TASK_CREATED",
        "PLAN_CREATED",
        "TOOL_STARTED",
        "TOOL_COMPLETED",
        "TASK_COMPLETED",
    ]

    # Verify event fields
    assert events[0]["task_id"] == t_id
    assert events[2]["step_id"] == "s1"
    assert events[2]["payload"]["tool"] == "filesystem"
