"""
Secure Test Runner Tool for AgentOS Phase 3.

Provides structured test execution through the existing ToolExecutor and
SecurityManager pipeline.  The LLM specifies:

  test.run { "framework": "pytest", "path": "tests/" }

No arbitrary command strings are accepted.

Supported frameworks
--------------------
* pytest — runs `python -m pytest <path> ...` inside WORKSPACE_ROOT.
* npm — reads package.json test script, validates it against shell-injection
  patterns and an allowlisted executor set, then runs with shell=False.

Security guarantees
-------------------
* shell=False at all times.
* Only allowlisted test executors may run (pytest, jest, mocha, vitest).
* npm test scripts are parsed from package.json and validated before execution.
* Dangerous shell constructs in npm scripts are rejected.
* Execution is bounded by MAX_TEST_RUNTIME (timeout).
* Output is truncated at MAX_OUTPUT_SIZE.
* Working directory is always WORKSPACE_ROOT (or validated subdirectory).
* Path argument is validated against WORKSPACE_ROOT.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from backend.app.config.settings import settings
from backend.app.models.tool import RiskLevel, ToolMetadata, ToolRequest, ToolResult
from backend.app.services.workspace_service import WorkspaceService
from backend.app.tools.base import BaseTool
from backend.app.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Executors that npm script commands are allowed to start with
_ALLOWED_NPM_EXECUTORS: frozenset[str] = frozenset({
    "jest", "vitest", "mocha", "jasmine", "ava", "tap", "tape",
    "node", "npx", "ts-jest",
})

# Shell metacharacters / constructs that are forbidden in npm scripts
_SHELL_INJECTION_RE = re.compile(
    r"[;&|`$<>]"            # common shell operators
    r"|(?:&&|\|\|)"        # logical operators (already caught by |, but explicit)
    r"|\$\("               # subshell
    r"|`"                  # backtick subshell
    r"|\brm\b"             # rm command
    r"|\bcurl\b"           # network exfiltration
    r"|\bwget\b"
    r"|\bnc\b"
    r"|\bpython\b.*-c"     # inline script execution
    r"|\beval\b"
)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

@dataclass
class TestRunResult:
    framework: str
    path: Optional[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    error: Optional[str] = None
    # Parsed counts (best-effort; None if not parseable)
    passed: Optional[int] = None
    failed: Optional[int] = None
    errors: Optional[int] = None
    skipped: Optional[int] = None


# ---------------------------------------------------------------------------
# npm script validator
# ---------------------------------------------------------------------------

def _validate_npm_test_script(workspace_root: Path) -> tuple[list[str], Optional[str]]:
    """Parse and validate the npm test script from package.json.

    Returns:
        (cmd_list, None) on success where cmd_list is the validated command.
        ([], error_message) on failure.
    """
    pkg_json = workspace_root / "package.json"
    if not pkg_json.exists():
        return [], "package.json not found in workspace root"

    try:
        pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [], f"Cannot read package.json: {exc}"

    scripts = pkg.get("scripts", {})
    test_script = scripts.get("test")
    if not test_script:
        return [], "No 'test' script found in package.json scripts"

    # Reject shell injection patterns
    if _SHELL_INJECTION_RE.search(test_script):
        return [], (
            f"npm test script contains unsafe shell construct: {test_script!r}. "
            "The test script must be a simple allowlisted command."
        )

    # Validate first token is an allowed executor
    parts = test_script.split()
    if not parts:
        return [], "npm test script is empty"

    first_token = parts[0].lower()
    # strip path separators (e.g. ./node_modules/.bin/jest → jest)
    base_name = first_token.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    # Remove .cmd / .exe suffixes (Windows)
    base_name = re.sub(r"\.(cmd|exe|sh|bat)$", "", base_name)

    if base_name not in _ALLOWED_NPM_EXECUTORS:
        return [], (
            f"npm test script executor '{base_name}' is not in the allowlist. "
            f"Allowed: {sorted(_ALLOWED_NPM_EXECUTORS)}"
        )

    # Build the actual command — use npm run test (via node) to stay within npm's
    # environment, NOT shell execution
    return ["npm", "run", "test", "--if-present"], None


# ---------------------------------------------------------------------------
# Output parser
# ---------------------------------------------------------------------------

_PYTEST_SUMMARY_RE = re.compile(
    r"(\d+) passed|(\d+) failed|(\d+) error|(\d+) skipped",
    re.IGNORECASE,
)


def _parse_pytest_counts(output: str) -> dict[str, Optional[int]]:
    counts: dict[str, Optional[int]] = {"passed": None, "failed": None, "errors": None, "skipped": None}
    for m in _PYTEST_SUMMARY_RE.finditer(output):
        if m.group(1):
            counts["passed"] = int(m.group(1))
        if m.group(2):
            counts["failed"] = int(m.group(2))
        if m.group(3):
            counts["errors"] = int(m.group(3))
        if m.group(4):
            counts["skipped"] = int(m.group(4))
    return counts


# ---------------------------------------------------------------------------
# TestRunnerTool
# ---------------------------------------------------------------------------

class TestRunnerTool(BaseTool):
    """Structured secure test runner: pytest and npm."""

    __test__ = False

    _FRAMEWORKS = ("pytest", "npm")

    def __init__(self) -> None:
        super().__init__(ToolMetadata(
            name="test",
            description=(
                "Securely execute allowlisted test frameworks inside the workspace. "
                "Frameworks: pytest, npm. No arbitrary shell commands accepted."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["run"],
                        "description": "Operation to perform (currently only 'run').",
                    },
                    "framework": {
                        "type": "string",
                        "enum": list(self._FRAMEWORKS),
                        "description": "Test framework to use.",
                    },
                    "path": {
                        "type": "string",
                        "description": (
                            "For pytest: relative path to test file or directory. "
                            "For npm: not used (reads from package.json)."
                        ),
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "For pytest: additional allowlisted flags (e.g. ['-v', '-x']).",
                    },
                },
                "required": ["operation", "framework"],
            },
            risk_level=RiskLevel.MEDIUM,
        ))
        self._custom_root: Optional[Path] = None

    @property
    def _root(self) -> Path:
        return (self._custom_root or Path(settings.WORKSPACE_ROOT)).resolve()

    @_root.setter
    def _root(self, val: Path) -> None:
        self._custom_root = val

    # Allowed additional pytest flags (LLM cannot inject arbitrary flags)
    _PYTEST_ALLOWED_FLAGS: frozenset[str] = frozenset({

        "-v", "--verbose",
        "-q", "--quiet",
        "-x", "--exitfirst",
        "-s", "--capture=no",
        "--tb=short", "--tb=long", "--tb=no",
        "--no-header",
    })

    def execute(self, request: ToolRequest) -> ToolResult:
        op = request.arguments.get("operation")
        if op != "run":
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error=f"Unknown test operation: '{op}'. Only 'run' is supported.",
            )

        framework = request.arguments.get("framework", "")
        if framework not in self._FRAMEWORKS:
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error=f"Unknown framework: '{framework}'. Allowed: {self._FRAMEWORKS}",
            )

        try:
            if framework == "pytest":
                run_result = self._run_pytest(request.arguments)
            else:
                run_result = self._run_npm(request.arguments)
        except Exception as exc:
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error=f"Unexpected error in test.run ({framework}): {exc}",
            )

        if run_result.error:
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error=run_result.error,
            )

        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            data={
                "framework": run_result.framework,
                "path": run_result.path,
                "exit_code": run_result.exit_code,
                "passed": run_result.exit_code == 0,
                "timed_out": run_result.timed_out,
                "duration_seconds": run_result.duration_seconds,
                "counts": {
                    "passed": run_result.passed,
                    "failed": run_result.failed,
                    "errors": run_result.errors,
                    "skipped": run_result.skipped,
                },
                # Truncated output for LLM consumption
                "stdout": run_result.stdout[:settings.MAX_OUTPUT_SIZE],
                "stderr": run_result.stderr[:4096],
            },
        )

    def _run_pytest(self, args: dict) -> TestRunResult:
        import time

        # Build base command
        cmd = [sys.executable, "-m", "pytest"]

        # Validate and add path argument
        path = args.get("path")
        cwd = self._root
        if path:
            try:
                target = WorkspaceService.validate_path(path)
            except ValueError as exc:
                return TestRunResult(
                    framework="pytest", path=path,
                    exit_code=-1, stdout="", stderr="",
                    duration_seconds=0,
                    error=f"Invalid test path: {exc}",
                )
            cmd.append(str(target))

        # Validate additional flags
        extra_flags = args.get("args", [])
        for flag in extra_flags:
            if flag not in self._PYTEST_ALLOWED_FLAGS:
                return TestRunResult(
                    framework="pytest", path=path,
                    exit_code=-1, stdout="", stderr="",
                    duration_seconds=0,
                    error=f"Flag '{flag}' is not in the pytest allowlist.",
                )
            cmd.append(flag)

        start = time.monotonic()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(cwd),
                shell=False,
                timeout=settings.MAX_TEST_RUNTIME,
            )
            duration = time.monotonic() - start
            stdout = result.stdout[:settings.MAX_OUTPUT_SIZE]
            stderr = result.stderr[:4096]
            counts = _parse_pytest_counts(stdout + stderr)
            return TestRunResult(
                framework="pytest",
                path=path,
                exit_code=result.returncode,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration,
                passed=counts["passed"],
                failed=counts["failed"],
                errors=counts["errors"],
                skipped=counts["skipped"],
            )
        except subprocess.TimeoutExpired:
            return TestRunResult(
                framework="pytest", path=path,
                exit_code=-1, stdout="", stderr="",
                duration_seconds=settings.MAX_TEST_RUNTIME,
                timed_out=True,
                error=f"pytest timed out after {settings.MAX_TEST_RUNTIME}s",
            )

    def _run_npm(self, args: dict) -> TestRunResult:
        import time

        cmd, err = _validate_npm_test_script(self._root)
        if err:
            return TestRunResult(
                framework="npm", path=None,
                exit_code=-1, stdout="", stderr="",
                duration_seconds=0,
                error=err,
            )

        start = time.monotonic()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self._root),
                shell=False,
                timeout=settings.MAX_TEST_RUNTIME,
            )
            duration = time.monotonic() - start
            return TestRunResult(
                framework="npm",
                path=None,
                exit_code=result.returncode,
                stdout=result.stdout[:settings.MAX_OUTPUT_SIZE],
                stderr=result.stderr[:4096],
                duration_seconds=duration,
            )
        except subprocess.TimeoutExpired:
            return TestRunResult(
                framework="npm", path=None,
                exit_code=-1, stdout="", stderr="",
                duration_seconds=settings.MAX_TEST_RUNTIME,
                timed_out=True,
                error=f"npm test timed out after {settings.MAX_TEST_RUNTIME}s",
            )
        except FileNotFoundError:
            return TestRunResult(
                framework="npm", path=None,
                exit_code=-1, stdout="", stderr="",
                duration_seconds=0,
                error="npm executable not found",
            )


# Register on import
ToolRegistry.register(TestRunnerTool())
