"""
AgentOS Phase 1 — LangGraph integration tests.

Tests exercise the FULL pipeline: Planner → LangGraph → ToolRegistry →
Security → Approval → Executor → Observation → Reviewer → TaskService.

MockLLMProvider is used — NOT monkey-patched methods.
All Phase 0 security rules remain intact.

Test coverage:
  - Multi-step happy path (Tool A → observe → Tool B → observe → COMPLETE)
  - DENY path (policy check → FAILED immediately, plan step passes planner validation)
  - NEEDS_APPROVAL → APPROVED → re-validate security → execute → COMPLETE
  - NEEDS_APPROVAL → REJECTED → FAILED (execution must NOT occur)
  - Approval substitution attack → FAILED
  - RETRYABLE → replan → new ToolRequest → Security → execute
  - MAX_REPLANS reached → FAILED
  - MAX_TOOL_CALLS reached → FAILED
  - FATAL → FAILED immediately
"""

from __future__ import annotations

import json
import time
import threading
import pytest

from backend.app.agents.orchestrator import Orchestrator
from backend.app.config.settings import settings
from backend.app.llm.mock import MockLLMProvider
from backend.app.models.approval import ApprovalStatus
from backend.app.models.task import TaskRequest, TaskStatus
from backend.app.security.approval import ApprovalManager
from backend.app.services.agent_service import AgentService
from backend.app.services.task_service import TaskService
from backend.app.workflows import task_graph


from backend.app.db.database import get_db_session
from backend.app.db.models import TaskModel, ApprovalModel, ExecutionModel, EventModel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_state():
    """Reset all state between tests."""
    with get_db_session() as session:
        session.query(EventModel).delete()
        session.query(ExecutionModel).delete()
        session.query(ApprovalModel).delete()
        session.query(TaskModel).delete()
    task_graph.reset_graph(memory_only=True)
    yield
    with get_db_session() as session:
        session.query(EventModel).delete()
        session.query(ExecutionModel).delete()
        session.query(ApprovalModel).delete()
        session.query(TaskModel).delete()
    task_graph.reset_graph(memory_only=True)


def _plan(*steps) -> dict:
    """Build a valid plan dict for the mock LLM."""
    return {"steps": list(steps)}


def _fs_step(step_id: str, op: str = "list", path: str = ".") -> dict:
    return {
        "step_id": step_id,
        "tool_name": "filesystem",
        "operation": op,
        "arguments": {"path": path},
        "description": f"filesystem.{op} on {path}",
    }


def _success_review() -> dict:
    return {"verdict": "SUCCESS", "reasoning": "Completed"}


def _retryable_review() -> dict:
    return {"verdict": "RETRYABLE", "reasoning": "Transient error"}


def _fatal_review() -> dict:
    return {"verdict": "FATAL", "reasoning": "Unrecoverable"}


def _run_sync(instruction: str, mock: MockLLMProvider) -> str:
    """Run agent synchronously and return task_id."""
    request = TaskRequest(instruction=instruction)
    result = AgentService.invoke_workflow_sync(request, llm=mock)
    return result.task_id


# ---------------------------------------------------------------------------
# Multi-step happy path
# ---------------------------------------------------------------------------

class TestMultiStepExecution:
    def test_two_step_happy_path(self):
        """Tool A → observe → Tool B → observe → review → COMPLETE."""
        mock = MockLLMProvider()
        # Plan: list workspace (step 1), read a file (step 2)
        mock.push_json(_plan(
            _fs_step("s1", "list", "."),
            _fs_step("s2", "read", "test.txt"),
        ))
        # Both review as SUCCESS
        mock.push_json(_success_review())
        mock.push_json(_success_review())

        # Create test.txt so read succeeds
        from backend.app.services.workspace_service import WorkspaceService
        ws = WorkspaceService.get_workspace_root()
        test_file = ws / "test.txt"
        test_file.write_text("hello from test")

        try:
            task_id = _run_sync("list workspace then read test.txt", mock)
            task = TaskService.get_task(task_id)
            assert task.status == TaskStatus.COMPLETED, f"Got: {task.status}, error: {task.error}"
        finally:
            if test_file.exists():
                test_file.unlink()

    def test_single_step_completes(self):
        mock = MockLLMProvider()
        mock.push_json(_plan(_fs_step("s1", "list", ".")))
        mock.push_json(_success_review())

        task_id = _run_sync("list workspace", mock)
        task = TaskService.get_task(task_id)
        assert task.status == TaskStatus.COMPLETED
        assert task.error is None


# ---------------------------------------------------------------------------
# DENY path — test uses an operation that passes planner but is CRITICAL in policy
# ---------------------------------------------------------------------------

class TestSecurityDeny:
    def test_critical_operation_denied_by_security(self):
        """
        Temporarily add a policy entry for a known operation set to CRITICAL.
        The planner returns it successfully, but security_node must DENY it.

        Design: we add 'filesystem.list' as CRITICAL temporarily — it passes
        the planner (which checks DEFAULT_POLICIES keys) but gets denied by
        SecurityManager.is_allowed() which returns False for CRITICAL.
        """
        from backend.app.models.tool import RiskLevel
        from backend.app.security import policies as pol

        # Make filesystem.list temporarily CRITICAL so it passes planner but gets DENIED
        original_policies = dict(pol.DEFAULT_POLICIES)
        # Add as a known key (so planner validation passes) but set CRITICAL (security denies)
        pol.DEFAULT_POLICIES["filesystem.list"] = RiskLevel.CRITICAL

        try:
            mock = MockLLMProvider()
            mock.push_json(_plan(_fs_step("s1", "list", ".")))

            task_id = _run_sync("list workspace (critical deny)", mock)
            task = TaskService.get_task(task_id)
            assert task.status == TaskStatus.FAILED, f"Got: {task.status}"
            assert "DENIED" in (task.error or ""), f"Error: {task.error}"
        finally:
            pol.DEFAULT_POLICIES.clear()
            pol.DEFAULT_POLICIES.update(original_policies)


# ---------------------------------------------------------------------------
# Approval flow
# ---------------------------------------------------------------------------

class TestApprovalFlow:
    def _run_with_approval(self, mock, instruction, settings_require_approval=True):
        """Helper: start a task in background that will pause for approval."""
        from backend.app.models.tool import RiskLevel
        from backend.app.security import policies as pol

        original_policies = dict(pol.DEFAULT_POLICIES)
        original_require = settings.REQUIRE_APPROVAL_FOR_DANGEROUS_ACTIONS
        pol.DEFAULT_POLICIES["filesystem.list"] = RiskLevel.HIGH
        settings.REQUIRE_APPROVAL_FOR_DANGEROUS_ACTIONS = settings_require_approval

        request = TaskRequest(instruction=instruction)
        task = TaskService.create_task(request)
        task_id = task.task_id
        TaskService.update_task_status(task_id, TaskStatus.PLANNING)

        run_thread = threading.Thread(
            target=lambda: Orchestrator().coordinate(task_id, instruction, llm=mock),
            daemon=True,
        )
        run_thread.start()
        # Give graph time to reach and process the interrupt
        run_thread.join(timeout=2.0)

        return task_id, run_thread, original_policies, original_require

    def test_approval_required_then_approved(self):
        """
        NEEDS_APPROVAL → interrupt → APPROVED → re-validate → execute → COMPLETE.
        """
        from backend.app.models.tool import RiskLevel
        from backend.app.security import policies as pol

        original_policies = dict(pol.DEFAULT_POLICIES)
        original_require = settings.REQUIRE_APPROVAL_FOR_DANGEROUS_ACTIONS
        pol.DEFAULT_POLICIES["filesystem.list"] = RiskLevel.HIGH
        settings.REQUIRE_APPROVAL_FOR_DANGEROUS_ACTIONS = True

        try:
            mock = MockLLMProvider()
            mock.push_json(_plan(_fs_step("s1", "list", ".")))
            mock.push_json(_success_review())

            request = TaskRequest(instruction="list workspace (approval required)")
            task = TaskService.create_task(request)
            task_id = task.task_id
            TaskService.update_task_status(task_id, TaskStatus.PLANNING)

            # Run in background; will pause at interrupt
            run_thread = threading.Thread(
                target=lambda: Orchestrator().coordinate(task_id, request.instruction, llm=mock),
                daemon=True,
            )
            run_thread.start()
            run_thread.join(timeout=2.0)  # graph pauses here at interrupt

            task = TaskService.get_task(task_id)
            assert task.status == TaskStatus.WAITING_APPROVAL, f"Got: {task.status}, err: {task.error}"
            approval_id = task.approval_id
            assert approval_id is not None, "approval_id must be set"

            # Resolve: APPROVED — runs resume in background thread and waits
            AgentService.resolve_approval(task_id, approval_id, approved=True)
            # Give the resume thread time to complete
            time.sleep(1.0)

            task = TaskService.get_task(task_id)
            assert task.status == TaskStatus.COMPLETED, f"Got: {task.status}, err: {task.error}"
        finally:
            pol.DEFAULT_POLICIES.clear()
            pol.DEFAULT_POLICIES.update(original_policies)
            settings.REQUIRE_APPROVAL_FOR_DANGEROUS_ACTIONS = original_require

    def test_approval_rejected_no_execution(self):
        """
        NEEDS_APPROVAL → REJECTED → execution MUST NOT occur → FAILED.
        """
        from backend.app.models.tool import RiskLevel
        from backend.app.security import policies as pol

        original_policies = dict(pol.DEFAULT_POLICIES)
        original_require = settings.REQUIRE_APPROVAL_FOR_DANGEROUS_ACTIONS
        pol.DEFAULT_POLICIES["filesystem.list"] = RiskLevel.HIGH
        settings.REQUIRE_APPROVAL_FOR_DANGEROUS_ACTIONS = True

        try:
            mock = MockLLMProvider()
            mock.push_json(_plan(_fs_step("s1", "list", ".")))

            request = TaskRequest(instruction="list workspace (will be rejected)")
            task = TaskService.create_task(request)
            task_id = task.task_id
            TaskService.update_task_status(task_id, TaskStatus.PLANNING)

            run_thread = threading.Thread(
                target=lambda: Orchestrator().coordinate(task_id, request.instruction, llm=mock),
                daemon=True,
            )
            run_thread.start()
            run_thread.join(timeout=2.0)

            task = TaskService.get_task(task_id)
            assert task.status == TaskStatus.WAITING_APPROVAL, f"Got: {task.status}, err: {task.error}"
            approval_id = task.approval_id

            # Resolve: REJECTED
            AgentService.resolve_approval(task_id, approval_id, approved=False)
            time.sleep(1.0)

            task = TaskService.get_task(task_id)
            assert task.status == TaskStatus.FAILED, f"Got: {task.status}"
            assert "rejected" in (task.error or "").lower(), f"Error: {task.error}"
        finally:
            pol.DEFAULT_POLICIES.clear()
            pol.DEFAULT_POLICIES.update(original_policies)
            settings.REQUIRE_APPROVAL_FOR_DANGEROUS_ACTIONS = original_require

    def test_approval_substitution_attack_fails(self):
        """
        Resume with wrong approval_id → FAILED.
        Prevents approval of one request being used to execute another.
        """
        from backend.app.models.tool import RiskLevel
        from backend.app.security import policies as pol

        original_policies = dict(pol.DEFAULT_POLICIES)
        original_require = settings.REQUIRE_APPROVAL_FOR_DANGEROUS_ACTIONS
        pol.DEFAULT_POLICIES["filesystem.list"] = RiskLevel.HIGH
        settings.REQUIRE_APPROVAL_FOR_DANGEROUS_ACTIONS = True

        try:
            mock = MockLLMProvider()
            mock.push_json(_plan(_fs_step("s1", "list", ".")))

            request = TaskRequest(instruction="list workspace")
            task = TaskService.create_task(request)
            task_id = task.task_id
            TaskService.update_task_status(task_id, TaskStatus.PLANNING)

            run_thread = threading.Thread(
                target=lambda: Orchestrator().coordinate(task_id, request.instruction, llm=mock),
                daemon=True,
            )
            run_thread.start()
            run_thread.join(timeout=2.0)

            task = TaskService.get_task(task_id)
            assert task.status == TaskStatus.WAITING_APPROVAL, f"Got: {task.status}, err: {task.error}"

            # Resume with WRONG approval_id (substitution attack)
            AgentService.resolve_approval(task_id, "fake-approval-id-000", approved=True)
            time.sleep(1.0)

            task = TaskService.get_task(task_id)
            assert task.status == TaskStatus.FAILED, f"Got: {task.status}"
            assert "mismatch" in (task.error or "").lower(), f"Error: {task.error}"
        finally:
            pol.DEFAULT_POLICIES.clear()
            pol.DEFAULT_POLICIES.update(original_policies)
            settings.REQUIRE_APPROVAL_FOR_DANGEROUS_ACTIONS = original_require


# ---------------------------------------------------------------------------
# Replanning
# ---------------------------------------------------------------------------

class TestReplanning:
    def test_retryable_triggers_replan(self):
        """RETRYABLE review → replan → new steps → security → execute → COMPLETE."""
        mock = MockLLMProvider()
        # Initial plan: one step
        mock.push_json(_plan(_fs_step("s1", "list", ".")))
        # First MAX_RETRIES_PER_STEP reviews → RETRYABLE (same step retried)
        # After MAX_RETRIES_PER_STEP+1 RETRYABLE reviews, replan is triggered
        for _ in range(settings.MAX_RETRIES_PER_STEP + 1):
            mock.push_json(_retryable_review())
        # Replan produces a new valid plan
        mock.push_json(_plan(_fs_step("r1", "list", ".")))
        # Review the replanned step as SUCCESS
        mock.push_json(_success_review())

        task_id = _run_sync("list with retry", mock)
        task = TaskService.get_task(task_id)
        assert task.status == TaskStatus.COMPLETED, f"Got: {task.status}, err: {task.error}"

    def test_max_replans_reached_fails(self):
        """Exhaust MAX_REPLANS → FAILED."""
        mock = MockLLMProvider()
        # Initial plan
        mock.push_json(_plan(_fs_step("s1", "list", ".")))

        # We need to feed enough RETRYABLE reviews to exhaust retries for each plan,
        # then feed replan responses. After MAX_REPLANS, it should FAIL.
        # Each "cycle" needs MAX_RETRIES_PER_STEP + 1 reviews, then a replan response.
        # With MAX_REPLANS=3 default: we need 3 full cycles + final failure.
        for cycle in range(settings.MAX_REPLANS + 1):
            # After each replan, the new step also fails MAX_RETRIES times
            for _ in range(settings.MAX_RETRIES_PER_STEP + 1):
                mock.push_json(_retryable_review())
            # Provide replan response (for cycles < MAX_REPLANS)
            if cycle < settings.MAX_REPLANS:
                mock.push_json(_plan(_fs_step(f"r{cycle}", "list", ".")))

        task_id = _run_sync("force max replans", mock)
        task = TaskService.get_task(task_id)
        assert task.status == TaskStatus.FAILED, f"Got: {task.status}, err: {task.error}"
        error_lower = (task.error or "").lower()
        assert "max_replans" in error_lower or "replan" in error_lower or "planner" in error_lower, \
            f"Expected replan-related error, got: {task.error}"

    def test_max_tool_calls_reached_fails(self):
        """Exceed MAX_TOOL_CALLS → FAILED."""
        mock = MockLLMProvider()
        # Temporarily raise MAX_PLAN_STEPS so a large plan is accepted
        original_plan_steps = settings.MAX_PLAN_STEPS
        original_tool_calls = settings.MAX_TOOL_CALLS
        # Set small limits for fast test
        settings.MAX_PLAN_STEPS = 5
        settings.MAX_TOOL_CALLS = 2

        try:
            # Plan with 5 steps — only 2 tool calls allowed
            steps = [_fs_step(f"s{i}", "list", ".") for i in range(5)]
            mock.push_json({"steps": steps})
            # Reviews for the first 2 (MAX_TOOL_CALLS) steps succeed, then limit hits
            for _ in range(6):
                mock.push_json(_success_review())

            task_id = _run_sync("force max tool calls", mock)
            task = TaskService.get_task(task_id)
            assert task.status == TaskStatus.FAILED, f"Got: {task.status}, err: {task.error}"
            assert "MAX_TOOL_CALLS" in (task.error or ""), f"Error: {task.error}"
        finally:
            settings.MAX_PLAN_STEPS = original_plan_steps
            settings.MAX_TOOL_CALLS = original_tool_calls


# ---------------------------------------------------------------------------
# Fatal error path
# ---------------------------------------------------------------------------

class TestFatalPath:
    def test_fatal_review_fails_immediately(self):
        mock = MockLLMProvider()
        mock.push_json(_plan(_fs_step("s1", "list", ".")))
        mock.push_json(_fatal_review())

        task_id = _run_sync("fatal step", mock)
        task = TaskService.get_task(task_id)
        assert task.status == TaskStatus.FAILED, f"Got: {task.status}"
        error_lower = (task.error or "").lower()
        assert "fatal" in error_lower or "unrecoverable" in error_lower, f"Error: {task.error}"
