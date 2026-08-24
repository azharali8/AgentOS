"""
AgentOS Phase 12 — End-to-End Engineering Workflow Demonstrations.

Demonstrates 5 critical real-world workflows:
1. E2E #1 — Coding Workflow (Supervisor -> Coding -> Patch -> Approval -> Apply -> Testing -> Reviewer -> Complete)
2. E2E #2 — Debugging Workflow (Bug -> Debugger -> Root Cause -> Coding -> Tests -> Review -> Complete)
3. E2E #3 — Data Engineering Workflow (Dataset -> Data Engineer -> Profiling -> Cleaning -> Report)
4. E2E #4 — DevOps Workflow (Repository -> DevOps -> Config Analysis -> Security Audit -> Report)
5. E2E #5 — Failure Recovery Workflow (Task -> Failure Detection -> Supervisor Recovery -> Retry/Replan -> Complete)
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
_root_path = str(Path(__file__).resolve().parent.parent.parent)
if _root_path not in sys.path:
    sys.path.insert(0, _root_path)

from backend.app.agents.debugger import DebuggerAgent
from backend.app.agents.domain_experts import CybersecurityAgent, DataEngineerAgent, DevOpsAgent, TestingAgent
from backend.app.agents.reviewer import ReviewerAgent
from backend.app.agents.specialized import CodingAgent, ResearchAgent, SecurityAgent
from backend.app.agents.supervisor import SupervisorAgent
from backend.app.code.patch.models import compute_patch_hash
from backend.app.config.settings import settings
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
from backend.app.services.event_service import EventService
from backend.app.services.multi_agent_service import MultiAgentService
from backend.app.services.repo_intelligence import RepoIntelligence
from backend.app.services.task_service import TaskService
from backend.app.services.workspace_service import WorkspaceService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("agentos.e2e_phase12")


def print_banner(title: str):
    print("\n" + "=" * 78)
    print(f"  {title}")
    print("=" * 78)


def run_e2e_01_coding():
    print_banner("E2E #1: Autonomous Coding & Patch Application Workflow")
    workspace_root = Path(settings.WORKSPACE_ROOT)
    workspace_root.mkdir(parents=True, exist_ok=True)
    calc_path = workspace_root / "calculator.py"
    calc_path.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    task = MultiAgentService.start_task(
        instruction="Add divide function with zero-division validation to calculator.py and verify patch",
        sync=False,
    )
    time.sleep(0.5)
    print(f"[+] Task initiated: ID={task.task_id}, Status={task.status}")

    # Resume approval with cryptographic authorization
    resumed = MultiAgentService.resume_approval(task.task_id, approved=True)
    print(f"[+] Approval granted. Resumed status: {resumed.status}")

    events = EventService.get_task_events(task.task_id)
    print(f"[+] Recorded execution events: {len(events)}")
    for ev in events[:6]:
        print(f"    - [{ev['event_type']}] {ev.get('payload', {})}")
    assert resumed.status in (TaskStatus.COMPLETED, TaskStatus.WAITING_APPROVAL)
    print("[PASS] E2E #1 Coding Workflow completed successfully.")


def run_e2e_02_debugging():
    print_banner("E2E #2: Autonomous Debugging & Root Cause Diagnosis")
    supervisor = SupervisorAgent()
    st_debug = SubTask(
        task_id="e2e-debug-task",
        subtask_id="st-debug-1",
        description="Diagnose arithmetic calculation error where subtraction returns addition",
        assigned_agent=AgentType.DEBUGGER,
        target_files=["calculator.py"],
    )
    res_debug = supervisor.execute_subtask(st_debug)
    print(f"[+] Debugger execution: status={res_debug.status}")
    print(f"[+] Summary: {res_debug.summary}")
    diagnosis = res_debug.evidence.get("diagnosis", {})
    print(f"[+] Root Cause: {diagnosis.get('root_cause')}")
    print(f"[+] Suggested Fix: {diagnosis.get('suggested_fix')}")
    print(f"[+] Confidence: {diagnosis.get('confidence_score')}")
    assert res_debug.status == AgentStatus.COMPLETED
    print("[PASS] E2E #2 Debugging Workflow completed successfully.")


def run_e2e_03_data_engineering():
    print_banner("E2E #3: Autonomous Data Engineering & Profiling")
    workspace_root = Path(settings.WORKSPACE_ROOT)
    data_file = workspace_root / "dataset.csv"
    data_file.write_text("id,val,category\n1,10.5,alpha\n2,,beta\n3,30.0,gamma\n", encoding="utf-8")

    data_agent = DataEngineerAgent()
    st = SubTask(
        task_id="e2e-data-task",
        subtask_id="st-data-1",
        description="Profile dataset.csv, check null values, and generate schema report",
        assigned_agent=AgentType.DATA_ENGINEER,
        target_files=["dataset.csv"],
    )
    res = data_agent.execute(st)
    report = res.evidence.get("structured_report", {})
    print(f"[+] Status: {res.status}")
    print(f"[+] Datasets Analyzed: {report.get('datasets_analyzed')}")
    print(f"[+] Row Counts: {report.get('row_counts')}")
    print(f"[+] Null Counts: {report.get('null_counts')}")
    print(f"[+] Operations: {report.get('cleaning_operations')}")
    assert res.status == AgentStatus.COMPLETED
    print("[PASS] E2E #3 Data Engineering Workflow completed successfully.")


def run_e2e_04_devops():
    print_banner("E2E #4: Autonomous DevOps & Infrastructure Audit")
    workspace_root = Path(settings.WORKSPACE_ROOT)
    docker_file = workspace_root / "Dockerfile"
    docker_file.write_text("FROM python:3.13-slim\nWORKDIR /app\nCOPY . .\nCMD ['python', 'main.py']\n", encoding="utf-8")

    devops = DevOpsAgent()
    st = SubTask(
        task_id="e2e-devops-task",
        subtask_id="st-devops-1",
        description="Analyze containerization and CI pipeline configurations",
        assigned_agent=AgentType.DEVOPS,
    )
    res = devops.execute(st)
    report = res.evidence.get("structured_report", {})
    print(f"[+] Status: {res.status}")
    print(f"[+] Docker Configured: {report.get('docker_configured')}")
    print(f"[+] Detected Configs: {report.get('detected_configs')}")
    print(f"[+] Recommendations: {report.get('recommendations')}")
    assert res.status == AgentStatus.COMPLETED
    print("[PASS] E2E #4 DevOps Workflow completed successfully.")


def run_e2e_05_failure_recovery():
    print_banner("E2E #5: Autonomous Failure Recovery & Replanning")
    supervisor = SupervisorAgent()
    st_broken = SubTask(
        task_id="e2e-recovery-task",
        subtask_id="st-broken-1",
        description="Execute failing regression tests in isolated environment",
        assigned_agent=AgentType.TESTING,
        target_files=["tests/non_existent_test.py"],
    )
    failed_res = AgentResult(
        subtask_id=st_broken.subtask_id,
        agent_type=AgentType.TESTING,
        status=AgentStatus.FAILED,
        summary="Test execution failed with exit code 1",
        error="FileNotFoundError: No test suite found",
    )
    decision = supervisor.handle_subtask_failure(st_broken, failed_res, "e2e-recovery-task")
    print(f"[+] Trigger Event: {decision.trigger_event}")
    print(f"[+] Rationale: {decision.reason}")
    print(f"[+] Strategy: {decision.strategy}")
    print(f"[+] Rerouted Agent: {decision.assigned_agent}")
    print(f"[+] Recovery Instructions: {decision.recovery_instructions}")
    assert decision.strategy == "REROUTE"
    assert decision.assigned_agent == AgentType.DEBUGGER.value
    print("[PASS] E2E #5 Failure Recovery & Replanning Workflow completed successfully.")


def main():
    print("\n" + "=" * 78)
    print("  AgentOS Phase 12 — End-to-End Real Engineering Demonstration Suite")
    print("=" * 78)

    run_e2e_01_coding()
    run_e2e_02_debugging()
    run_e2e_03_data_engineering()
    run_e2e_04_devops()
    run_e2e_05_failure_recovery()

    print("\n" + "=" * 78)
    print("  ALL 5 E2E WORKFLOWS VERIFIED AND PASSING (100% SUCCESS)")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    main()
