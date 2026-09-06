"""
AgentOS Voice Agent — Intent Model.

Represents a classified voice intent extracted from a user transcript.
The Voice Agent uses this to decide which AgentOS service to invoke.
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class IntentType(str, Enum):
    """Supported Voice Agent intent categories."""
    CREATE_PROJECT = "create_project"          # Scaffold a new project from scratch
    CONNECT_PROJECT = "connect_project"        # Switch / connect to an existing project path
    SWITCH_PROJECT = "switch_project"          # Switch active workspace to another project
    CREATE_TASK = "create_task"                # Submit an engineering task to Supervisor
    EXECUTE_TASK = "execute_task"              # Run / execute task immediately
    GET_TASK_STATUS = "get_task_status"        # Query status of a running or recent task
    CANCEL_TASK = "cancel_task"                # Cancel a running task
    RUN_TESTS = "run_tests"                    # Run the test suite on current workspace
    INVESTIGATE_FAILURE = "investigate_failure" # Ask why tests/tasks failed and suggest fix
    REVIEW_CHANGES = "review_changes"          # Ask for code review or git changes summary
    GET_ARTIFACTS = "get_artifacts"            # Fetch artifacts (test report, patch, plan)
    GET_WORKSPACE_STATUS = "get_workspace_status" # Inspect project structure, files, framework
    APPROVE_ACTION = "approve_action"          # Approve pending approval request
    REJECT_ACTION = "reject_action"            # Reject pending approval request
    UNKNOWN = "unknown"                        # Unrecognized command — fallback to general task


@dataclass
class VoiceIntent:
    """
    Structured result of intent classification for a voice transcript.

    Attributes:
        intent_type:           Classified intent category.
        transcript:            Raw transcript text from STT.
        confidence:            Classification confidence [0.0 – 1.0].
        project_name:          Extracted project name (for CREATE_PROJECT).
        project_path:          Extracted project path (for CONNECT_PROJECT / SWITCH_PROJECT).
        task_id:               Extracted or referenced task ID (for status/cancel/artifacts).
        approval_id:           Extracted approval ID (for APPROVE/REJECT_ACTION).
        instruction:           Cleaned instruction to pass to AgentOS services.
        parameters:            Arbitrary key-value parameters extracted from voice utterance.
        requires_confirmation: Whether this intent triggers a confirmation gate.
    """
    intent_type: IntentType
    transcript: str
    confidence: float = 1.0
    project_name: Optional[str] = None
    project_path: Optional[str] = None
    task_id: Optional[str] = None
    approval_id: Optional[str] = None
    instruction: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False

    @property
    def is_actionable(self) -> bool:
        """True if the intent can be routed to an AgentOS service immediately."""
        return self.intent_type != IntentType.UNKNOWN or bool(self.instruction.strip())
