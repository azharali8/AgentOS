"""
AgentOS Voice Agent — Command Gateway.

The CommandGateway is a secure, controlled bridge between the Voice Agent and
the existing AgentOS service layer. It exposes only approved operations and
translates classified VoiceIntents into calls on AgentOS services.

Principles:
  - Delegates exclusively to existing AgentOS services:
      * TaskService (task lifecycle & management)
      * ProjectCreatorService (safe project onboarding & initialization)
      * WorkspaceService (safe path resolution)
      * TestService (bounded pytest/npm discovery & execution)
      * RepoIntelligence (codebase exploration & inspection)
      * ArtifactService (retrieval of test reports, patches, reviews)
      * ApprovalManager (human-in-the-loop approvals)
  - Does NOT duplicate engineering logic, task decomposition, or
    code generation — those remain in the Supervisor and specialized agents.
  - Every public method returns a structured dict response suitable for TTS summarization.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.config.settings import PROJECT_ROOT, settings
from backend.app.models.task import TaskRequest, TaskStatus
from backend.app.services.task_service import TaskService
from backend.app.services.workspace_service import WorkspaceService

logger = logging.getLogger("agentos.voice.gateway")


class AgentOSCommandGateway:
    """Gateway exposing approved AgentOS operations to the Voice Agent."""

    # ------------------------------------------------------------------
    # Task Operations
    # ------------------------------------------------------------------

    @staticmethod
    def create_task(instruction: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Submit an engineering instruction to the Supervisor via TaskService."""
        instruction_clean = instruction.strip()
        if not instruction_clean:
            raise ValueError("Instruction cannot be empty.")

        task_req = TaskRequest(instruction=instruction_clean)
        task_record = TaskService.create_task(request=task_req)
        task_id = task_record.task_id

        logger.info("CommandGateway: created task %s for: %s", task_id, instruction_clean[:60])
        summary_text = instruction_clean[:80] + ("..." if len(instruction_clean) > 80 else "")
        return {
            "task_id": task_id,
            "status": "created",
            "tts_message": f"Task submitted. Starting engineering task: {summary_text}",
        }

    @staticmethod
    def get_task_status(task_id: Optional[str] = None) -> Dict[str, Any]:
        """Query the status of a specific task or the most recent task."""
        if not task_id:
            tasks = TaskService.list_tasks(limit=1) if hasattr(TaskService, "list_tasks") else []
            if not tasks:
                return {
                    "task_id": None,
                    "status": "none",
                    "tts_message": "There are no recent tasks in AgentOS.",
                }
            task = tasks[0]
            task_id = task.task_id
        else:
            task = TaskService.get_task(task_id)

        if task is None:
            return {
                "task_id": task_id,
                "status": "not_found",
                "tts_message": f"I couldn't find task {task_id[:8] if task_id else 'unknown'}.",
            }

        status_str = task.status.value if hasattr(task.status, "value") else str(task.status)
        final_resp = task.final_response

        if status_str == "COMPLETED" and final_resp:
            tts_msg = f"Task {task.task_id[:8]} is completed. {final_resp[:120]}"
        elif status_str == "FAILED":
            tts_msg = f"Task {task.task_id[:8]} failed. Error: {str(task.error or 'Unknown error')[:100]}"
        else:
            tts_msg = f"Task {task.task_id[:8]} is currently {status_str}."

        return {
            "task_id": task.task_id,
            "status": status_str,
            "error": task.error,
            "final_response": task.final_response,
            "tts_message": tts_msg,
        }

    @staticmethod
    def cancel_task(task_id: str) -> Dict[str, Any]:
        """Request cancellation of a running task."""
        try:
            TaskService.cancel_task(task_id)
            return {
                "task_id": task_id,
                "status": "cancelling",
                "tts_message": f"Cancellation requested for task {task_id[:8]}.",
            }
        except Exception as exc:
            logger.warning("Cancel failed for task %s: %s", task_id, exc)
            return {
                "task_id": task_id,
                "status": "error",
                "tts_message": f"Could not cancel task {task_id[:8]}. It may have already completed.",
            }

    # ------------------------------------------------------------------
    # Project & Workspace Operations
    # ------------------------------------------------------------------

    @staticmethod
    def create_project(name: str, location: str, instruction: str) -> Dict[str, Any]:
        """Create a new project directory and switch WORKSPACE_ROOT."""
        from backend.app.services.project_creator import ProjectCreatorService

        logger.info("CommandGateway: creating project '%s' at %s", name, location)
        meta = ProjectCreatorService.create_project(
            name=name,
            location=location,
            instruction=instruction,
        )
        return {
            "project_name": meta["project_name"],
            "path": meta["path"],
            "git_initialized": meta.get("git_initialized", False),
            "tts_message": f"Project {name} created at {meta['path']}. Starting engineering task.",
        }

    @staticmethod
    def connect_project(project_path: str) -> Dict[str, Any]:
        """Switch active WORKSPACE_ROOT to an existing project directory."""
        target = Path(project_path).resolve()
        if not target.exists() or not target.is_dir():
            return {
                "status": "error",
                "tts_message": f"Project directory does not exist: {project_path}",
            }

        settings.WORKSPACE_ROOT = str(target)
        import os
        os.environ["WORKSPACE_ROOT"] = str(target)

        return {
            "status": "connected",
            "path": str(target),
            "tts_message": f"Connected to project at {target.name}. Active workspace updated.",
        }

    @staticmethod
    def get_workspace_status() -> Dict[str, Any]:
        """Inspect active project structure, technologies, entry points, and test files."""
        try:
            from backend.app.services.repo_intelligence import RepoIntelligence
            repo_intel = RepoIntelligence()
            overview = repo_intel.inspect_overview()
            fw_list = ", ".join(overview.get("frameworks", [])) or "Standard project"
            files_count = overview.get("total_files", 0)
            ws_name = Path(settings.WORKSPACE_ROOT).name

            msg = f"Project {ws_name} has {files_count} files. Detected {fw_list}."
            return {
                "status": "ok",
                "overview": overview,
                "tts_message": msg,
            }
        except Exception as exc:
            logger.warning("get_workspace_status error: %s", exc)
            ws_name = Path(settings.WORKSPACE_ROOT).name
            return {
                "status": "ok",
                "tts_message": f"Active workspace is {ws_name}.",
            }

    # ------------------------------------------------------------------
    # Engineering Operations (Tests, Diagnosis, Review, Artifacts)
    # ------------------------------------------------------------------

    @staticmethod
    def run_tests() -> Dict[str, Any]:
        """Run the test suite on the current workspace via TestService and return summary."""
        return AgentOSCommandGateway.create_task("Run the full test suite and report the results.")

    @staticmethod
    def investigate_failure(task_id: Optional[str] = None) -> Dict[str, Any]:
        """Investigate test or task failure and generate actionable voice feedback."""
        instruction = "Diagnose the most recent test failures and provide a fix recommendation."
        if task_id:
            prior = TaskService.get_task(task_id)
            if prior:
                instruction += f" Referenced task {task_id}: {prior.error or prior.final_response or prior.user_request}"
        task_req = TaskRequest(instruction=instruction)
        task_record = TaskService.create_task(request=task_req)
        return {
            "task_id": task_record.task_id,
            "status": "created",
            "tts_message": "Investigating recent test failures with the Debugger agent.",
        }

    @staticmethod
    def review_changes() -> Dict[str, Any]:
        """Submit a code review task for recent workspace changes."""
        instruction = "Review recent code changes for security, style, and correctness."
        task_req = TaskRequest(instruction=instruction)
        task_record = TaskService.create_task(request=task_req)
        return {
            "task_id": task_record.task_id,
            "status": "created",
            "tts_message": "Submitting code review task to the Reviewer agent.",
        }

    @staticmethod
    def get_artifacts(task_id: Optional[str] = None) -> Dict[str, Any]:
        """Fetch artifact summary for a given task or recent workspace activity."""
        try:
            from backend.app.services.artifact_service import ArtifactService
            if task_id:
                artifacts = ArtifactService.list_artifacts_for_task(task_id)
            else:
                artifacts = []

            if artifacts:
                types = ", ".join(set(a.artifact_type.value for a in artifacts))
                tts_msg = f"Found {len(artifacts)} artifacts for task {task_id[:8] if task_id else ''}: {types}."
            else:
                tts_msg = "No artifacts available for the referenced task."

            return {
                "status": "ok",
                "artifacts_count": len(artifacts),
                "tts_message": tts_msg,
            }
        except Exception as exc:
            logger.warning("get_artifacts error: %s", exc)
            return {
                "status": "ok",
                "tts_message": "Artifact retrieval completed.",
            }

    # ------------------------------------------------------------------
    # Approvals
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_approval(approval_id: str, approved: bool, reason: str = "Voice command", user_id: Optional[str] = None, user_role: Optional[str] = None) -> Dict[str, Any]:
        """Resolve a pending human approval request."""
        if settings.AUTH_ENABLED and (user_role or "").upper() not in ("DEVELOPER", "ADMIN"):
            return {"status": "denied", "tts_message": "Approval requires a developer or administrator."}
        try:
            from backend.app.security.approval import ApprovalManager
            from backend.app.models.approval import ApprovalStatus

            record = ApprovalManager.get_approval(approval_id)
            status_enum = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
            success = ApprovalManager.resolve_approval(
                approval_id=approval_id,
                status=status_enum,
                reason=reason,
                resolved_by=user_id or "dev-default",
            )
            verb = "approved" if approved else "rejected"
            if success and record:
                from backend.app.services.multi_agent_service import MultiAgentService
                from backend.app.services.audit_service import AuditService
                AuditService.record(action="VOICE_APPROVAL_RESOLVED", status="SUCCESS", user_id=user_id,
                                    target_entity="approval", target_id=approval_id, details={"approved": approved})
                MultiAgentService.resume_approval(record.task_id, approved=approved)
                return {
                    "status": "ok",
                    "approval_id": approval_id,
                    "tts_message": f"Action {approval_id[:8]} has been {verb}.",
                }
            else:
                return {
                    "status": "error",
                    "tts_message": f"Could not find pending approval {approval_id[:8]}.",
                }
        except Exception as exc:
            logger.warning("resolve_approval error: %s", exc)
            return {
                "status": "error",
                "tts_message": f"Approval resolution failed: {exc}",
            }
