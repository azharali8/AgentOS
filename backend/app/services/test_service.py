"""
AgentOS Phase 4 — Test Service for automated test discovery and execution.

Uses existing Phase 3 ToolRegistry and TestRunnerTool.
Never spawns arbitrary shell commands; all runs are strictly bounded and shell=False.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.code.scanner import RepositoryScanner
from backend.app.config.settings import settings
from backend.app.models.tool import ToolRequest
from backend.app.services.workspace_service import WorkspaceService
from backend.app.tools.registry import ToolRegistry

logger = logging.getLogger("agentos.test_service")


class TestService:
    """Discovers tests and invokes the allowlisted TestRunnerTool."""

    @staticmethod
    def discover_test_framework(workspace_root: Optional[Path] = None) -> tuple[str, Optional[str]]:
        """
        Inspect repository to determine framework ("pytest" or "npm") and main test target directory.
        Returns: (framework, target_path_hint)
        """
        root = (workspace_root or Path(settings.WORKSPACE_ROOT)).resolve()
        scanner = RepositoryScanner(workspace_root=root)
        scan_res = scanner.scan()

        has_package_json = any(f.relative_path == "package.json" for f in scan_res.files)
        has_python_tests = any(f.is_test_file and f.extension == ".py" for f in scan_res.files)

        if has_python_tests or any(f.extension == ".py" for f in scan_res.files):
            # Locate primary test folder if any
            test_files = [f.relative_path for f in scan_res.files if f.is_test_file and f.extension == ".py"]
            primary_target = test_files[0] if test_files else None
            return "pytest", primary_target
        elif has_package_json:
            return "npm", None
        else:
            return "pytest", None

    @staticmethod
    def run_tests(framework: str = "pytest", path: Optional[str] = None, args: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Execute test runner tool through ToolRegistry.
        """
        test_tool = ToolRegistry.get("test")
        if not test_tool:
            return {"success": False, "error": "Test tool not registered"}

        arguments: Dict[str, Any] = {
            "operation": "run",
            "framework": framework,
        }
        if path:
            arguments["path"] = path
        if args:
            arguments["args"] = args

        req = ToolRequest(tool_name="test", arguments=arguments)
        result = test_tool.execute(req)

        if not result.success:
            return {
                "success": False,
                "error": result.error or "Test execution failed",
                "data": None,
            }

        return {
            "success": True,
            "error": None,
            "data": result.data,
        }

    @staticmethod
    def parse_test_report(test_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Produce a user-facing StructuredTestReport with evidence-grounded issue diagnosis.
        """
        import re
        from backend.app.models.coding import FailureClassification, DiagnosedIssue, StructuredTestReport

        stdout = test_data.get("stdout", "")
        stderr = test_data.get("stderr", "")
        combined = (stdout + "\n" + stderr).strip()
        counts = test_data.get("counts", {})
        passed_c = counts.get("passed") or 0
        failed_c = (counts.get("failed") or 0) + (counts.get("errors") or 0)
        skipped_c = counts.get("skipped") or 0
        total_c = passed_c + failed_c + skipped_c
        duration = float(test_data.get("duration_seconds") or 0.0)
        exit_code = int(test_data.get("exit_code", 0 if passed_c > 0 and failed_c == 0 else 1))

        # Classify and extract individual issues
        issues: List[DiagnosedIssue] = []
        lines = combined.splitlines()

        _FILE_LINE_RE = re.compile(r"([a-zA-Z0-9_\-\\/.]+\.py):(\d+)(?::\s+(.*))?")
        _ASSERT_MSG_RE = re.compile(r"E\s+(.*)")

        current_test = None
        current_file = None
        current_line = None
        current_messages: List[str] = []
        current_trace: List[str] = []
        in_failure = False

        for line in lines:
            if (line.startswith("_") and line.endswith("_") and len(line.strip("_").strip()) > 0) or line.startswith("FAILED ") or line.startswith("ERROR "):
                if current_test:
                    issues.append(TestService._create_diagnosed_issue(
                        len(issues) + 1, current_test, current_file, current_line, current_messages, current_trace
                    ))
                current_messages, current_trace, current_file, current_line = [], [], None, None
                if line.startswith("FAILED ") or line.startswith("ERROR "):
                    part = line.split(" ", 1)[1].split()[0]
                    if "::" in part:
                        current_file, current_test = part.split("::", 1)
                    else:
                        current_test = part
                else:
                    t_str = line.strip("_").strip()
                    if t_str not in ("FAILURES", "ERRORS", "short test summary info"):
                        current_test = t_str
                in_failure = True
                continue

            if in_failure:
                if line.startswith("="):
                    if current_test:
                        issues.append(TestService._create_diagnosed_issue(
                            len(issues) + 1, current_test, current_file, current_line, current_messages, current_trace
                        ))
                        current_test = None
                    in_failure = False
                    continue

                current_trace.append(line)
                if line.strip().startswith("E   "):
                    current_messages.append(line.strip()[4:])
                fl_m = _FILE_LINE_RE.search(line)
                if fl_m:
                    fpath = fl_m.group(1).replace("\\", "/")
                    if not current_file or "test" in fpath:
                        current_file = fpath
                        current_line = int(fl_m.group(2))

        if current_test:
            issues.append(TestService._create_diagnosed_issue(
                len(issues) + 1, current_test, current_file, current_line, current_messages, current_trace
            ))

        if not issues and failed_c > 0:
            err_lines = [l for l in lines if "error" in l.lower() or "fail" in l.lower()][:3]
            msg = "\n".join(err_lines) or "Test suite encountered failures."
            issues.append(DiagnosedIssue(
                issue_number=1,
                title="Test Execution Failure",
                test_name="test_suite",
                error_type="AssertionError",
                message=msg,
                stack_trace=combined[:1000],
                explanation="Test run reported failing tests. See raw console logs for details.",
                likely_cause="Test assertions failed against current implementation.",
                suggested_fix="Inspect the failing test output and correct the affected code.",
                classification=FailureClassification.APPLICATION_BUG,
                confidence=0.8,
            ))

        report = StructuredTestReport(
            command=test_data.get("command", ""),
            framework=test_data.get("framework", "pytest"),
            exit_code=exit_code,
            passed=exit_code == 0 and not test_data.get("timed_out", False),
            passed_count=passed_c,
            failed_count=failed_c,
            skipped_count=skipped_c,
            error_count=counts.get("errors") or 0,
            total_count=total_c,
            duration_seconds=duration,
            issues=issues,
            raw_stdout=stdout,
            raw_stderr=stderr,
        )
        return report.model_dump()

    @staticmethod
    def _create_diagnosed_issue(
        issue_num: int,
        test_name: str,
        file_path: Optional[str],
        line_number: Optional[int],
        messages: List[str],
        trace: List[str],
    ):
        import re
        from backend.app.models.coding import FailureClassification, DiagnosedIssue
        from backend.app.services.workspace_service import WorkspaceService

        full_msg = " \n ".join(messages) if messages else "Test assertion failed."
        full_trace = "\n".join(trace[:30])

        source_file = None
        source_line = None
        _FL_RE = re.compile(r"([a-zA-Z0-9_\-\\/.]+\.py):(\d+)")
        for line in reversed(trace):
            m = _FL_RE.search(line)
            if m:
                path_str = m.group(1).replace("\\", "/")
                if not path_str.startswith("tests/") and "test_" not in path_str and "/test" not in path_str:
                    source_file = path_str
                    source_line = int(m.group(2))
                    break

        resolved_source = source_file or file_path
        resolved_line = source_line or line_number

        # Classify
        text_lower = f"{full_msg} {full_trace}".lower()
        if "modulenotfound" in text_lower or "no module named" in text_lower:
            classification = FailureClassification.DEPENDENCY_ERROR
        elif "operationalerror" in text_lower and ("database" in text_lower or "table" in text_lower):
            classification = FailureClassification.CONFIGURATION_ERROR
        elif "fixture" in text_lower and "not found" in text_lower:
            classification = FailureClassification.TEST_BUG
        elif "permissionerror" in text_lower:
            classification = FailureClassification.ENVIRONMENT_ERROR
        elif "syntaxerror" in text_lower:
            classification = FailureClassification.APPLICATION_BUG
        else:
            classification = FailureClassification.APPLICATION_BUG

        # Snippet
        snippet = None
        if resolved_source:
            try:
                p = WorkspaceService.validate_path(resolved_source)
                if p.is_file():
                    all_lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                    target_ln = (resolved_line or 1) - 1
                    start = max(0, target_ln - 2)
                    end = min(len(all_lines), target_ln + 3)
                    snippet = "\n".join(
                        f"{' > ' if i == target_ln else '   '}{i+1}: {all_lines[i]}"
                        for i in range(start, end)
                    )
            except Exception:
                pass

        title = f"{test_name.replace('test_', '').replace('_', ' ').capitalize()} failure"
        if "assert" in full_msg.lower():
            explanation = f"The test `{test_name}` failed an assertion condition: {full_msg.strip()}"
            likely_cause = f"The implementation in `{resolved_source or 'source'}` did not return the expected value."
            suggested_fix = f"Update `{resolved_source or 'source'}` around line {resolved_line or 1} to satisfy the test requirement."
        else:
            explanation = f"The test `{test_name}` encountered an error: {full_msg.strip()}"
            likely_cause = "An unexpected exception was raised during execution."
            suggested_fix = f"Fix the exception in `{resolved_source or 'source'}` at line {resolved_line or 1}."

        return DiagnosedIssue(
            issue_number=issue_num,
            title=title,
            test_name=test_name,
            test_file=file_path,
            source_file=resolved_source,
            line=resolved_line,
            error_type="AssertionError" if "assert" in full_msg.lower() else "Exception",
            message=full_msg,
            stack_trace=full_trace,
            explanation=explanation,
            likely_cause=likely_cause,
            suggested_fix=suggested_fix,
            classification=classification,
            confidence=0.92 if source_file else 0.85,
            source_snippet=snippet,
        )

