"""
End-to-End integration test for Phase 5 supervised multi-agent collaboration workflow.

Demonstrates full scenario:
1. User provides complex software engineering instruction.
2. SupervisorAgent decomposes task into DAG (Research -> Debugger -> Coding -> Reviewer -> Documentation).
3. Independent subtasks execute with concurrency and conflict checks.
4. Approval gate pauses for human authorization on code mutations.
5. Resumes upon approval, runs reviews, security scans, and produces unified engineering report.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from langgraph.checkpoint.memory import MemorySaver

from backend.app.db.database import get_db_session
from backend.app.db.models import ApprovalModel, EventModel, ExecutionModel, TaskModel
from backend.app.llm.mock import MockLLMProvider
from backend.app.models.task import TaskStatus
from backend.app.services.multi_agent_service import MultiAgentService
import backend.app.workflows.multi_agent_workflow as _mw_module


@pytest.fixture(autouse=True)
def clean_db():
    """Wipe DB and reset multi-agent graph singletons before/after tests."""
    with get_db_session() as session:
        session.query(EventModel).delete()
        session.query(ExecutionModel).delete()
        session.query(ApprovalModel).delete()
        session.query(TaskModel).delete()
    _mw_module._multi_agent_compiled_graph = None
    _mw_module._multi_agent_sqlite_conn = None
    _mw_module._multi_agent_checkpointer = None
    yield
    with get_db_session() as session:
        session.query(EventModel).delete()
        session.query(ExecutionModel).delete()
        session.query(ApprovalModel).delete()
        session.query(TaskModel).delete()
    _mw_module._multi_agent_compiled_graph = None
    _mw_module._multi_agent_sqlite_conn = None
    _mw_module._multi_agent_checkpointer = None


def test_multi_agent_end_to_end_workflow(tmp_path, monkeypatch):
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

    # ── 2. Inject MockLLMProvider for offline deterministic execution ───
    monkeypatch.setattr("backend.app.config.settings.settings.LLM_PROVIDER", "mock")

    # ── 3. Isolate graph using MemorySaver checkpointer ─────────────────
    def _fresh_mock_graph():
        from backend.app.workflows.multi_agent_workflow import build_multi_agent_graph
        return build_multi_agent_graph().compile(checkpointer=MemorySaver())

    fresh_graph = _fresh_mock_graph()
    monkeypatch.setattr(_mw_module, "_multi_agent_compiled_graph", None)
    monkeypatch.setattr(
        "backend.app.services.multi_agent_service.get_multi_agent_graph",
        lambda: fresh_graph
    )

    # ── 4. Write buggy calculator fixture ────────────────────────────────
    calc_file = tmp_path / "calculator.py"
    calc_file.write_text("def add(a: int, b: int) -> int:\n    return a - b\n", encoding="utf-8")

    test_file = tmp_path / "test_calculator.py"
    test_file.write_text(
        "from calculator import add\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n",
        encoding="utf-8"
    )

    # ── 5. Start Multi-Agent workflow ─────────────────────────────────────
    task = MultiAgentService.start_task(
        instruction="Analyze the project, identify failing test, formulate fix, obtain approval, apply patch, and document.",
        sync=True
    )
    assert task is not None
    assert task.task_id is not None

    # ── 6. Check that workflow paused at WAITING_APPROVAL ────────────────
    state = MultiAgentService.get_state(task.task_id)
    assert state is not None
    assert state.get("approval_id") is not None
    assert len(state.get("subtasks", [])) >= 3

    # ── 7. Grant human approval and resume workflow ───────────────────────
    resumed = MultiAgentService.resume_approval(task_id=task.task_id, approved=True)
    assert resumed.status == TaskStatus.COMPLETED

    # ── 8. Check final report ─────────────────────────────────────────────
    report = MultiAgentService.get_report(task.task_id)
    assert report is not None
    assert report["status"] == "COMPLETED"
    assert report["completed_count"] >= 3
    assert "Multi-Agent Collaboration Report" in report["final_response"]
