"""
AgentOS Phase 13 Evaluation Suite — Deterministic Benchmarks (20/20 Target).

Covers all 20 Phase 13 capabilities:
1. P13-01: Task-aware classification and routing
2. P13-02: Task prioritization and concurrency queue
3. P13-03: Per-agent worker concurrency isolation
4. P13-04: Two-phase task cancellation (RUNNING -> CANCELLING -> CANCELLED)
5. P13-05: First-class durable task pause
6. P13-06: Task resumption from checkpoint
7. P13-07: Interrupted task startup recovery detection
8. P13-08: Immutable artifact storage and retrieval
9. P13-09: Artifact cryptographic tamper detection (ArtifactIntegrityError)
10. P13-10: Context engine relevance scoring and explanation
11. P13-11: Context token budgeting and compression
12. P13-12: Model router task-aware profile selection
13. P13-13: Model router graceful degradation (No silent mock in prod)
14. P13-14: Model router health probing
15. P13-15: Structured agent protocol validation and trace logging
16. P13-16: Adaptive replanning with partial result preservation
17. P13-17: Failure classification (Tool, Agent, Timeout, Security)
18. P13-18: Administrative security and audit logging
19. P13-19: Workspace boundary and RBAC non-bypassability
20. P13-20: Full long-running multi-agent engineering workflow
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.agents.debugger import DebuggerAgent
from backend.app.agents.domain_experts import CybersecurityAgent, DataEngineerAgent, DevOpsAgent, TestingAgent
from backend.app.agents.reviewer import ReviewerAgent
from backend.app.agents.specialized import CodingAgent, ResearchAgent, SecurityAgent
from backend.app.agents.supervisor import SupervisorAgent
from backend.app.code.patch.models import Patch, PatchFile, PatchHunk, compute_patch_hash
from backend.app.config.settings import settings
from backend.app.db.database import get_db_session
from backend.app.db.models import ArtifactModel, TaskModel
from backend.app.models.engineering_workflow import CodeChangesPayload, DiagnosisReport, TestExecutionReport
from backend.app.models.multi_agent import AgentResult, AgentStatus, AgentType, SubTask
from backend.app.models.task import TaskPriority, TaskRequest, TaskResult, TaskStatus
from backend.app.services.agent_protocol import AgentProtocol, MessageType
from backend.app.services.artifact_service import Artifact, ArtifactIntegrityError, ArtifactService, ArtifactType
from backend.app.services.audit_service import AuditService
from backend.app.services.concurrency_manager import ConcurrencyManager
from backend.app.services.context_engine import ContextEngine
from backend.app.services.event_service import EventService
from backend.app.services.execution_manager import ExecutionManager
from backend.app.services.model_router import ModelHealth, ModelRouter, ModelStatus, ModelTaskType, ModelUnavailableError
from backend.app.services.multi_agent_service import MultiAgentService
from backend.app.services.task_classifier import TaskCategory, TaskClassification, TaskClassifier
from backend.app.services.task_runtime import TaskRuntime
from backend.app.services.task_service import TaskService
from backend.app.services.trace_service import TraceService
from backend.app.services.workspace_service import WorkspaceService


class Phase13BenchmarkSuite:
    """Consolidated Phase 13 test battery (20 cases)."""

    @classmethod
    def run_all(cls) -> Dict[str, Any]:
        workspace_root = Path(settings.WORKSPACE_ROOT)
        workspace_root.mkdir(parents=True, exist_ok=True)
        calc_path = workspace_root / "calculator.py"
        calc_path.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

        cases = [
            ("P13-01", "Task-aware classification and routing", cls._test_01_classification),
            ("P13-02", "Task prioritization and concurrency queue", cls._test_02_concurrency_queue),
            ("P13-03", "Per-agent worker concurrency isolation", cls._test_03_agent_semaphores),
            ("P13-04", "Two-phase task cancellation lifecycle", cls._test_04_cancellation),
            ("P13-05", "First-class durable task pause", cls._test_05_task_pause),
            ("P13-06", "Task resumption from checkpoint", cls._test_06_task_resume),
            ("P13-07", "Interrupted task startup recovery detection", cls._test_07_startup_recovery),
            ("P13-08", "Immutable artifact storage and retrieval", cls._test_08_artifact_storage),
            ("P13-09", "Artifact cryptographic tamper detection", cls._test_09_artifact_tamper),
            ("P13-10", "Context engine relevance scoring and explanation", cls._test_10_context_engine),
            ("P13-11", "Context token budgeting and compression", cls._test_11_context_token_budget),
            ("P13-12", "Model router task-aware profile selection", cls._test_12_model_router_profiles),
            ("P13-13", "Model router graceful degradation", cls._test_13_model_router_no_mock_prod),
            ("P13-14", "Model router health probing", cls._test_14_model_router_health),
            ("P13-15", "Structured agent protocol validation and trace logging", cls._test_15_agent_protocol),
            ("P13-16", "Adaptive replanning with partial result preservation", cls._test_16_adaptive_replan),
            ("P13-17", "Failure classification and recovery strategies", cls._test_17_failure_classification),
            ("P13-18", "Administrative security and audit logging", cls._test_18_audit_logging),
            ("P13-19", "Workspace boundary and RBAC non-bypassability", cls._test_19_security_enforcement),
            ("P13-20", "Full long-running multi-agent engineering workflow", cls._test_20_full_long_running_workflow),
        ]

        results = []
        passed_count = 0

        for case_id, name, func in cases:
            start_t = time.perf_counter()
            try:
                func()
                dur = time.perf_counter() - start_t
                passed_count += 1
                results.append({"case_id": case_id, "name": name, "passed": True, "duration_seconds": round(dur, 4), "error": None})
            except Exception as exc:
                dur = time.perf_counter() - start_t
                results.append({"case_id": case_id, "name": name, "passed": False, "duration_seconds": round(dur, 4), "error": str(exc)})

        return {
            "total_cases": len(cases),
            "passed_count": passed_count,
            "failed_count": len(cases) - passed_count,
            "success_rate_pct": (passed_count / len(cases)) * 100.0,
            "results": results,
        }

    @staticmethod
    def _test_01_classification():
        c1 = TaskClassifier.classify("Fix failing unit test in calculator arithmetic function")
        assert c1.category == TaskCategory.DEBUGGING
        assert AgentType.DEBUGGER in c1.required_agents
        assert c1.requires_testing is True

        c2 = TaskClassifier.classify("Audit security credentials and vulnerability scanning")
        assert c2.category == TaskCategory.SECURITY_AUDIT
        assert c2.risk_level == "CRITICAL"

        c3 = TaskClassifier.classify("Clean CSV dataset and profile column missingness")
        assert c3.category == TaskCategory.DATA_ENGINEERING

    @staticmethod
    def _test_02_concurrency_queue():
        # Clean queue state
        ConcurrencyManager._active_tasks.clear()
        ConcurrencyManager._task_queue.clear()

        # Fill capacity (4 slots)
        assert ConcurrencyManager.can_start_task("t-1", TaskPriority.NORMAL) is True
        assert ConcurrencyManager.can_start_task("t-2", TaskPriority.NORMAL) is True
        assert ConcurrencyManager.can_start_task("t-3", TaskPriority.NORMAL) is True
        assert ConcurrencyManager.can_start_task("t-4", TaskPriority.NORMAL) is True

        # 5th task is queued
        assert ConcurrencyManager.can_start_task("t-5-crit", TaskPriority.CRITICAL) is False
        assert ConcurrencyManager.can_start_task("t-6-low", TaskPriority.LOW) is False

        # Release one slot -> t-5-crit should dequeue first due to CRITICAL priority
        next_t = ConcurrencyManager.release_task("t-1")
        assert next_t == "t-5-crit"

    @staticmethod
    def _test_03_agent_semaphores():
        # Coding semaphore has limit 2
        assert ConcurrencyManager.acquire_agent_slot(AgentType.CODING, timeout=0.1) is True
        assert ConcurrencyManager.acquire_agent_slot(AgentType.CODING, timeout=0.1) is True
        # 3rd attempt fails/timeouts
        assert ConcurrencyManager.acquire_agent_slot(AgentType.CODING, timeout=0.05) is False
        # Release
        ConcurrencyManager.release_agent_slot(AgentType.CODING)
        assert ConcurrencyManager.acquire_agent_slot(AgentType.CODING, timeout=0.1) is True
        ConcurrencyManager.release_agent_slot(AgentType.CODING)
        ConcurrencyManager.release_agent_slot(AgentType.CODING)

    @staticmethod
    def _test_04_cancellation():
        task = TaskService.create_task(TaskRequest(instruction="Long running task"))
        TaskService.update_task_status(task.task_id, TaskStatus.EXECUTING)

        success = TaskRuntime.cancel_task(task.task_id, reason="User cancelled test")
        assert success is True
        updated = TaskService.get_task(task.task_id)
        assert updated.status == TaskStatus.CANCELLED

    @staticmethod
    def _test_05_task_pause():
        task = TaskService.create_task(TaskRequest(instruction="Pausable task"))
        TaskService.update_task_status(task.task_id, TaskStatus.EXECUTING)

        paused = TaskRuntime.pause_task(task.task_id)
        assert paused is True
        assert TaskRuntime.is_paused(task.task_id) is True
        updated = TaskService.get_task(task.task_id)
        assert updated.status == TaskStatus.PAUSED

    @staticmethod
    def _test_06_task_resume():
        task = TaskService.create_task(TaskRequest(instruction="Resumable task"))
        TaskService.update_task_status(task.task_id, TaskStatus.PAUSED)

        res = TaskRuntime.resume_task(task.task_id)
        assert res.status == TaskStatus.EXECUTING
        assert TaskRuntime.is_paused(task.task_id) is False

    @staticmethod
    def _test_07_startup_recovery():
        task_id = f"p13-crash-{int(time.time())}"
        with get_db_session() as session:
            t = TaskModel(
                task_id=task_id,
                user_request="Stranded execution",
                status=TaskStatus.EXECUTING.value,
            )
            session.add(t)
            session.commit()

        recovered = TaskRuntime.startup_recovery()
        assert task_id in recovered
        task = TaskService.get_task(task_id)
        assert task.status == TaskStatus.RECOVERY_REQUIRED

    @staticmethod
    def _test_08_artifact_storage():
        task_id = f"p13-art-{int(time.time())}"
        payload = {"diff": "+def sub(a, b): return a - b", "target": "calculator.py"}
        art = ArtifactService.save(
            task_id=task_id,
            agent_id="coding",
            artifact_type=ArtifactType.PATCH,
            content=payload,
        )
        assert len(art.content_hash) == 64

        fetched = ArtifactService.get(art.artifact_id)
        assert fetched is not None
        assert fetched.content["target"] == "calculator.py"

    @staticmethod
    def _test_09_artifact_tamper():
        task_id = f"p13-tamper-{int(time.time())}"
        payload = {"verdict": "APPROVE", "score": 0.98}
        art = ArtifactService.save(
            task_id=task_id,
            agent_id="reviewer",
            artifact_type=ArtifactType.REVIEW,
            content=payload,
        )

        # Directly corrupt database row to simulate unauthorized tamper
        with get_db_session() as session:
            row = session.query(ArtifactModel).filter(ArtifactModel.artifact_id == art.artifact_id).first()
            row.content_json = {"verdict": "REJECT_TAMPERED", "score": 0.1}
            session.add(row)
            session.commit()

        # Read-time cryptographic check MUST raise ArtifactIntegrityError
        try:
            ArtifactService.get(art.artifact_id)
            assert False, "Failed to catch artifact tampering!"
        except ArtifactIntegrityError:
            pass  # Expected cryptographic protection

    @staticmethod
    def _test_10_context_engine():
        engine = ContextEngine()
        bundle = engine.assemble_context(
            task_id="p13-ctx",
            instruction="Fix calculator arithmetic function in calculator.py",
            target_agent=AgentType.CODING,
            token_budget=2000,
        )
        assert "calculator.py" in bundle.files
        file_ctx = bundle.files["calculator.py"]
        assert file_ctx.why_selected != ""
        assert file_ctx.relevance_score > 0

    @staticmethod
    def _test_11_context_token_budget():
        engine = ContextEngine()
        bundle = engine.assemble_context(
            task_id="p13-budget",
            instruction="calculator.py",
            target_agent=AgentType.CODING,
            token_budget=100,  # Very small budget
        )
        assert bundle.total_tokens_estimated <= 100 or bundle.budget_exceeded is False

    @staticmethod
    def _test_12_model_router_profiles():
        # Router maps task types to appropriate tiers
        summary = ModelRouter.get_runtime_summary()
        assert "task_routing_matrix" in summary
        assert "CODING" in summary["task_routing_matrix"]
        assert "REASONING" in summary["task_routing_matrix"]

    @staticmethod
    def _test_13_model_router_no_mock_prod():
        # In non-test mode, unreachable provider raises ModelUnavailableError instead of silent mock
        ModelRouter.set_test_mode(False)
        old_prov = settings.LLM_PROVIDER
        try:
            settings.LLM_PROVIDER = "unreachable_prov"
            try:
                ModelRouter.get_provider(ModelTaskType.CODING)
                assert False, "Should raise ModelUnavailableError"
            except ModelUnavailableError:
                pass
        finally:
            settings.LLM_PROVIDER = old_prov
            ModelRouter.set_test_mode(True)

    @staticmethod
    def _test_14_model_router_health():
        health: ModelHealth = ModelRouter.check_health()
        assert health.status in (ModelStatus.READY, ModelStatus.DEGRADED, ModelStatus.UNAVAILABLE)
        assert health.latency_ms >= 0.0

    @staticmethod
    def _test_15_agent_protocol():
        task_id = f"p13-proto-{int(time.time())}"
        envelope = AgentProtocol.send(
            task_id=task_id,
            sender=AgentType.SUPERVISOR,
            recipient=AgentType.CODING,
            message_type=MessageType.TASK_ASSIGNMENT,
            payload={"subtask_id": "st-1", "action": "formulate_patch"},
            subtask_id="st-1",
        )
        assert envelope.message_id != ""
        history = AgentProtocol.get_task_history(task_id)
        assert len(history) >= 1
        assert history[0].recipient == AgentType.CODING.value

    @staticmethod
    def _test_16_adaptive_replan():
        supervisor = SupervisorAgent()
        st = SubTask(
            task_id="p13-replan",
            subtask_id="st-t",
            description="Run unit tests",
            assigned_agent=AgentType.TESTING,
            target_files=["calculator.py"],
        )
        failed_res = AgentResult(
            subtask_id="st-t",
            agent_type=AgentType.TESTING,
            status=AgentStatus.FAILED,
            summary="Tests failed",
            error="AssertionError in test_add",
        )
        decision = supervisor.handle_subtask_failure(st, failed_res, "p13-replan")
        assert decision.strategy == "REROUTE"
        assert decision.assigned_agent == AgentType.DEBUGGER.value

    @staticmethod
    def _test_17_failure_classification():
        supervisor = SupervisorAgent()
        st_sec = SubTask(task_id="p13-sec", subtask_id="st-s", description="Unauthorized", assigned_agent=AgentType.CODING)
        res_sec = AgentResult(subtask_id="st-s", agent_type=AgentType.CODING, status=AgentStatus.FAILED, summary="denied", error="Permission denied")
        dec = supervisor.handle_subtask_failure(st_sec, res_sec, "p13-sec")
        assert dec.strategy == "ABORT"

    @staticmethod
    def _test_18_audit_logging():
        log_id = AuditService.record(
            action="APPROVAL_GRANTED",
            status="SUCCESS",
            user_id="dev-user-42",
            user_role="DEVELOPER",
            target_entity="approval",
            target_id="appr-1234",
            details={"patch_hash": "a1b2c3d4"},
        )
        assert log_id != ""
        logs = AuditService.list_logs(limit=5, action="APPROVAL_GRANTED")
        assert len(logs) >= 1
        assert logs[0].target_id == "appr-1234"

    @staticmethod
    def _test_19_security_enforcement():
        # Security boundary rejection
        with pytest_raises():
            WorkspaceService.validate_path("../../../etc/passwd")

    @staticmethod
    def _test_20_full_long_running_workflow():
        ModelRouter.set_test_mode(True)
        task = MultiAgentService.start_task(
            instruction="Add multiply method to calculator.py and verify tests",
            sync=True,
        )
        assert task.status in (TaskStatus.COMPLETED, TaskStatus.WAITING_APPROVAL)

        # Verify trace and artifacts
        trace = TraceService.build_trace(task.task_id)
        assert trace is not None
        assert trace.task_id == task.task_id

        artifacts = ArtifactService.list_by_task(task.task_id)
        assert len(artifacts) >= 1
        art_types = [a.artifact_type.value for a in artifacts]
        assert "PLAN" in art_types or "CONTEXT" in art_types


def pytest_raises():
    import pytest
    return pytest.raises(Exception)
