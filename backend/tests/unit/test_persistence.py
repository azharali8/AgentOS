"""
AgentOS Phase 2 — Persistence Unit Tests
"""

import pytest
import datetime
from backend.app.db.database import get_db_session
from backend.app.db.models import TaskModel, ApprovalModel, ExecutionModel, EventModel
from backend.app.models.task import TaskRequest, TaskStatus
from backend.app.models.approval import ApprovalRequest, ApprovalStatus
from backend.app.models.tool import RiskLevel
from backend.app.security.approval import ApprovalManager
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


def test_task_create_and_retrieve():
    req = TaskRequest(instruction="Test persistent task creation")
    task = TaskService.create_task(req)
    assert task.task_id is not None
    assert task.status == TaskStatus.PENDING
    assert task.user_request == "Test persistent task creation"

    # Retrieve via service
    fetched = TaskService.get_task(task.task_id)
    assert fetched is not None
    assert fetched.task_id == task.task_id
    assert fetched.user_request == task.user_request


def test_task_status_updates():
    req = TaskRequest(instruction="Test status transitions")
    task = TaskService.create_task(req)
    t_id = task.task_id

    TaskService.update_task_status(t_id, TaskStatus.PLANNING)
    assert TaskService.get_task(t_id).status == TaskStatus.PLANNING

    TaskService.update_task_status(t_id, TaskStatus.EXECUTING)
    assert TaskService.get_task(t_id).status == TaskStatus.EXECUTING

    TaskService.set_final_response(t_id, "Completed successfully")
    final_task = TaskService.get_task(t_id)
    assert final_task.status == TaskStatus.COMPLETED
    assert final_task.final_response == "Completed successfully"
    assert final_task.completed_at is not None


def test_approval_persistence_and_resolution():
    req = TaskRequest(instruction="Task needing approval")
    task = TaskService.create_task(req)
    t_id = task.task_id

    app_req = ApprovalRequest(
        approval_id="app-12345",
        task_id=t_id,
        step_id="step-1",
        tool_name="terminal",
        operation="execute",
        arguments_hash="",
        arguments_summary={"command": "dir"},
        risk_level=RiskLevel.HIGH,
        reason="Test approval reason",
    )
    app_id = ApprovalManager.request_approval(app_req)
    assert app_id == "app-12345"

    # Retrieve
    stored_app = ApprovalManager.get_approval("app-12345")
    assert stored_app is not None
    assert stored_app.status == ApprovalStatus.PENDING
    assert stored_app.arguments_hash != ""

    # Verify hash check
    assert ApprovalManager.verify_request(
        approval_id="app-12345",
        task_id=t_id,
        step_id="step-1",
        tool_name="terminal",
        operation="execute",
        arguments={"command": "dir"},
    ) is True

    # Verify substitution detection
    assert ApprovalManager.verify_request(
        approval_id="app-12345",
        task_id=t_id,
        step_id="step-1",
        tool_name="terminal",
        operation="execute",
        arguments={"command": "del *"},
    ) is False

    # Resolve approval
    resolved = ApprovalManager.resolve_approval("app-12345", ApprovalStatus.APPROVED, "Approved by admin", "admin")
    assert resolved is True

    updated_app = ApprovalManager.get_approval("app-12345")
    assert updated_app.status == ApprovalStatus.APPROVED
    assert updated_app.resolved_by == "admin"
