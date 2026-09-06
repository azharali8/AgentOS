"""
AgentOS Voice Agent — Central Controller.

The VoiceAgent is the single entry point for voice-driven AgentOS interactions.
It acts as the dedicated voice controller and interface layer — NOT a second
engineering Supervisor.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from backend.app.voice.agent.command_router import AgentOSCommandGateway
from backend.app.voice.agent.confirmation import ConfirmationGate
from backend.app.voice.agent.conversation import ConversationState
from backend.app.voice.agent.intent import IntentType, VoiceIntent

logger = logging.getLogger("agentos.voice.agent")


@dataclass
class VoiceAgentResult:
    """Result of a single VoiceAgent.process() call."""
    tts_summary: str
    intent_type: IntentType = IntentType.UNKNOWN
    status: str = "ok"
    task_id: Optional[str] = None
    project_created: bool = False
    project_path: Optional[str] = None
    needs_clarification: bool = False
    requires_confirmation: bool = False


class VoiceAgent:
    """Dedicated Voice Control Agent for AgentOS."""

    def __init__(
        self,
        conversation: Optional[ConversationState] = None,
        gateway: Optional[AgentOSCommandGateway] = None,
    ) -> None:
        self.conversation = conversation or ConversationState()
        self.gateway = gateway or AgentOSCommandGateway()
        self.confirmation_gate = ConfirmationGate()

    def process(
        self,
        transcript: str,
        user_id: Optional[str] = None,
    ) -> VoiceAgentResult:
        """Process a voice transcript end-to-end."""
        transcript = transcript.strip()
        if not transcript:
            return VoiceAgentResult(
                tts_summary="I didn't catch that. Please speak again clearly.",
                status="empty",
            )

        logger.info("VoiceAgent.process: '%s'", transcript[:80])

        # 1. Handle pending clarification questions
        if self.conversation.has_pending_question():
            return self._handle_clarification_reply(transcript, user_id)

        self.conversation.add_user_turn(transcript)

        # 2. Classify intent
        intent = self._classify_intent(transcript)
        logger.info("VoiceAgent: classified as %s (confidence=%.2f)", intent.intent_type, intent.confidence)

        # 3. Confirmation gate for destructive operations
        if intent.requires_confirmation or self.confirmation_gate.requires_confirmation(transcript):
            self.conversation.set_pending_question(
                question=f"Are you sure you want to proceed with: {transcript[:60]}?",
                context={"intent": intent},
            )
            self.conversation.add_agent_turn("Please confirm before I proceed.")
            return VoiceAgentResult(
                tts_summary="This operation may modify or delete files. Please say 'confirm' to proceed or 'cancel' to abort.",
                intent_type=intent.intent_type,
                status="awaiting_confirmation",
                requires_confirmation=True,
                needs_clarification=True,
            )

        # 4. Route intent to AgentOS services
        return self._route_and_respond(intent, user_id)

    def _classify_intent(self, transcript: str) -> VoiceIntent:
        """Classify transcript into a structured VoiceIntent."""
        lower = transcript.lower()

        # --- CREATE PROJECT ---
        create_project_triggers = [
            "create a new project", "create new project", "scaffold project",
            "scaffold a project", "create a fastapi", "create a python",
            "create a react", "create a nextjs", "create a web app",
            "create an app", "create a url shortener", "create project",
            "create a project",
        ]
        if any(t in lower for t in create_project_triggers):
            proj_name = self._extract_project_name(transcript)
            return VoiceIntent(
                intent_type=IntentType.CREATE_PROJECT,
                transcript=transcript,
                instruction=transcript,
                project_name=proj_name,
                confidence=0.95,
            )

        # --- RUN TESTS ---
        run_test_triggers = [
            "run tests", "run the tests", "run the test suite",
            "execute tests", "test the code", "run tests again",
            "run the tests again",
        ]
        if any(t in lower for t in run_test_triggers):
            return VoiceIntent(
                intent_type=IntentType.RUN_TESTS,
                transcript=transcript,
                instruction=transcript,
                confidence=0.95,
            )

        # --- INVESTIGATE FAILURE ---
        investigate_triggers = [
            "why did the tests fail", "why did tests fail", "why did it fail",
            "investigate the failure", "diagnose failure", "what failed",
            "why did the test fail",
        ]
        if any(t in lower for t in investigate_triggers):
            return VoiceIntent(
                intent_type=IntentType.INVESTIGATE_FAILURE,
                transcript=transcript,
                instruction=transcript,
                confidence=0.90,
            )

        # --- REVIEW CHANGES ---
        review_triggers = [
            "review the changes", "review changes", "review the code",
            "what files did you modify", "what did you change",
            "explain what you changed", "explain changes",
        ]
        if any(t in lower for t in review_triggers):
            return VoiceIntent(
                intent_type=IntentType.REVIEW_CHANGES,
                transcript=transcript,
                instruction=transcript,
                confidence=0.90,
            )

        # --- WORKSPACE STATUS ---
        workspace_status_triggers = [
            "open my agentos project", "workspace status", "project status",
            "inspect project", "what is this project", "tell me about this project",
        ]
        if any(t in lower for t in workspace_status_triggers):
            return VoiceIntent(
                intent_type=IntentType.GET_WORKSPACE_STATUS,
                transcript=transcript,
                instruction=transcript,
                confidence=0.85,
            )

        # --- TASK STATUS ---
        if any(w in lower for w in ["show me the current task status", "task status", "how is the task going", "check task status"]):
            status_match = re.search(r"(?:status|state|progress)\s+(?:of\s+)?(?:task\s+)?([a-f0-9\-]{8,})?", lower)
            task_id = status_match.group(1) if status_match else self.conversation.active_task_id
            return VoiceIntent(
                intent_type=IntentType.GET_TASK_STATUS,
                transcript=transcript,
                task_id=task_id,
                instruction=transcript,
                confidence=0.90,
            )

        # --- CANCEL TASK ---
        if any(w in lower for w in ["stop the current task", "cancel task", "stop task", "abort task"]):
            cancel_match = re.search(r"(?:cancel|stop|abort)\s+(?:task\s+)?([a-f0-9\-]{8,})?", lower)
            task_id = cancel_match.group(1) if (cancel_match and cancel_match.group(1)) else self.conversation.active_task_id
            return VoiceIntent(
                intent_type=IntentType.CANCEL_TASK,
                transcript=transcript,
                task_id=task_id,
                instruction=transcript,
                confidence=0.90,
            )

        # --- APPROVE / REJECT ACTION ---
        if lower.startswith("approve") or "approve action" in lower:
            app_match = re.search(r"approve\s+(?:action\s+)?([a-f0-9\-]{8,})?", lower)
            approval_id = app_match.group(1) if app_match else None
            return VoiceIntent(
                intent_type=IntentType.APPROVE_ACTION,
                transcript=transcript,
                approval_id=approval_id,
                confidence=0.95,
            )

        if lower.startswith("reject") or "reject action" in lower:
            app_match = re.search(r"reject\s+(?:action\s+)?([a-f0-9\-]{8,})?", lower)
            approval_id = app_match.group(1) if app_match else None
            return VoiceIntent(
                intent_type=IntentType.REJECT_ACTION,
                transcript=transcript,
                approval_id=approval_id,
                confidence=0.95,
            )

        # --- DEFAULT: GENERAL ENGINEERING TASK ---
        return VoiceIntent(
            intent_type=IntentType.CREATE_TASK,
            transcript=transcript,
            instruction=transcript,
            confidence=0.80,
        )

    def _route_and_respond(self, intent: VoiceIntent, user_id: Optional[str]) -> VoiceAgentResult:
        """Route intent through AgentOSCommandGateway and build a natural VoiceAgentResult."""
        if intent.intent_type == IntentType.CREATE_PROJECT:
            if not intent.project_name:
                self.conversation.set_pending_question(
                    question="What would you like to name the project?",
                    context={"intent": intent},
                )
                self.conversation.add_agent_turn("What would you like to name the project?")
                return VoiceAgentResult(
                    tts_summary="What would you like to name the project?",
                    intent_type=intent.intent_type,
                    status="needs_clarification",
                    needs_clarification=True,
                )

            parent = self._resolve_project_parent()
            try:
                result = self.gateway.create_project(
                    name=intent.project_name,
                    location=str(parent),
                    instruction=intent.instruction or intent.transcript,
                )
                self.conversation.active_project_path = result.get("path")
                task_res = self.gateway.create_task(
                    instruction=intent.instruction or intent.transcript,
                    user_id=user_id,
                )
                task_id = task_res.get("task_id")
                self.conversation.active_task_id = task_id

                summary_instr = (intent.instruction or intent.transcript)[:80]
                tts_msg = f"Project {intent.project_name} created. Starting engineering task: {summary_instr}"
                self.conversation.add_agent_turn(tts_msg)
                return VoiceAgentResult(
                    tts_summary=tts_msg,
                    intent_type=intent.intent_type,
                    status="created",
                    task_id=task_id,
                    project_created=True,
                    project_path=result.get("path"),
                )
            except Exception as exc:
                logger.warning("CREATE_PROJECT failed: %s; falling back to task", exc)
                return self._fallback_task(intent, user_id)

        elif intent.intent_type == IntentType.RUN_TESTS:
            res = self.gateway.run_tests()
            tts = res.get("tts_message", "Tests completed.")
            self.conversation.add_agent_turn(tts)
            return VoiceAgentResult(
                tts_summary=tts,
                intent_type=intent.intent_type,
                status=res.get("status", "ok"),
                task_id=res.get("task_id"),
            )

        elif intent.intent_type == IntentType.INVESTIGATE_FAILURE:
            res = self.gateway.investigate_failure(intent.task_id or self.conversation.active_task_id)
            tts = res.get("tts_message", "Diagnosing failure.")
            self.conversation.add_agent_turn(tts)
            return VoiceAgentResult(
                tts_summary=tts,
                intent_type=intent.intent_type,
                status=res.get("status", "created"),
                task_id=res.get("task_id"),
            )

        elif intent.intent_type == IntentType.REVIEW_CHANGES:
            res = self.gateway.review_changes()
            tts = res.get("tts_message", "Reviewing changes.")
            self.conversation.add_agent_turn(tts)
            return VoiceAgentResult(
                tts_summary=tts,
                intent_type=intent.intent_type,
                status=res.get("status", "created"),
                task_id=res.get("task_id"),
            )

        elif intent.intent_type == IntentType.GET_WORKSPACE_STATUS:
            res = self.gateway.get_workspace_status()
            tts = res.get("tts_message", "Workspace inspected.")
            self.conversation.add_agent_turn(tts)
            return VoiceAgentResult(
                tts_summary=tts,
                intent_type=intent.intent_type,
                status=res.get("status", "ok"),
            )

        elif intent.intent_type == IntentType.GET_TASK_STATUS:
            res = self.gateway.get_task_status(intent.task_id or self.conversation.active_task_id)
            tts = res.get("tts_message", "Task status retrieved.")
            self.conversation.add_agent_turn(tts)
            return VoiceAgentResult(
                tts_summary=tts,
                intent_type=intent.intent_type,
                status=res.get("status", "ok"),
                task_id=res.get("task_id"),
            )

        elif intent.intent_type == IntentType.CANCEL_TASK:
            res = self.gateway.cancel_task(intent.task_id or self.conversation.active_task_id or "")
            tts = res.get("tts_message", "Cancellation requested.")
            self.conversation.add_agent_turn(tts)
            return VoiceAgentResult(
                tts_summary=tts,
                intent_type=intent.intent_type,
                status=res.get("status", "cancelling"),
                task_id=intent.task_id,
            )

        elif intent.intent_type == IntentType.APPROVE_ACTION:
            res = self.gateway.resolve_approval(intent.approval_id or "", approved=True)
            tts = res.get("tts_message", "Action approved.")
            self.conversation.add_agent_turn(tts)
            return VoiceAgentResult(
                tts_summary=tts,
                intent_type=intent.intent_type,
                status=res.get("status", "ok"),
            )

        elif intent.intent_type == IntentType.REJECT_ACTION:
            res = self.gateway.resolve_approval(intent.approval_id or "", approved=False)
            tts = res.get("tts_message", "Action rejected.")
            self.conversation.add_agent_turn(tts)
            return VoiceAgentResult(
                tts_summary=tts,
                intent_type=intent.intent_type,
                status=res.get("status", "ok"),
            )

        else:
            return self._fallback_task(intent, user_id)

    def _fallback_task(self, intent: VoiceIntent, user_id: Optional[str]) -> VoiceAgentResult:
        """Route general or fallback commands as engineering tasks to Supervisor."""
        instruction = intent.instruction or intent.transcript
        if not instruction.strip():
            return VoiceAgentResult(
                tts_summary="I didn't understand the command. Please try again.",
                intent_type=IntentType.UNKNOWN,
                status="failed",
            )

        res = self.gateway.create_task(instruction=instruction, user_id=user_id)
        task_id = res.get("task_id")
        self.conversation.active_task_id = task_id
        tts = res.get("tts_message", f"Starting task: {instruction[:80]}")
        self.conversation.add_agent_turn(tts)

        return VoiceAgentResult(
            tts_summary=tts,
            intent_type=IntentType.CREATE_TASK,
            status="created",
            task_id=task_id,
        )

    def _handle_clarification_reply(self, reply: str, user_id: Optional[str]) -> VoiceAgentResult:
        """Process user's reply to a pending question or confirmation gate."""
        question, context = self.conversation.consume_pending_question()
        pending_intent: Optional[VoiceIntent] = context.get("intent")

        if self.confirmation_gate.is_confirmed(reply):
            if pending_intent:
                pending_intent.requires_confirmation = False
                return self._route_and_respond(pending_intent, user_id)
            return VoiceAgentResult(tts_summary="Confirmed. Proceeding with operation.", status="ok")

        if self.confirmation_gate.is_rejected(reply):
            return VoiceAgentResult(tts_summary="Operation cancelled.", status="cancelled")

        if pending_intent and pending_intent.intent_type == IntentType.CREATE_PROJECT and not pending_intent.project_name:
            clean_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "", reply.strip().replace(" ", "-")) or "NewProject"
            pending_intent.project_name = clean_name
            return self._route_and_respond(pending_intent, user_id)

        combined_instruction = f"{pending_intent.instruction if pending_intent else ''} {reply}".strip()
        new_intent = self._classify_intent(combined_instruction)
        return self._route_and_respond(new_intent, user_id)

    @staticmethod
    def _extract_project_name(transcript: str) -> Optional[str]:
        """Extract project name from transcript phrases."""
        lower = transcript.lower().strip()

        # If it's a bare generic command like "create a new project" or "create a project"
        if lower in ("create a new project", "create new project", "create a project", "create project", "scaffold a project", "scaffold project"):
            return None

        # 1. Explicit name pattern: "called <name>", "named <name>"
        match_named = re.search(r"(?:called|named)\s+([a-zA-Z0-9_\-]+)", transcript, re.IGNORECASE)
        if match_named:
            cand = match_named.group(1).strip()
            if cand.lower() not in {"a", "an", "the", "with", "for", "in", "and"}:
                return cand

        # 2. Pattern: "project <name>"
        match_proj = re.search(r"(?:project)\s+([a-zA-Z0-9_\-]+)", transcript, re.IGNORECASE)
        if match_proj:
            cand = match_proj.group(1).strip()
            if cand.lower() not in {"a", "an", "the", "with", "for", "in", "and", "called", "named"}:
                return cand

        # Common archetypes
        if "url shortener" in lower or "url-shortener" in lower:
            return "UrlShortenerApp"
        elif "fastapi" in lower:
            return "FastApiProject"
        elif "task manager" in lower or "todo" in lower:
            return "TaskManagerApp"
        elif "api" in lower:
            return "ApiProject"
        return None

    @staticmethod
    def _resolve_project_parent() -> Path:
        """Resolve a safe parent directory for new project creation."""
        from backend.app.config.settings import PROJECT_ROOT
        from backend.app.services.workspace_service import WorkspaceService

        agentos_root = Path(PROJECT_ROOT).resolve()
        current_root = WorkspaceService.get_workspace_root()

        if current_root.resolve() == agentos_root / "workspace":
            return current_root
        if current_root.exists() and current_root.is_dir() and not current_root.resolve().is_relative_to(agentos_root):
            return current_root.parent
        return current_root
