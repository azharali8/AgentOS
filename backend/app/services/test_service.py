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
