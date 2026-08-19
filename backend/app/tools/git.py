"""
Structured Read-Only Git Tool for AgentOS Phase 3.

Provides five strongly-typed read-only Git operations.  The LLM MUST NOT
pass arbitrary command strings or flags — operations are dispatched by name
with individually validated argument schemas.

Security guarantees
-------------------
* shell=False at all times (subprocess.run with an explicit list).
* Write/mutation operations (push, pull, merge, rebase, reset, clean,
  checkout, switch, commit, tag) are explicitly rejected.
* The Git working directory is restricted to WORKSPACE_ROOT; the --git-dir
  and --work-tree flags cannot be injected by the LLM.
* Arguments are individually validated against per-operation allowlists.
* No arbitrary flags accepted — only parameters explicitly permitted by the
  operation schema.
* stdout/stderr are truncated to MAX_OUTPUT_SIZE.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Optional

from backend.app.config.settings import settings
from backend.app.models.tool import RiskLevel, ToolMetadata, ToolRequest, ToolResult
from backend.app.tools.base import BaseTool
from backend.app.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Explicitly rejected mutation operations — for defence-in-depth
# ---------------------------------------------------------------------------
_MUTATION_OPERATIONS: frozenset[str] = frozenset({
    "push", "pull", "merge", "rebase", "reset", "clean",
    "checkout", "switch", "commit", "tag", "stash", "cherry-pick",
    "bisect", "apply", "am", "fetch", "remote", "submodule",
    "worktree", "gc", "prune", "reflog", "update-index",
    "rm", "mv", "add", "restore", "revert",
})

_ALLOWED_OPERATIONS: frozenset[str] = frozenset({
    "status", "branch", "log", "diff", "show",
})


def _truncate(text: str, max_bytes: int) -> str:
    """Truncate text to at most max_bytes encoded bytes."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="replace") + "\n[...output truncated...]"


class GitTool(BaseTool):
    """Structured read-only Git tool (status, branch, log, diff, show)."""

    def __init__(self) -> None:
        super().__init__(ToolMetadata(
            name="git",
            description=(
                "Read-only Git inspection: status, branch, log, diff, show. "
                "Write operations (push, merge, commit, etc.) are unconditionally rejected."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": sorted(_ALLOWED_OPERATIONS),
                        "description": "Git operation to perform.",
                    },
                    # --- log parameters ---
                    "max_count": {
                        "type": "integer",
                        "description": "For 'log': maximum number of commits to show (default 20, max 100).",
                    },
                    "oneline": {
                        "type": "boolean",
                        "description": "For 'log': use --oneline format.",
                    },
                    # --- diff / show parameters ---
                    "ref": {
                        "type": "string",
                        "description": "For 'diff'/'show': git ref (commit hash, branch, tag). "
                                       "Must be alphanumeric with -, _, ., / only.",
                    },
                    "path": {
                        "type": "string",
                        "description": "For 'diff': optional relative file path to restrict diff.",
                    },
                    # --- branch parameters ---
                    "all_branches": {
                        "type": "boolean",
                        "description": "For 'branch': list all branches including remotes.",
                    },
                    # --- status parameters ---
                    "short": {
                        "type": "boolean",
                        "description": "For 'status': use --short format.",
                    },
                },
                "required": ["operation"],
            },
            risk_level=RiskLevel.LOW,
        ))
        self._workspace = Path(settings.WORKSPACE_ROOT).resolve()

    # ------------------------------------------------------------------
    # BaseTool interface
    # ------------------------------------------------------------------

    def execute(self, request: ToolRequest) -> ToolResult:
        op = request.arguments.get("operation", "")

        # Defence-in-depth: explicitly reject mutation operations
        if op in _MUTATION_OPERATIONS:
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error=f"git.{op} is a write/mutation operation and is not permitted.",
            )

        if op not in _ALLOWED_OPERATIONS:
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error=f"Unknown git operation: '{op}'. Allowed: {sorted(_ALLOWED_OPERATIONS)}",
            )

        try:
            cmd, error = self._build_command(op, request.arguments)
            if error:
                return ToolResult(
                    tool_name=self.metadata.name,
                    success=False,
                    error=error,
                )

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self._workspace),  # Always run inside WORKSPACE_ROOT
                shell=False,               # NEVER shell=True
                timeout=settings.TERMINAL_TIMEOUT,
            )

            stdout = _truncate(result.stdout, settings.MAX_OUTPUT_SIZE)
            stderr = _truncate(result.stderr, 4096)  # Cap error output separately

            if result.returncode == 0:
                return ToolResult(
                    tool_name=self.metadata.name,
                    success=True,
                    data={
                        "operation": op,
                        "output": stdout,
                        "return_code": result.returncode,
                    },
                )
            else:
                return ToolResult(
                    tool_name=self.metadata.name,
                    success=False,
                    error=f"git {op} exited with code {result.returncode}: {stderr}",
                )

        except subprocess.TimeoutExpired:
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error=f"git {op} timed out after {settings.TERMINAL_TIMEOUT}s",
            )
        except FileNotFoundError:
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error="git executable not found. Ensure Git is installed and on PATH.",
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error=f"Unexpected error in git.{op}: {exc}",
            )

    # ------------------------------------------------------------------
    # Command builders — one per operation
    # ------------------------------------------------------------------

    def _build_command(
        self, op: str, args: dict[str, Any]
    ) -> tuple[list[str], Optional[str]]:
        """Build a validated git command list.

        Returns (cmd, None) on success or ([], error_message) on failure.
        """
        if op == "status":
            cmd = ["git", "status"]
            if args.get("short"):
                cmd.append("--short")
            return cmd, None

        elif op == "branch":
            cmd = ["git", "branch"]
            if args.get("all_branches"):
                cmd.append("--all")
            return cmd, None

        elif op == "log":
            max_count = args.get("max_count", 20)
            if not isinstance(max_count, int) or max_count < 1:
                return [], "max_count must be a positive integer"
            max_count = min(max_count, 100)  # Hard cap
            cmd = ["git", "log", f"--max-count={max_count}"]
            if args.get("oneline"):
                cmd.append("--oneline")
            return cmd, None

        elif op == "diff":
            cmd = ["git", "diff"]
            ref = args.get("ref")
            if ref is not None:
                err = _validate_ref(ref)
                if err:
                    return [], err
                cmd.append(ref)
            path = args.get("path")
            if path is not None:
                # Validate the path doesn't escape workspace
                err = _validate_relative_path(path)
                if err:
                    return [], err
                cmd.extend(["--", path])
            return cmd, None

        elif op == "show":
            ref = args.get("ref")
            if not ref:
                return [], "'ref' is required for git.show"
            err = _validate_ref(ref)
            if err:
                return [], err
            cmd = ["git", "show", "--stat", ref]
            return cmd, None

        # Should never reach here since we validated op above
        return [], f"Internal: unhandled operation '{op}'"


# ---------------------------------------------------------------------------
# Argument validators
# ---------------------------------------------------------------------------

import re

_REF_PATTERN = re.compile(r"^[a-zA-Z0-9_.\-/~^:@{}\[\]]+$")
_PATH_TRAVERSAL_RE = re.compile(r"\.\.|//|\\\\")


def _validate_ref(ref: str) -> Optional[str]:
    """Validate a git ref (commit hash, branch, tag) for safety.

    Returns None on success or an error message string on failure.
    """
    if not ref or len(ref) > 256:
        return "git ref must be between 1 and 256 characters"
    # Block shell metacharacters and injection sequences
    if not _REF_PATTERN.match(ref):
        return (
            f"Invalid git ref '{ref}': only alphanumeric characters and "
            "-, _, ., /, ~, ^, :, @, {{, }}, [, ] are permitted"
        )
    # Block path traversal inside refs
    if ".." in ref:
        return f"Path traversal ('..') detected in git ref: {ref}"
    return None


def _validate_relative_path(path: str) -> Optional[str]:
    """Validate a relative file path argument for a git command.

    Returns None on success or an error message string on failure.
    """
    if not path:
        return "path must not be empty"
    if path.startswith("\\\\") or path.startswith("//"):
        return "UNC paths are not allowed"
    p = Path(path)
    if p.is_absolute():
        return f"Absolute paths are not allowed: {path}"
    if ".." in p.parts:
        return f"Path traversal ('..') detected: {path}"
    return None


# Register on import
ToolRegistry.register(GitTool())
