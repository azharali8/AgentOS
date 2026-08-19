"""
AgentOS Phase 2 — Concurrency Unit Tests
"""

import pytest
import threading
from backend.app.db.database import get_db_session
from backend.app.db.models import TaskModel, ApprovalModel, ExecutionModel, EventModel
from backend.app.llm.mock import MockLLMProvider
from backend.app.models.task import TaskRequest, TaskStatus
from backend.app.services.agent_service import AgentService
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


def test_concurrent_tasks_isolation():
    """Run two independent tasks concurrently and verify complete state isolation."""
    mock1 = MockLLMProvider()
    mock1.push_json({"steps": [{"step_id": "s1", "tool_name": "filesystem", "operation": "list", "arguments": {"path": "."}, "description": "Task 1 list"}]})
    mock1.push_json({"verdict": "SUCCESS", "reasoning": "Task 1 complete"})

    mock2 = MockLLMProvider()
    mock2.push_json({"steps": [{"step_id": "s2", "tool_name": "filesystem", "operation": "list", "arguments": {"path": "."}, "description": "Task 2 list"}]})
    mock2.push_json({"verdict": "SUCCESS", "reasoning": "Task 2 complete"})

    req1 = TaskRequest(instruction="Concurrent Task A")
    req2 = TaskRequest(instruction="Concurrent Task B")

    res1_holder = []
    res2_holder = []

    t1 = threading.Thread(target=lambda: res1_holder.append(AgentService.invoke_workflow_sync(req1, llm=mock1)))
    t2 = threading.Thread(target=lambda: res2_holder.append(AgentService.invoke_workflow_sync(req2, llm=mock2)))

    t1.start()
    t2.start()

    t1.join(timeout=10.0)
    t2.join(timeout=10.0)

    assert len(res1_holder) == 1
    assert len(res2_holder) == 1

    task1 = res1_holder[0]
    task2 = res2_holder[0]

    assert task1.task_id != task2.task_id
    assert task1.status == TaskStatus.COMPLETED
    assert task2.status == TaskStatus.COMPLETED
    assert task1.user_request == "Concurrent Task A"
    assert task2.user_request == "Concurrent Task B"
