"""
End-to-End integration test for Phase 4 autonomous software engineering and debugging runtime.

Uses a fresh MemorySaver per test and MockLLMProvider to ensure deterministic, offline execution
without requiring Ollama or any external LLM service.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from langgraph.checkpoint.memory import MemorySaver

from backend.app.llm.mock import MockLLMProvider
from backend.app.models.approval import ApprovalStatus
from backend.app.models.task import TaskStatus
from backend.app.services.coding_service import CodingService
from backend.app.db.database import get_db_session
from backend.app.db.models import TaskModel, ApprovalModel, ExecutionModel, EventModel
import backend.app.workflows.coding_workflow as _cw_module
import backend.app.services.coding_service as _cs_module


@pytest.fixture(autouse=True)
def clean_db():
    """Wipe all DB tables and reset the coding graph singleton before/after each test."""
    with get_db_session() as session:
        session.query(EventModel).delete()
        session.query(ExecutionModel).delete()
        session.query(ApprovalModel).delete()
        session.query(TaskModel).delete()
    # Reset coding graph singleton so each test gets a fresh graph
    _cw_module._coding_compiled_graph = None
    _cw_module._coding_sqlite_conn = None
    _cw_module._coding_checkpointer = None
    yield
    with get_db_session() as session:
        session.query(EventModel).delete()
        session.query(ExecutionModel).delete()
        session.query(ApprovalModel).delete()
        session.query(TaskModel).delete()
    _cw_module._coding_compiled_graph = None
    _cw_module._coding_sqlite_conn = None
    _cw_module._coding_checkpointer = None


def test_coding_autonomous_loop_e2e(tmp_path, monkeypatch):
    # ── 1. Workspace setup ──────────────────────────────────────────────
    monkeypatch.setattr("backend.app.config.settings.settings.WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("backend.app.code.scanner.settings.WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("backend.app.code.patch.validator.settings.WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("backend.app.code.patch.applier.settings.WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("backend.app.tools.test_runner.settings.WORKSPACE_ROOT", str(tmp_path))

    import backend.app.services.workspace_service as ws
    def patched_validate(path_str):
        p = Path(path_str)
        if ".." in p.parts:
            raise ValueError("Path traversal")
        return (tmp_path / path_str).resolve()
    monkeypatch.setattr(ws.WorkspaceService, "validate_path", staticmethod(patched_validate))

    # ── 2. Inject deterministic MockLLMProvider into all Phase 4 agents ─
    monkeypatch.setattr("backend.app.config.settings.settings.LLM_PROVIDER", "mock")
    monkeypatch.setattr("backend.app.agents.task_classifier.get_llm_provider", lambda: MockLLMProvider())
    monkeypatch.setattr("backend.app.agents.failure_analyzer.get_llm_provider", lambda: MockLLMProvider())
    monkeypatch.setattr("backend.app.agents.investigator.get_llm_provider", lambda: MockLLMProvider())
    monkeypatch.setattr("backend.app.agents.debugger.get_llm_provider", lambda: MockLLMProvider())
    monkeypatch.setattr("backend.app.agents.judge.get_llm_provider", lambda: MockLLMProvider())

    # ── 3. Replace global graph singleton with a fresh in-memory graph ───
    def _fresh_mock_graph():
        """Build a fresh coding graph with MemorySaver for test isolation."""
        from backend.app.workflows.coding_workflow import build_coding_graph
        return build_coding_graph().compile(checkpointer=MemorySaver())

    fresh_graph = _fresh_mock_graph()
    monkeypatch.setattr(_cw_module, "_coding_compiled_graph", None)  # reset singleton
    monkeypatch.setattr(
        "backend.app.services.coding_service.get_coding_graph",
        lambda: fresh_graph
    )

    # ── 4. Write buggy fixture files ─────────────────────────────────────
    calc_file = tmp_path / "calculator.py"
    calc_file.write_text("def add(a: int, b: int) -> int:\n    return a - b\n", encoding="utf-8")

    test_file = tmp_path / "test_calculator.py"
    test_file.write_text(
        "from calculator import add\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n",
        encoding="utf-8"
    )

    # ── 5. Launch coding workflow ─────────────────────────────────────────
    task = CodingService.start_coding_task(
        instruction="Fix the failing test in calculator.py",
        sync=True
    )
    assert task is not None, "start_coding_task must return a TaskResult"
    assert task.task_id is not None

    # ── 6. Verify workflow paused at WAITING_APPROVAL ────────────────────
    state = CodingService.get_coding_state(task.task_id)
    assert state is not None, "State should be available after graph paused"
    assert state.get("patch_hash") is not None, "patch_hash must be set before approval"
    assert state.get("approval_id") is not None, "approval_id must be set when waiting for approval"

    # ── 7. Human grants approval — resume graph ───────────────────────────
    resumed_task = CodingService.resume_approval(task_id=task.task_id, approved=True)
    assert resumed_task.status == TaskStatus.COMPLETED

    # ── 8. Verify the file was patched correctly ──────────────────────────
    fixed_content = calc_file.read_text(encoding="utf-8")
    assert "return a + b" in fixed_content, "Calculator should be fixed to use addition"

    # ── 9. Verify final report ────────────────────────────────────────────
    report = CodingService.get_final_report(task.task_id)
    assert report is not None
    assert report["status"] == "COMPLETED"
    assert "add" in report["diagnosis"]["affected_symbols"]
