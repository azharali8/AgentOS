"""
Tool Execution Idempotency, Side-Effect, and Recovery Policy for AgentOS.
"""

from enum import Enum
from typing import Any, Dict
from pydantic import BaseModel


class SideEffectLevel(str, Enum):
    NONE = "NONE"
    READ_ONLY = "READ_ONLY"
    LOW = "LOW"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class RecoveryStrategy(str, Enum):
    SAFE_TO_RETRY = "SAFE_TO_RETRY"
    UNKNOWN_SIDE_EFFECT = "UNKNOWN_SIDE_EFFECT"
    MANUAL_RECOVERY = "MANUAL_RECOVERY"


class ToolExecutionPolicy(BaseModel):
    retryable: bool
    idempotent: bool
    side_effect_level: SideEffectLevel
    recovery_strategy: RecoveryStrategy


# Platform-safe read-only terminal commands
SAFE_READ_COMMANDS = {
    "python --version",
    "python -v",
    "python3 --version",
    "git status",
    "git log",
    "git --version",
    "dir",
    "ls",
    "echo",
    "where",
    "which",
    "pwd",
}


def classify_tool_request(tool_name: str, operation: str, arguments: Dict[str, Any]) -> ToolExecutionPolicy:
    """
    Classify individual ToolRequests based on tool, operation, and arguments.
    """
    if tool_name == "filesystem":
        if operation in ("read", "list"):
            return ToolExecutionPolicy(
                retryable=True,
                idempotent=True,
                side_effect_level=SideEffectLevel.READ_ONLY,
                recovery_strategy=RecoveryStrategy.SAFE_TO_RETRY,
            )
        elif operation in ("create", "write"):
            # Overwrite/create can be idempotent or state-mutating
            return ToolExecutionPolicy(
                retryable=True,
                idempotent=True,
                side_effect_level=SideEffectLevel.LOW,
                recovery_strategy=RecoveryStrategy.SAFE_TO_RETRY,
            )
        else:
            return ToolExecutionPolicy(
                retryable=False,
                idempotent=False,
                side_effect_level=SideEffectLevel.UNKNOWN,
                recovery_strategy=RecoveryStrategy.UNKNOWN_SIDE_EFFECT,
            )

    elif tool_name == "terminal":
        cmd = arguments.get("command", "").strip()
        cmd_lower = cmd.lower()

        # Check if the command matches safe read-only commands
        is_safe_cmd = any(
            cmd_lower == safe_cmd or cmd_lower.startswith(f"{safe_cmd} ")
            for safe_cmd in SAFE_READ_COMMANDS
        )

        if is_safe_cmd:
            return ToolExecutionPolicy(
                retryable=True,
                idempotent=True,
                side_effect_level=SideEffectLevel.READ_ONLY,
                recovery_strategy=RecoveryStrategy.SAFE_TO_RETRY,
            )
        else:
            return ToolExecutionPolicy(
                retryable=False,
                idempotent=False,
                side_effect_level=SideEffectLevel.HIGH,
                recovery_strategy=RecoveryStrategy.UNKNOWN_SIDE_EFFECT,
            )

    elif tool_name == "git":
        if operation in ("status", "log", "diff", "branch", "show"):
            return ToolExecutionPolicy(
                retryable=True,
                idempotent=True,
                side_effect_level=SideEffectLevel.READ_ONLY,
                recovery_strategy=RecoveryStrategy.SAFE_TO_RETRY,
            )
        else:
            return ToolExecutionPolicy(
                retryable=False,
                idempotent=False,
                side_effect_level=SideEffectLevel.HIGH,
                recovery_strategy=RecoveryStrategy.UNKNOWN_SIDE_EFFECT,
            )

    elif tool_name == "code":
        # All code operations are read-only; sensitive-file gate is enforced by SecurityManager
        if operation in ("scan", "search", "read", "symbols"):
            return ToolExecutionPolicy(
                retryable=True,
                idempotent=True,
                side_effect_level=SideEffectLevel.READ_ONLY,
                recovery_strategy=RecoveryStrategy.SAFE_TO_RETRY,
            )
        else:
            return ToolExecutionPolicy(
                retryable=False,
                idempotent=False,
                side_effect_level=SideEffectLevel.UNKNOWN,
                recovery_strategy=RecoveryStrategy.UNKNOWN_SIDE_EFFECT,
            )

    elif tool_name == "patch":
        if operation == "apply":
            return ToolExecutionPolicy(
                retryable=False,
                idempotent=False,
                side_effect_level=SideEffectLevel.HIGH,
                recovery_strategy=RecoveryStrategy.UNKNOWN_SIDE_EFFECT,
            )
        elif operation == "rollback":
            return ToolExecutionPolicy(
                retryable=False,
                idempotent=False,
                side_effect_level=SideEffectLevel.HIGH,
                recovery_strategy=RecoveryStrategy.UNKNOWN_SIDE_EFFECT,
            )
        else:
            return ToolExecutionPolicy(
                retryable=False,
                idempotent=False,
                side_effect_level=SideEffectLevel.UNKNOWN,
                recovery_strategy=RecoveryStrategy.UNKNOWN_SIDE_EFFECT,
            )

    elif tool_name == "test":
        if operation == "run":
            return ToolExecutionPolicy(
                retryable=True,
                idempotent=True,   # running tests doesn't modify state
                side_effect_level=SideEffectLevel.LOW,
                recovery_strategy=RecoveryStrategy.SAFE_TO_RETRY,
            )
        else:
            return ToolExecutionPolicy(
                retryable=False,
                idempotent=False,
                side_effect_level=SideEffectLevel.UNKNOWN,
                recovery_strategy=RecoveryStrategy.UNKNOWN_SIDE_EFFECT,
            )

    # Default fallback
    return ToolExecutionPolicy(
        retryable=False,
        idempotent=False,
        side_effect_level=SideEffectLevel.UNKNOWN,
        recovery_strategy=RecoveryStrategy.UNKNOWN_SIDE_EFFECT,
    )

