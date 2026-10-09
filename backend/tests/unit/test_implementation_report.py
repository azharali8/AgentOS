from uuid import uuid4
import pytest
from fastapi import HTTPException
from backend.app.config.settings import settings
from backend.app.models.task import TaskRequest, TaskStatus
from backend.app.services.task_service import TaskService
from backend.app.services.project_service import ProjectService
from backend.app.services.event_service import EventService
from backend.app.services.artifact_service import ArtifactService, ArtifactType
from backend.app.services.implementation_report import build_implementation_report

@pytest.fixture
def session_task(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(tmp_path))
    owner = uuid4().hex
    project = ProjectService.register(tmp_path, "Report project", owner)
    task = TaskService.create_task(TaskRequest(instruction="Proposed work is not evidence"))
    ProjectService.attach_task(task.task_id, project["project_id"], None, owner, task.user_request)
    return task.task_id, owner, project

def save(task, kind, content):
    return ArtifactService.save(task_id=task, agent_id="testing", artifact_type=kind, content=content)

def test_report_requires_terminal_state_and_owner(session_task):
    task, owner, _ = session_task
    with pytest.raises(HTTPException) as error:
        build_implementation_report(task, owner)
    assert error.value.status_code == 409
    TaskService.set_final_response(task, "LLM claims 500 tests passed")
    report = build_implementation_report(task, owner)
    assert report["status"] == "COMPLETED_WITH_WARNINGS"
    assert report["tests"] == [] and report["files_changed"] == []
    assert "500" not in str(report)
    with pytest.raises(HTTPException) as error:
        build_implementation_report(task, "another-owner")
    assert error.value.status_code == 404

def test_applied_files_only_have_exact_diff_counts_and_links(session_task):
    task, owner, _ = session_task
    patch = save(task, ArtifactType.PATCH, {"patch_id":"p", "files":[{"relative_path":"app.py","hunks":[{"lines":[" context", "-old", "+new", "+next"]}]}]})
    save(task, ArtifactType.PATCH, {"patch_id":"unapplied", "files":[{"relative_path":"secret.py","hunks":[]}]})
    EventService.record_event(task,"PATCH_APPLIED",payload={"applied":True,"patch_id":"p","files":["app.py"]})
    EventService.record_event(task,"PATCH_APPLIED",payload={"applied":False,"patch_id":"unapplied","files":["secret.py"]})
    TaskService.set_error(task,"Retest failed")
    report=build_implementation_report(task,owner)
    assert report["status"] == "FAILED"
    assert report["files_changed"][0]["path"] == "app.py"
    assert report["files_changed"][0]["additions"] == 2
    assert report["files_changed"][0]["deletions"] == 1
    assert report["files_changed"][0]["diffs"] == [patch.artifact_id]
    assert len(report["files_changed"]) == 1
    assert "Retest failed" in report["remaining_issues"]

def test_test_runs_commands_approvals_reviews_and_restoration(session_task):
    from backend.app.models.approval import ApprovalRequest, ApprovalStatus
    from backend.app.models.tool import RiskLevel
    from backend.app.security.approval import ApprovalManager
    task, owner, project=session_task
    failed=save(task,ArtifactType.TEST_REPORT,{"command":"python -m pytest", "passed":False,"passed_count":8,"failed_count":1,"exit_code":1})
    passed=save(task,ArtifactType.TEST_REPORT,{"command":"python -m pytest", "passed":True,"passed_count":9,"failed_count":0,"exit_code":0})
    review=save(task,ArtifactType.REVIEW,{"approved":True,"summary":"Recorded review", "reasoning":"PRIVATE"})
    aid=str(uuid4())
    ApprovalManager.request_approval(ApprovalRequest(approval_id=aid,task_id=task,step_id="s",tool_name="patch.apply",operation="apply",arguments_hash="",arguments_summary={},risk_level=RiskLevel.HIGH,reason="Apply patch"))
    ApprovalManager.resolve_approval(aid,ApprovalStatus.APPROVED,resolved_by=owner)
    TaskService.set_final_response(task,"Do not use prose as evidence")
    report=build_implementation_report(task,owner)
    assert report["status"] == "COMPLETED_WITH_WARNINGS"
    assert [t["passed"] for t in report["tests"]] == [False,True]
    assert [t["exit_code"] for t in report["commands"]] == [1,0]
    assert report["approvals"] == [{"approval_id":aid,"status":"APPROVED"}]
    assert report["reviews"][0]["status"] == "APPROVED"
    assert report["remaining_issues"] == [] and report["warnings"]
    assert "PRIVATE" not in str(report)
    assert {a["artifact_id"] for a in report["artifacts"]} == {failed.artifact_id,passed.artifact_id,review.artifact_id}
    ProjectService.deselect(owner)
    assert build_implementation_report(task,owner) == report
    assert report["project_id"] == project["project_id"]

def test_mixed_test_counts_never_become_success(session_task):
    task,owner,_=session_task
    save(task,ArtifactType.TEST_REPORT,{"command":"pytest", "passed":True,"passed_count":8,"failed_count":1,"exit_code":0})
    TaskService.set_final_response(task,"done")
    report=build_implementation_report(task,owner)
    assert report["tests"][0]["passed"] is False
    assert report["status"] == "COMPLETED_WITH_WARNINGS" and report["remaining_issues"]

def test_cancelled_and_legacy_applied_evidence_do_not_invent_counts(session_task):
    task,owner,_=session_task
    EventService.record_event(task,"PATCH_APPLIED",payload={"applied":True,"files":["legacy.py"]})
    TaskService.update_task_status(task,TaskStatus.CANCELLED)
    report=build_implementation_report(task,owner)
    assert report["status"] == "CANCELLED"
    assert report["files_changed"][0]["additions"] is None
    assert report["files_changed"][0]["diffs"] == []
    assert report["reviews"] == [] and report["commands"] == []


def test_tool_failure_and_review_security_findings_are_not_hidden(session_task):
    from datetime import datetime, timezone
    from backend.app.db.database import get_db_session
    from backend.app.db.models import ExecutionModel
    task, owner, _ = session_task
    with get_db_session() as db:
        db.add(ExecutionModel(execution_id=str(uuid4()), task_id=task, step_id="s", tool_name="file.read", operation="read", status="FAILED", error="File missing", started_at=datetime.now(timezone.utc)))
        db.commit()
    save(task, ArtifactType.REVIEW, {"approved": True, "security_concerns": ["Missing validation"]})
    finding = save(task, ArtifactType.SECURITY_FINDINGS, {"passed": False, "sensitive_files": [".env"]})
    TaskService.set_final_response(task, "done")
    report = build_implementation_report(task, owner)
    assert report["tools"][0]["error"] == "File missing"
    assert report["commands"] == []  # Never guess a command from a tool name.
    assert "Review concern: Missing validation" in report["remaining_issues"]
    assert any(finding.artifact_id in issue for issue in report["remaining_issues"])
    assert report["warnings"] and report["status"] == "COMPLETED_WITH_WARNINGS"


def test_followup_task_does_not_overwrite_or_inherit_report(session_task):
    task, owner, project = session_task
    save(task, ArtifactType.TEST_REPORT, {"command":"pytest first.py", "passed":True, "passed_count":1, "exit_code":0})
    TaskService.set_final_response(task, "first complete")
    first = build_implementation_report(task, owner)
    followup = TaskService.create_task(TaskRequest(instruction="A separate follow-up"))
    ProjectService.attach_task(followup.task_id, project["project_id"], first["conversation_id"], owner, followup.user_request)
    TaskService.set_error(followup.task_id, "Follow-up failed")
    second = build_implementation_report(followup.task_id, owner)
    assert second["tests"] == [] and second["status"] == "FAILED"
    assert second["report_id"] != first["report_id"]
    assert build_implementation_report(task, owner) == first
