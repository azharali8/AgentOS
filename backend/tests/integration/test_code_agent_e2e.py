"""
End-to-End integration test for Phase 3 Code Intelligence and Engineering Agent.

Simulates a real software engineering workflow:
1. Scan repository structure.
2. Search for buggy function.
3. Extract AST symbols.
4. Run tests and observe failure.
5. Create and validate patch.
6. Apply patch and verify fix with test runner.
7. Verify rollback mechanism restores clean baseline.
"""

from pathlib import Path
import pytest

from backend.app.code.patch.applier import PatchApplier
from backend.app.code.patch.models import (
    Patch,
    PatchFile,
    PatchHunk,
    compute_file_hash,
    compute_patch_hash,
)
from backend.app.code.patch.validator import PatchValidator
from backend.app.code.reader import CodeReader
from backend.app.code.scanner import RepositoryScanner
from backend.app.code.search import CodeSearch
from backend.app.code.symbols import SymbolExtractor
from backend.app.models.tool import ToolRequest
from backend.app.tools.registry import ToolRegistry


def test_phase3_end_to_end_engineering_workflow(tmp_path, monkeypatch):
    # 1. Setup workspace with code and tests
    monkeypatch.setattr("backend.app.config.settings.settings.WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("backend.app.code.scanner.settings.WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("backend.app.code.search.settings.WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("backend.app.code.reader.settings.WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("backend.app.code.symbols.settings.WORKSPACE_ROOT", str(tmp_path))
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

    src_file = tmp_path / "math_lib.py"
    src_file.write_text(
        "def multiply(a, b):\n"
        "    return a + b  # Bug: adding instead of multiplying\n",
        encoding="utf-8"
    )
    original_hash = compute_file_hash(src_file.read_bytes())

    test_file = tmp_path / "test_math.py"
    test_file.write_text(
        "from math_lib import multiply\n"
        "def test_multiply():\n"
        "    assert multiply(2, 3) == 6\n",
        encoding="utf-8"
    )

    # 2. Scanner discovers files
    scanner = RepositoryScanner(workspace_root=tmp_path)
    scan_res = scanner.scan()
    rel_paths = [f.relative_path for f in scan_res.files]
    assert "math_lib.py" in rel_paths
    assert "test_math.py" in rel_paths

    # 3. Search finds buggy function
    searcher = CodeSearch()
    searcher._root = tmp_path.resolve()
    search_res = searcher.search("multiply", relative_path=".")
    assert len(search_res.matches) >= 1

    # 4. Reader inspects buggy line
    reader = CodeReader()
    reader._root = tmp_path.resolve()
    read_res = reader.read("math_lib.py", start_line=1, end_line=2)
    assert "return a + b" in read_res.lines[1]

    # 5. AST Symbol extraction
    sym_extractor = SymbolExtractor()
    sym_extractor._root = tmp_path.resolve()
    sym_res = sym_extractor.extract("math_lib.py")
    assert any(s.name == "multiply" and s.symbol_type == "function" for s in sym_res.symbols)

    # 6. Run test tool (fails initially)
    test_tool = ToolRegistry.get("test")
    test_req = ToolRequest(
        tool_name="test",
        arguments={"operation": "run", "framework": "pytest", "path": "test_math.py"}
    )
    test_res = test_tool.execute(test_req)
    assert test_res.success is True
    assert test_res.data["passed"] is False
    assert test_res.data["exit_code"] == 1

    # 7. Generate, validate and apply patch
    hunk = PatchHunk(
        original_start=2, original_count=1, new_start=2, new_count=1,
        lines=["-    return a + b  # Bug: adding instead of multiplying\n", "+    return a * b\n"]
    )
    pf = PatchFile(relative_path="math_lib.py", original_hash=original_hash, hunks=[hunk])
    patch_obj = Patch(patch_id="patch-123", task_id="task-e2e-1", description="Fix multiply logic", files=[pf])

    validator = PatchValidator()
    validator._root = tmp_path.resolve()
    val_res = validator.validate(patch_obj)
    assert val_res.valid is True
    assert val_res.patch_hash is not None

    applier = PatchApplier()
    applier._root = tmp_path.resolve()
    app_res = applier.apply(patch_obj, val_res.patch_hash)
    assert app_res.success is True

    # 8. Re-run test tool (passes now)
    test_res_after = test_tool.execute(test_req)
    assert test_res_after.success is True
    assert test_res_after.data["passed"] is True
    assert test_res_after.data["exit_code"] == 0

    # 9. Verify rollback restores initial state & test fails again
    rb_res = applier.rollback(app_res.rollback_record, "task-e2e-1")
    assert rb_res.success is True
    test_res_rollback = test_tool.execute(test_req)
    assert test_res_rollback.data["passed"] is False
