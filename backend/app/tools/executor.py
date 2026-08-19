"""
AgentOS Phase 1 — Tool Executor

Two execution paths:

execute(request, task_id):
    Full path — security check → approval check → execute.
    Used for initial, non-approved calls.

execute_post_approval(request, task_id):
    Post-approval path — security check AGAIN → execute (no second approval prompt).
    NEVER bypasses the Security subsystem.
    Only bypasses the duplicate approval prompt.
    Correct flow:
        ToolRequest
        → Security validation (is_allowed)
        → execute (no requires_approval check — already approved for this request)
        → Tool
"""

from __future__ import annotations

import uuid

from backend.app.models.approval import ApprovalRequest, ApprovalStatus
from backend.app.models.tool import RiskLevel, ToolRequest, ToolResult
from backend.app.security.approval import ApprovalManager
from backend.app.security.permissions import SecurityManager
from backend.app.security.policies import get_policy
from backend.app.tools.registry import ToolRegistry


class ToolExecutor:

    @staticmethod
    def execute(request: ToolRequest, task_id: str) -> ToolResult:
        """
        Full execution path with security and approval gate.

        Returns a ToolResult with success=False if:
          - tool not found
          - operation denied by policy (CRITICAL)
          - operation requires approval (returns approval_id in error string)
        """
        tool = ToolRegistry.get_tool(request.tool_name)
        if not tool:
            return ToolResult(
                tool_name=request.tool_name,
                success=False,
                error="Tool not found in registry",
            )

        operation = request.arguments.get("operation", "default")

        if not SecurityManager.is_allowed(request.tool_name, operation):
            return ToolResult(
                tool_name=request.tool_name,
                success=False,
                error="Security: Operation DENIED by policy",
            )

        if SecurityManager.requires_approval(request.tool_name, operation):
            approval_id = str(uuid.uuid4())
            app_req = ApprovalRequest(
                approval_id=approval_id,
                task_id=task_id,
                tool_name=request.tool_name,
                operation=operation,
                arguments_summary=request.arguments,
                risk_level=get_policy(request.tool_name, operation),
                reason="Requires human approval per security policy",
            )
            ApprovalManager.request_approval(app_req)
            return ToolResult(
                tool_name=request.tool_name,
                success=False,
                error=f"APPROVAL_REQUIRED:{approval_id}",
            )

        try:
            return tool.execute(request)
        except Exception as exc:
            return ToolResult(
                tool_name=request.tool_name,
                success=False,
                error=str(exc),
            )

    @staticmethod
    def execute_post_approval(request: ToolRequest, task_id: str) -> ToolResult:
        """
        Post-approval execution path.

        Security is validated AGAIN (per spec). The approval prompt is NOT
        re-triggered — this method is called only after the LangGraph interrupt
        has been resolved with APPROVED and the request integrity has been
        verified by the approval_node.

        This method MUST NOT bypass SecurityManager.is_allowed().
        """
        tool = ToolRegistry.get_tool(request.tool_name)
        if not tool:
            return ToolResult(
                tool_name=request.tool_name,
                success=False,
                error="Tool not found in registry",
            )

        operation = request.arguments.get("operation", "default")

        # Security re-validation — mandatory even after approval
        if not SecurityManager.is_allowed(request.tool_name, operation):
            return ToolResult(
                tool_name=request.tool_name,
                success=False,
                error="Security: Operation DENIED by policy (post-approval re-validation)",
            )

        # NOTE: requires_approval is intentionally NOT checked here.
        # The approval was already granted by the human for this specific request.
        # Checking it again would create an infinite loop.

        try:
            return tool.execute(request)
        except Exception as exc:
            return ToolResult(
                tool_name=request.tool_name,
                success=False,
                error=str(exc),
            )
