"""
Unit and integration tests for Phase 5 Multi-Agent Collaboration system.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from langgraph.checkpoint.memory import MemorySaver

from backend.app.agents.registry import AgentRegistry
from backend.app.agents.supervisor import SupervisorAgent
from backend.app.llm.mock import MockLLMProvider
from backend.app.memory.manager import AgentMemoryManager, sanitize_memory_content
from backend.app.models.multi_agent import (
    AgentBudget,
    AgentDefinition,
    AgentMessage,
    AgentPermission,
    AgentStatus,
    AgentType,
    SubTask,
)
from backend.app.models.task import TaskStatus
from backend.app.security.agent_permissions import AgentPermissionManager
from backend.app.services.agent_budget import AgentBudgetTracker, BudgetExceededError
from backend.app.services.agent_message_bus import AgentMessageBus
from backend.app.services.multi_agent_service import MultiAgentService
from backend.app.services.parallel_executor import ParallelExecutor
from backend.app.services.result_aggregator import ResultAggregator
from backend.app.services.task_decomposer import TaskDecomposer


# ── 1. Agent Registry Tests ──────────────────────────────────────────

def test_agent_registry_discovery():
    AgentRegistry.reset()
    agents = AgentRegistry.list_agents()
    assert len(agents) >= 7

    supervisor = AgentRegistry.get("supervisor")
    assert supervisor is not None
    assert supervisor.agent_type == AgentType.SUPERVISOR

    research = AgentRegistry.get_by_type(AgentType.RESEARCH)
    assert research is not None
    assert "code.search" in research.allowed_tools


def test_agent_registry_rejects_duplicate():
    AgentRegistry.reset()
    with pytest.raises(ValueError, match="already registered"):
        AgentRegistry.register(AgentDefinition(
            name="supervisor",
            agent_type=AgentType.SUPERVISOR,
            description="Duplicate supervisor",
        ))


# ── 2. Permission & Security Tests ───────────────────────────────────

def test_agent_permission_matrix():
    AgentPermissionManager.reset()

    # Research: read allowed, patch denied
    assert AgentPermissionManager.can_use_tool(AgentType.RESEARCH, "code.read") is True
    assert AgentPermissionManager.can_use_tool(AgentType.RESEARCH, "patch.apply") is False

    # Coding: modify allowed, terminal denied
    assert AgentPermissionManager.can_modify_code(AgentType.CODING) is True
    assert AgentPermissionManager.can_use_tool(AgentType.CODING, "terminal.execute") is False

    # Delegation: ONLY Supervisor can delegate
    assert AgentPermissionManager.can_delegate(AgentType.SUPERVISOR) is True
    assert AgentPermissionManager.can_delegate(AgentType.CODING) is False
    assert AgentPermissionManager.can_delegate(AgentType.RESEARCH) is False


# ── 3. Task Decomposition & Cycle Detection ──────────────────────────

def test_task_decomposer_dag_and_cycle_check():
    decomposer = TaskDecomposer(llm_provider=MockLLMProvider())
    subtasks = decomposer.decompose("Fix buggy addition in calculator.py")
    assert len(subtasks) >= 3

    # Ensure no cycle
    TaskDecomposer.detect_cycles(subtasks)

    # Inject cycle and assert detection
    cyclic = [
        SubTask(task_id="t1", subtask_id="s1", description="1", assigned_agent=AgentType.RESEARCH, dependencies=["s2"]),
        SubTask(task_id="t1", subtask_id="s2", description="2", assigned_agent=AgentType.CODING, dependencies=["s1"]),
    ]
    with pytest.raises(ValueError, match="Circular dependency"):
        TaskDecomposer.detect_cycles(cyclic)


# ── 4. Structured Message Bus Tests ──────────────────────────────────

def test_agent_message_bus():
    AgentMessageBus.clear("task-m1")
    msg = AgentMessage(
        message_id="m-1",
        task_id="task-m1",
        sender_agent=AgentType.SUPERVISOR,
        recipient_agent=AgentType.RESEARCH,
        message_type="QUERY",
        payload={"query": "find functions"},
    )
    AgentMessageBus.send(msg)

    received = AgentMessageBus.receive("task-m1", AgentType.RESEARCH)
    assert len(received) == 1
    assert received[0].payload["query"] == "find functions"

    history = AgentMessageBus.get_history("task-m1")
    assert len(history) == 1


# ── 5. Multi-Tier Memory & Secret Sanitization ────────────────────────

def test_agent_memory_and_secret_redaction():
    AgentMemoryManager.clear("task-mem-1")

    # Store clean metadata
    AgentMemoryManager.write("task-mem-1", "project", "framework", "pytest")
    assert AgentMemoryManager.read("task-mem-1", "project", "framework") == "pytest"

    # Store credential containing string and verify automatic scrubbing
    secret_text = "Database conn string: api_key='sk-1234567890abcdef1234567890abcdef'"
    AgentMemoryManager.write("task-mem-1", "short_term", "conn", secret_text)
    stored = AgentMemoryManager.read("task-mem-1", "short_term", "conn")
    assert "[REDACTED_SECRET]" in stored
    assert "sk-1234567890abcdef" not in stored


# ── 6. Budget & Resource Limit Enforcement ────────────────────────────

def test_agent_budget_enforcement():
    AgentBudgetTracker.reset("task-b1")
    budget = AgentBudget(max_tokens=100, max_tool_calls=2, max_execution_time=60)
    AgentBudgetTracker.initialize_task("task-b1", budget=budget)

    # Tool calls within budget
    AgentBudgetTracker.record_tool_call("task-b1")
    AgentBudgetTracker.record_tool_call("task-b1")

    # Tool call exceeding budget
    with pytest.raises(BudgetExceededError, match="exceeded tool call limit"):
        AgentBudgetTracker.record_tool_call("task-b1")


# ── 7. Parallel Executor & Conflict Detection ─────────────────────────

def test_parallel_executor_conflict_partitioning():
    executor = ParallelExecutor(max_concurrency=4)

    st1 = SubTask(task_id="t1", subtask_id="s1", description="Edit A", assigned_agent=AgentType.CODING, target_files=["calc.py"])
    st2 = SubTask(task_id="t1", subtask_id="s2", description="Edit A conflict", assigned_agent=AgentType.CODING, target_files=["calc.py"])
    st3 = SubTask(task_id="t1", subtask_id="s3", description="Read B", assigned_agent=AgentType.RESEARCH, target_files=["other.py"])

    stages = executor._partition_conflict_free_stages([st1, st2, st3])
    # st1 and st2 modify the same file so they must be placed in separate stages
    assert len(stages) >= 2
    assert st1 in stages[0] or st2 in stages[0]


# ── 8. REST API Endpoints ─────────────────────────────────────────────

def test_multi_agent_api_endpoints():
    from fastapi.testclient import TestClient
    from backend.app.main import app

    client = TestClient(app)

    # 1. List catalog
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    assert len(resp.json()) >= 7

    # 2. Get specific agent
    resp = client.get("/api/agents/supervisor")
    assert resp.status_code == 200
    assert resp.json()["agent_type"] == "supervisor"

    # 3. 404 on nonexistent task
    resp = client.get("/api/multi-agent/nonexistent-task-id")
    assert resp.status_code == 404
