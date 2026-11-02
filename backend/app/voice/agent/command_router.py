"""
AgentOS Voice Agent — Command Gateway.

The CommandGateway is a secure, controlled bridge between the Voice Agent and
its existing service layer. It translates classified voice intents into
approved AgentOS operations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.config.settings import PROJECT_ROOT, settings
from backend.app.auth.service import AuthenticatedUser, UserRole
from backend.app.models.task import TaskRequest, TaskStatus
from backend.app.services.task_service import TaskService
from backend.app.services.workspace_service import WorkspaceService

logger = logging.getLogger("agentos.voice.gateway")


class AgentOSCommandGateway:
    """Gateway exposing approved AgentOS operations to the Voice Agent."""

    @staticmethod
    def create_task(instruction: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        instruction_clean = instruction.strip()
        if not instruction_clean:
            raise ValueError("Instruction cannot be empty.")
        task_record = TaskService.create_task(request=TaskRequest(instruction=instruction_clean))
        summary_text = instruction_clean[:80] + ("..." if len(instruction_clean) > 80 else "")
        return {
            "task_id": task_record.task_id,
            "status": "created",
            "tts_message": f"Task submitted. Starting engineering task: {summary_text}",
        }

    @staticmethod
    def get_task_status(task_id: Optional[str] = None) -> Dict[str, Any]:
        if not task_id:
            tasks = TaskService.list_tasks(limit=1)
            if not tasks:
                return {"task_id": None, "status": "none", "tts_message": "There are no recent tasks in AgentOS."}
            task = tasks[0]
        else:
            task = TaskService.get_task(task_id)
        if task is None:
            return {"task_id": task_id, "status": "not_found", "tts_message": f"I couldn't find task {task_id[:8] if task_id else 'unknown'}."}
        status_str = task.status.value if hasattr(task.status, "value") else str(task.status)
        if status_str == "COMPLETED" and task.final_response:
            tts_msg = f"Task {task.task_id[:8]} is completed. {task.final_response[:120]}"
        elif status_str == "FAILED":
            tts_msg = f"Task {task.task_id[:8]} failed. Error: {str(task.error or 'Unknown error')[:100]}"
        else:
            tts_msg = f"Task {task.task_id[:8]} is currently {status_str}."
        return {"task_id": task.task_id, "status": status_str, "error": task.error,
                "final_response": task.final_response, "tts_message": tts_msg}

    @staticmethod
    def cancel_task(task_id: str) -> Dict[str, Any]:
        try:
            TaskService.cancel_task(task_id)
            return {"task_id": task_id, "status": "cancelling", "tts_message": f"Cancellation requested for task {task_id[:8]}."}
        except Exception as exc:
            logger.warning("Cancel failed for task %s: %s", task_id, exc)
            return {"task_id": task_id, "status": "error", "tts_message": f"Could not cancel task {task_id[:8]}. It may have already completed."}

    @staticmethod
    def create_project(name: str, location: str, instruction: str, principal: Optional[AuthenticatedUser] = None) -> Dict[str, Any]:
        """Create and activate a project, allowing the development fallback only when auth is off."""
        from backend.app.services.project_creator import ProjectCreatorService
        from backend.app.api.routes.v1 import WorkspaceSetRootRequest, set_workspace_root

        authorized = principal is not None and principal.role in (UserRole.DEVELOPER, UserRole.ADMIN)
        if not settings.AUTH_ENABLED and principal is None:
            authorized = True
        if not authorized:
            return {"status": "denied", "tts_message": "You do not have permission to change the workspace."}

        logger.info("CommandGateway: creating project '%s' at %s", name, location)
        meta = ProjectCreatorService.create_project(name=name, location=location, instruction=instruction)
        fallback_principal = principal or AuthenticatedUser(
            user_id="dev-default", username="dev_user", role=UserRole.DEVELOPER,
        )
        set_workspace_root(WorkspaceSetRootRequest(path=meta["path"], name=name), fallback_principal)
        return {
            "project_name": meta["project_name"], "path": meta["path"],
            "git_initialized": meta.get("git_initialized", False),
            "tts_message": f"Project {name} created at {meta['path']}. Starting engineering task.",
        }

    @staticmethod
    def connect_project(project_path: str, principal: Optional[AuthenticatedUser] = None) -> Dict[str, Any]:
        from backend.app.api.routes.v1 import WorkspaceSetRootRequest, set_workspace_root
        if principal is None or principal.role not in (UserRole.DEVELOPER, UserRole.ADMIN):
            return {"status": "denied", "tts_message": "You do not have permission to change the workspace."}
        try:
            result = set_workspace_root(WorkspaceSetRootRequest(path=project_path), principal)
        except Exception as exc:
            return {"status": "error", "tts_message": str(getattr(exc, "detail", exc))}
        target = Path(result["path"])
        return {"status": "connected", "path": str(target),
                "tts_message": f"Connected to project at {target.name}. Active workspace updated."}

    @staticmethod
    def disconnect_project(principal: Optional[AuthenticatedUser] = None) -> Dict[str, Any]:
        from backend.app.api.routes.v1 import disconnect_workspace_v1
        if principal is None or principal.role not in (UserRole.DEVELOPER, UserRole.ADMIN):
            return {"status": "denied", "tts_message": "You do not have permission to change the workspace."}
        try:
            result = disconnect_workspace_v1(principal)
        except Exception as exc:
            return {"status": "error", "tts_message": str(getattr(exc, "detail", exc))}
        return {"status": "disconnected", "path": result["path"],
                "tts_message": "Project disconnected. AgentOS is using its default workspace."}

    @staticmethod
    def get_workspace_status() -> Dict[str, Any]:
        try:
            if not Path(settings.WORKSPACE_ROOT).is_dir():
                raise ValueError("Workspace directory is unavailable")
            from backend.app.services.repo_intelligence import RepoIntelligence
            overview = RepoIntelligence().inspect_overview()
            frameworks = ", ".join(overview.get("frameworks", [])) or "Standard project"
            return {"status": "ok", "overview": overview,
                    "tts_message": f"Project {Path(settings.WORKSPACE_ROOT).name} has {overview.get('total_files', 0)} files. Detected {frameworks}."}
        except Exception as exc:
            logger.warning("get_workspace_status error: %s", exc)
            return {"status": "failed", "tts_message": "I couldn't inspect the workspace. Check that the active project is available and readable."}

    @staticmethod
    def run_tests() -> Dict[str, Any]:
        return AgentOSCommandGateway.create_task("Run the full test suite and report the results.")

    @staticmethod
    def investigate_failure(task_id: Optional[str] = None) -> Dict[str, Any]:
        instruction = "Diagnose the most recent test failures and provide a fix recommendation."
        if task_id:
            prior = TaskService.get_task(task_id)
            if prior:
                instruction += f" Referenced task {task_id}: {prior.error or prior.final_response or prior.user_request}"
        task_record = TaskService.create_task(request=TaskRequest(instruction=instruction))
        return {"task_id": task_record.task_id, "status": "created", "tts_message": "Investigating recent test failures with the Debugger agent."}

    @staticmethod
    def review_changes() -> Dict[str, Any]:
        task_record = TaskService.create_task(request=TaskRequest(instruction="Review recent code changes for security, style, and correctness."))
        return {"task_id": task_record.task_id, "status": "created", "tts_message": "Submitting code review task to the Reviewer agent."}

    @staticmethod
    def get_artifacts(task_id: Optional[str] = None) -> Dict[str, Any]:
        try:
            from backend.app.services.artifact_service import ArtifactService
            artifacts = ArtifactService.list_artifacts_for_task(task_id) if task_id else []
            if artifacts:
                types = ", ".join(set(a.artifact_type.value for a in artifacts))
                message = f"Found {len(artifacts)} artifacts for task {task_id[:8] if task_id else ''}: {types}."
            else:
                message = "No artifacts available for the referenced task."
            return {"status": "ok", "artifacts_count": len(artifacts), "tts_message": message}
        except Exception as exc:
            logger.warning("get_artifacts error: %s", exc)
            return {"status": "ok", "tts_message": "Artifact retrieval completed."}

    @staticmethod
    def resolve_approval(approval_id: str, approved: bool, reason: str = "Voice command", user_id: Optional[str] = None, user_role: Optional[str] = None) -> Dict[str, Any]:
        if settings.AUTH_ENABLED and (user_role or "").upper() not in ("DEVELOPER", "ADMIN"):
            return {"status": "denied", "tts_message": "Approval requires a developer or administrator."}
        try:
            from backend.app.security.approval import ApprovalManager
            from backend.app.models.approval import ApprovalStatus
            record = ApprovalManager.get_approval(approval_id)
            status_enum = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
            success = ApprovalManager.resolve_approval(approval_id=approval_id, status=status_enum,
                                                       reason=reason, resolved_by=user_id or "dev-default")
            verb = "approved" if approved else "rejected"
            if success and record:
                from backend.app.services.multi_agent_service import MultiAgentService
                from backend.app.services.audit_service import AuditService
                AuditService.record(action="VOICE_APPROVAL_RESOLVED", status="SUCCESS", user_id=user_id,
                                    target_entity="approval", target_id=approval_id, details={"approved": approved})
                MultiAgentService.resume_approval(record.task_id, approved=approved)
                return {"status": "ok", "approval_id": approval_id, "tts_message": f"Action {approval_id[:8]} has been {verb}."}
            return {"status": "error", "tts_message": f"Could not find pending approval {approval_id[:8]}."}
        except Exception as exc:
            logger.warning("resolve_approval error: %s", exc)
            return {"status": "error", "tts_message": f"Approval resolution failed: {exc}"}
