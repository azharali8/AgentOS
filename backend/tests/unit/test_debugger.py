"""
Tests for backend/app/agents/debugger.py
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from backend.app.agents.debugger import DebuggerAgent
from backend.app.code.patch.models import Patch, PatchFile, PatchHunk, compute_file_hash, compute_patch_hash
from backend.app.models.tool import ToolResult


def test_debugger_agent_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.app.code.patch.validator.settings.WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("backend.app.code.patch.applier.settings.WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("backend.app.tools.test_runner.settings.WORKSPACE_ROOT", str(tmp_path))

    import backend.app.services.workspace_service as ws
    def patched_validate(path_str):
        root = tmp_path.resolve()
        p = Path(path_str)
        if ".." in p.parts:
            raise ValueError("Path traversal")
        target = (root / path_str).resolve()
        return target
    monkeypatch.setattr(ws.WorkspaceService, "validate_path", staticmethod(patched_validate))

    calc_file = tmp_path / "calc.py"
    calc_file.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    original_hash = compute_file_hash(calc_file.read_bytes())

    agent = DebuggerAgent(task_id="debug-task-1", framework="pytest", max_iterations=2)
    agent.validator._root = tmp_path.resolve()
    agent.applier._root = tmp_path.resolve()

    # 1. Mock test run initially failing
    with patch("backend.app.tools.registry.ToolRegistry.get") as mock_get_tool:
        mock_test_tool = MagicMock()
        mock_test_tool.execute.return_value = ToolResult(
            tool_name="test",
            success=True,
            data={"framework": "pytest", "exit_code": 1, "passed": False, "stdout": "1 failed", "stderr": ""}
        )
        mock_get_tool.return_value = mock_test_tool

        res = agent.run_tests("test_calc.py")
        assert res["success"] is True
        assert res["data"]["passed"] is False

    # 2. Propose patch
    hunk = PatchHunk(
        original_start=2, original_count=1, new_start=2, new_count=1,
        lines=["-    return a - b\n", "+    return a + b\n"]
    )
    pf = PatchFile(relative_path="calc.py", original_hash=original_hash, hunks=[hunk])
    patch_obj = Patch(patch_id="p1", task_id="debug-task-1", description="Fix add function", files=[pf])

    val_res = agent.validate_proposed_patch(patch_obj)
    assert val_res["valid"] is True
    assert val_res["patch_hash"] is not None

    # 3. Apply patch
    app_res = agent.apply_patch(val_res["patch_hash"])
    assert app_res.success is True
    assert "return a + b" in calc_file.read_text()

    # 4. Verify fix with mock test passing
    with patch("backend.app.tools.registry.ToolRegistry.get") as mock_get_tool:
        mock_test_tool = MagicMock()
        mock_test_tool.execute.return_value = ToolResult(
            tool_name="test",
            success=True,
            data={"framework": "pytest", "exit_code": 0, "passed": True, "stdout": "1 passed", "stderr": ""}
        )
        mock_get_tool.return_value = mock_test_tool

        verified = agent.verify_fix()
        assert verified is True
        assert agent.state.resolved is True

    # 5. Test rollback
    rb_res = agent.rollback()
    assert rb_res.success is True
    assert "return a - b" in calc_file.read_text()
