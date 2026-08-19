"""
AgentOS Phase 2 — Restart & Recovery Integration Tests
"""

import threading
import time
import pytest

from backend.app.agents.orchestrator import Orchestrator
from backend.app.config.settings import settings
from backend.app.db.database import get_db_session
from backend.app.db.models import TaskModel, ApprovalModel, ExecutionModel, EventModel
from backend.app.llm.mock import MockLLMProvider
from backend.app.models.approval import ApprovalStatus
from backend.app.models.task import TaskRequest, TaskStatus
from backend.app.models.tool import RiskLevel
from backend.app.security import policies as pol
from backend.app.services.agent_service import AgentService
from backend.app.services.recovery_service import RecoveryService
from backend.app.services.task_service import TaskService
from backend.app.workflows import task_graph


@pytest.fixture(autouse=True)
def clean_db():
    with get_db_session() as session:
        session.query(EventModel).delete()
        session.query(ExecutionModel).delete()
        session.query(ApprovalModel).delete()
        session.query(TaskModel).delete()
    task_graph.reset_graph()
    yield
    with get_db_session() as session:
        session.query(EventModel).delete()
        session.query(ExecutionModel).delete()
        session.query(ApprovalModel).delete()
        session.query(TaskModel).delete()
    task_graph.reset_graph()


def test_restart_approval_flow_survives():
    """
    Process A:
      - Create task
      - Pauses at WAITING_APPROVAL
      - Simulated shutdown (reset runtime)
    Process B:
      - Startup recovery runs
      - Task remains WAITING_APPROVAL
      - Resolve approval
      - Revalidation & resume
      - Completes successfully
    """
    original_policies = dict(pol.DEFAULT_POLICIES)
    original_require = settings.REQUIRE_APPROVAL_FOR_DANGEROUS_ACTIONS
    pol.DEFAULT_POLICIES["filesystem.list"] = RiskLevel.HIGH
    settings.REQUIRE_APPROVAL_FOR_DANGEROUS_ACTIONS = True

    try:
        mock = MockLLMProvider()
        mock.push_json({
            "steps": [
                {
                    "step_id": "s1",
                    "tool_name": "filesystem",
                    "operation": "list",
                    "arguments": {"path": "."},
                    "description": "List directory post restart",
                }
            ]
        })
        mock.push_json({"verdict": "SUCCESS", "reasoning": "Completed after resume"})

        # Process A starts
        req = TaskRequest(instruction="Restart approval test")
        task = TaskService.create_task(req)
        task_id = task.task_id
        TaskService.update_task_status(task_id, TaskStatus.PLANNING)

        run_thread = threading.Thread(
            target=lambda: Orchestrator().coordinate(task_id, req.instruction, llm=mock),
            daemon=True,
        )
        run_thread.start()
        run_thread.join(timeout=2.0)

        task_a = TaskService.get_task(task_id)
        assert task_a.status == TaskStatus.WAITING_APPROVAL
        approval_id = task_a.approval_id
        assert approval_id is not None

        # --- SIMULATE PROCESS SHUTDOWN & RESTART ---
        task_graph.reset_graph()

        # Process B starts up
        recovery_summary = RecoveryService.recover_tasks_on_startup()
        assert task_id in recovery_summary["waiting_approval"]

        task_b = TaskService.get_task(task_id)
        assert task_b.status == TaskStatus.WAITING_APPROVAL

        # Process B resolves approval
        AgentService.resolve_approval(task_id, approval_id, approved=True)
        time.sleep(1.0)

        final_task = TaskService.get_task(task_id)
        assert final_task.status == TaskStatus.COMPLETED
        assert final_task.final_response is not None

    finally:
        pol.DEFAULT_POLICIES = original_policies
        settings.REQUIRE_APPROVAL_FOR_DANGEROUS_ACTIONS = original_require
