"""Deterministic terminal report projected from durable execution evidence.

No model call, status mutation, new execution, or duplicate summary store. Reopening
rebuilds the same versioned representation from the existing persisted records.
"""
from fastapi import HTTPException
from backend.app.db.database import get_db_session
from backend.app.db.models import TaskModel, EventModel, ApprovalModel, ExecutionModel
from backend.app.services.artifact_service import ArtifactService
from backend.app.services.project_service import ProjectService
from backend.app.observability.redaction import redact_secrets

TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}


def build_implementation_report(task_id, owner_id):
    scope = ProjectService.task_scope(task_id, owner_id)
    with get_db_session() as db:
        task = db.get(TaskModel, task_id)
        if task is None:
            raise HTTPException(404, "Task not found")
        if task.status not in TERMINAL:
            raise HTTPException(409, "Implementation report is available when execution ends")
        state, error = task.status, task.error
        dates = {key: getattr(task, key) for key in ("started_at", "completed_at")}
        events = [{"id": e.event_id, "type": e.event_type, "payload": e.payload or {}}
                  for e in db.query(EventModel).filter_by(task_id=task_id).order_by(EventModel.timestamp, EventModel.event_id)]
        approvals = [{"approval_id": a.approval_id, "status": a.status}
                     for a in db.query(ApprovalModel).filter_by(task_id=task_id).order_by(ApprovalModel.created_at, ApprovalModel.approval_id)]
        tools = [{"execution_id": e.execution_id, "tool": e.tool_name, "operation": e.operation,
                  "status": e.status, "error": e.error}
                 for e in db.query(ExecutionModel).filter_by(task_id=task_id).order_by(ExecutionModel.started_at, ExecutionModel.execution_id)]
    # Integrity verification is deliberately retained; corrupted evidence cannot become a report.
    artifacts = ArtifactService.list_by_task(task_id)
    artifacts.sort(key=lambda a: (a.created_at, a.artifact_id))
    patches = {a.content.get("patch_id"): a for a in artifacts if a.artifact_type.value == "PATCH" and a.content.get("patch_id")}
    files = {}
    for event in events:
        data = event["payload"]
        if event["type"] != "PATCH_APPLIED" or data.get("applied") is not True:
            continue
        patch = patches.get(data.get("patch_id"))
        for path in data.get("files", data.get("modified_files", [])) or []:
            if not isinstance(path, str):
                continue
            entry = files.setdefault(path, {"path": path, "additions": 0, "deletions": 0, "diffs": [], "evidence_ids": []})
            entry["evidence_ids"].append(event["id"])
            matching = next((f for f in patch.content.get("files", []) if isinstance(f, dict) and f.get("relative_path") == path), None) if patch else None
            if matching is None:
                entry["additions"] = entry["deletions"] = None
                continue
            if patch.artifact_id in entry["diffs"]:
                continue
            entry["diffs"].append(patch.artifact_id)
            lines = [line for h in matching.get("hunks", []) for line in h.get("lines", []) if isinstance(line, str)]
            if entry["additions"] is not None:
                entry["additions"] += sum(line.startswith("+") for line in lines)
                entry["deletions"] += sum(line.startswith("-") for line in lines)
    tests, reviews, commands = [], [], []
    review_concerns = []
    for artifact in artifacts:
        content, kind = artifact.content, artifact.artifact_type.value
        if kind == "TEST_REPORT":
            test = {key: content.get(key) for key in ("command", "passed_count", "failed_count", "skipped_count", "exit_code", "duration_seconds")}
            test.update(artifact_id=artifact.artifact_id, passed=content.get("passed") is True and content.get("exit_code") == 0 and not content.get("failed_count") and not content.get("error_count"))
            tests.append(test)
            if test["command"]:
                commands.append({"command": test["command"], "exit_code": test["exit_code"], "status": "PASSED" if test["passed"] else "FAILED", "artifact_id": artifact.artifact_id})
        elif kind == "REVIEW":
            review_concerns = [str(item) for item in content.get("security_concerns", [])]
            reviews.append({"artifact_id": artifact.artifact_id, "status": "APPROVED" if content.get("approved") is True else "NOT_APPROVED" if content.get("approved") is False else "RECORDED", "summary": content.get("summary")})
    issues = ["Review concern: " + concern for concern in review_concerns]
    security = [a for a in artifacts if a.artifact_type.value == "SECURITY_FINDINGS"]
    if security and security[-1].content.get("passed") is False:
        issues.append(f"The latest recorded security check failed; see {security[-1].artifact_id}.")
    if error:
        issues.append(error)
    if state == "CANCELLED":
        issues.append("Execution was cancelled; any applied changes listed below remain recorded.")
    if state == "FAILED" and not error:
        issues.append("Task execution failed; inspect the recorded evidence.")
    latest_tests = {}
    for test in tests:
        latest_tests[str(test["command"])] = test
    for test in latest_tests.values():
        if not test["passed"]:
            issues.append(f"Latest test run failed or is unverified (exit {test['exit_code']}); see {test['artifact_id']}.")
    if not tests:
        issues.append("No test results were recorded; verification is not established.")
    if reviews and reviews[-1]["status"] == "NOT_APPROVED":
        issues.append("The latest recorded review did not approve the work.")
    if any(a["status"] == "PENDING" for a in approvals):
        issues.append("An approval remains pending.")
    warnings = []
    if any(tool["error"] or str(tool["status"]).lower() in {"failed", "timeout", "cancelled"} for tool in tools):
        warnings.append("Tool execution failures were recorded; inspect their outcomes below.")
    if any(not t["passed"] for t in tests) and latest_tests and all(t["passed"] for t in latest_tests.values()):
        warnings.append("Earlier failing test runs are retained; the latest recorded runs passed.")
    report_status = "COMPLETED_WITH_WARNINGS" if state == "COMPLETED" and (issues or warnings) else state
    changes = [{"category": "Applied changes", "description": f"Applied recorded patch changes to {len(files)} file(s)."}] if files else []
    if tests:
        changes.append({"category": "Verification", "description": f"Recorded {len(tests)} test run(s); individual results are listed below."})
    if reviews:
        changes.append({"category": "Review", "description": f"Recorded {len(reviews)} review artifact(s)."})
    summary = {"COMPLETED": "Task completed.", "FAILED": "Task failed.", "CANCELLED": "Task cancelled."}[state]
    summary += f" {len(files)} file(s) have confirmed applied changes; {len(tests)} test run(s) recorded."
    return redact_secrets({"schema_version": 1, "report_id": f"implementation:{task_id}", "task_id": task_id, **scope,
        "task_status": state, "status": report_status, "summary": summary, **dates, "changes": changes,
        "files_changed": list(files.values()), "commands": commands, "tools": tools, "tests": tests,
        "approvals": approvals, "reviews": reviews,
        "artifacts": [{"artifact_id": a.artifact_id, "type": a.artifact_type.value, "label": a.artifact_type.value.replace("_", " ").title()} for a in artifacts],
        "remaining_issues": issues, "warnings": warnings})
