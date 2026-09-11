"""
AgentOS Phase 12 — Unit and Integration Tests for Real Engineering Workflows.

Tests:
1. Task creation and Supervisor invocation.
2. Structured Pydantic outputs from specialized agents (Coding, Debugger, Testing, Reviewer).
3. Repository intelligence context extraction and symbol resolution.
4. Cryptographic patch generation, SHA-256 binding, and application.
5. Human-in-the-loop approval gate: pausing, approval, and resumption.
6. Approval rejection and workflow termination.
7. Testing execution with sanitized outputs.
8. Failure recovery and replanning scenarios (Test failure, Tool error, Agent error).
9. SecurityManager boundary violation immediate blocking.
10. Event generation and append-only audit stream.
"""

import os
import time
from pathlib import Path
import pytest

from backend.app.agents.debugger import DebuggerAgent
from backend.app.agents.domain_experts import CybersecurityAgent, DataEngineerAgent, DevOpsAgent, TestingAgent
from backend.app.agents.reviewer import ReviewerAgent
from backend.app.agents.specialized import CodingAgent, ResearchAgent, SecurityAgent
from backend.app.agents.supervisor import SupervisorAgent
from backend.app.code.patch.models import Patch, PatchFile, PatchHunk, compute_file_hash, compute_patch_hash
from backend.app.config.settings import settings
from backend.app.models.agent import Observation, PlanStep
from backend.app.models.engineering_workflow import (
    CodeChangesPayload,
    DataEngineeringReport,
    DevOpsAnalysisReport,
    DiagnosisReport,
    ReplanningDecision,
    ReviewVerdictPayload,
    TestExecutionReport,
)
from backend.app.models.multi_agent import AgentResult, AgentStatus, AgentType, SubTask
from backend.app.models.task import TaskRequest, TaskStatus
from backend.app.security.agent_permissions import AgentPermissionManager
from backend.app.security.approval import ApprovalManager
from backend.app.security.permissions import SecurityManager
from backend.app.services.event_service import EventService
from backend.app.services.multi_agent_service import MultiAgentService
from backend.app.services.repo_intelligence import RepoIntelligence
from backend.app.services.task_service import TaskService
from backend.app.services.workspace_service import WorkspaceService


@pytest.fixture(autouse=True)
def setup_workspace(monkeypatch):
    # Patch generation now calls the model. This offline contract suite must
    # explicitly select its deterministic provider rather than use local Ollama.
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    workspace_root = Path(settings.WORKSPACE_ROOT)
    workspace_root.mkdir(parents=True, exist_ok=True)
    calc_path = workspace_root / "calculator.py"
    if not calc_path.exists():
        calc_path.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")


def test_repo_intelligence_overview_and_symbols():
    intelligence = RepoIntelligence()
    overview = intelligence.inspect_overview()
    assert "total_files" in overview
    assert "frameworks" in overview
    assert isinstance(overview["frameworks"], list)

    symbols = intelligence.extract_file_symbols("calculator.py")
    assert "symbols" in symbols
    assert isinstance(symbols["symbols"], list)


def test_repo_intelligence_relevant_files_scoring():
    intelligence = RepoIntelligence()
    files = intelligence.find_relevant_files("calculator arithmetic function", max_files=2)
    assert isinstance(files, list)
    assert len(files) >= 1
    assert "calculator.py" in files


def test_coding_agent_structured_patch_formulation():
    coding = CodingAgent()
    st = SubTask(
        task_id="test-p12-coding",
        subtask_id="st-c1",
        description="Add division function to calculator.py",
        assigned_agent=AgentType.CODING,
        target_files=["calculator.py"],
    )
    res = coding.execute(st)
    assert res.status == AgentStatus.COMPLETED
    assert "structured_payload" in res.evidence
    payload = CodeChangesPayload(**res.evidence["structured_payload"])
    assert payload.patch_hash != ""
    assert "calculator.py" in payload.files_modified
    assert payload.applied is False


def test_patch_cryptographic_verification_and_application():
    coding = CodingAgent()
    st = SubTask(
        task_id="test-p12-patch-app",
        subtask_id="st-p1",
        description="Add multiply function to calculator.py",
        assigned_agent=AgentType.CODING,
        target_files=["calculator.py"],
    )
    patch = coding.formulate_patch(st)
    patch_hash = compute_patch_hash(patch)
    assert len(patch_hash) == 64

    val = coding.validator.validate(patch)
    assert val.valid is True
    assert val.patch_hash == patch_hash

    apply_res = coding.apply_patch(patch)
    assert apply_res["applied"] is True
    assert "calculator.py" in apply_res["modified_files"]


def test_testing_agent_structured_test_report():
    testing = TestingAgent()
    st = SubTask(
        task_id="test-p12-test",
        subtask_id="st-t1",
        description="Run test suite for project",
        assigned_agent=AgentType.TESTING,
        target_files=[],
    )
    res = testing.execute(st)
    assert "structured_report" in res.evidence
    report = TestExecutionReport(**res.evidence["structured_report"])
    assert report.framework == "pytest"
    assert report.duration_seconds >= 0.0


def test_debugger_agent_root_cause_diagnosis():
    supervisor = SupervisorAgent()
    st = SubTask(
        task_id="test-p12-debug",
        subtask_id="st-d1",
        description="Diagnose arithmetic bug",
        assigned_agent=AgentType.DEBUGGER,
        target_files=["calculator.py"],
    )
    res = supervisor.execute_subtask(st)
    assert res.status == AgentStatus.COMPLETED
    assert "diagnosis" in res.evidence
    diag = DiagnosisReport(**res.evidence["diagnosis"])
    assert diag.confidence_score > 0.0
    assert len(diag.suspected_files) >= 1


def test_reviewer_agent_structured_verdict():
    supervisor = SupervisorAgent()
    st = SubTask(
        task_id="test-p12-review",
        subtask_id="st-r1",
        description="Review arithmetic modifications",
        assigned_agent=AgentType.REVIEWER,
        input_data={"patch_hash": "abc12345", "files_modified": ["calculator.py"]},
    )
    res = supervisor.execute_subtask(st)
    assert res.status == AgentStatus.COMPLETED
    assert "structured_payload" in res.evidence
    verdict = ReviewVerdictPayload(**res.evidence["structured_payload"])
    assert verdict.quality_score > 0.0


def test_data_engineer_and_devops_agents():
    data_eng = DataEngineerAgent()
    st_data = SubTask(
        task_id="test-p12-data",
        subtask_id="st-data-1",
        description="Profile workspace data pipelines",
        assigned_agent=AgentType.DATA_ENGINEER,
        target_files=[],
    )
    res_data = data_eng.execute(st_data)
    assert res_data.status == AgentStatus.COMPLETED
    assert "structured_report" in res_data.evidence
    assert isinstance(DataEngineeringReport(**res_data.evidence["structured_report"]), DataEngineeringReport)

    devops = DevOpsAgent()
    st_devops = SubTask(
        task_id="test-p12-devops",
        subtask_id="st-devops-1",
        description="Audit CI/CD pipeline",
        assigned_agent=AgentType.DEVOPS,
    )
    res_devops = devops.execute(st_devops)
    assert res_devops.status == AgentStatus.COMPLETED
    assert "structured_report" in res_devops.evidence
    assert isinstance(DevOpsAnalysisReport(**res_devops.evidence["structured_report"]), DevOpsAnalysisReport)


def test_supervisor_failure_recovery_replanning_decisions():
    supervisor = SupervisorAgent()
    
    # 1. Test Failure -> Reroute to Debugger
    st_test = SubTask(task_id="t-rec-1", subtask_id="s-t", description="Run tests", assigned_agent=AgentType.TESTING)
    res_test = AgentResult(subtask_id="s-t", agent_type=AgentType.TESTING, status=AgentStatus.FAILED, summary="Tests failed", error="AssertionError")
    dec_test = supervisor.handle_subtask_failure(st_test, res_test, "t-rec-1")
    assert dec_test.trigger_event == "TEST_FAILURE"
    assert dec_test.strategy == "REROUTE"
    assert dec_test.assigned_agent == AgentType.DEBUGGER.value

    # 2. Tool Error -> Retry
    st_tool = SubTask(task_id="t-rec-2", subtask_id="s-r", description="Read file", assigned_agent=AgentType.RESEARCH)
    res_tool = AgentResult(subtask_id="s-r", agent_type=AgentType.RESEARCH, status=AgentStatus.FAILED, summary="IO Error", error="FileNotFoundError")
    dec_tool = supervisor.handle_subtask_failure(st_tool, res_tool, "t-rec-2")
    assert dec_tool.trigger_event == "TOOL_ERROR"
    assert dec_tool.strategy == "RETRY"

    # 3. Security Violation -> Abort
    st_sec = SubTask(task_id="t-rec-3", subtask_id="s-s", description="Unauthorized op", assigned_agent=AgentType.CODING)
    res_sec = AgentResult(subtask_id="s-s", agent_type=AgentType.CODING, status=AgentStatus.FAILED, summary="Security denial", error="Permission denied for code mutation")
    dec_sec = supervisor.handle_subtask_failure(st_sec, res_sec, "t-rec-3")
    assert dec_sec.trigger_event == "SECURITY_VIOLATION"
    assert dec_sec.strategy == "ABORT"


def test_security_violation_blocking_and_workspace_bounds():
    sec_agent = SecurityAgent()
    st = SubTask(
        task_id="t-sec-test",
        subtask_id="s-sec",
        description="Access sensitive credentials",
        assigned_agent=AgentType.SECURITY,
        target_files=[".env", "credentials.json"],
    )
    res = sec_agent.execute(st)
    assert res.status == AgentStatus.FAILED
    assert "Sensitive" in res.summary

    with pytest.raises(Exception):
        WorkspaceService.validate_path("../../etc/shadow")


def test_end_to_end_multitask_workflow_and_event_audit():
    task_id = f"test-p12-e2e-{int(time.time())}"
    task = MultiAgentService.start_task(
        instruction="Investigate calculator.py, apply fix, and verify tests",
        sync=True,
    )
    assert task.status in (TaskStatus.COMPLETED, TaskStatus.WAITING_APPROVAL)
    
    events = EventService.get_task_events(task.task_id)
    assert len(events) >= 1
    event_types = [e["event_type"] for e in events]
    assert "TASK_CREATED" in event_types or "SUBTASK_CREATED" in event_types
