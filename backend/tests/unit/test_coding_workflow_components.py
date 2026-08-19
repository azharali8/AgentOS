"""
Unit and integration tests for Phase 4 autonomous software engineering workflow.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from backend.app.agents.failure_analyzer import FailureAnalyzerAgent
from backend.app.agents.investigator import CodeInvestigatorAgent
from backend.app.agents.judge import ResultJudgeAgent
from backend.app.agents.task_classifier import TaskClassifierAgent
from backend.app.llm.mock import MockLLMProvider
from backend.app.models.coding import FailureInfo, JudgeVerdictType, TaskType
from backend.app.models.tool import ToolResult
from backend.app.services.coding_service import CodingService
from backend.app.services.test_service import TestService
from backend.app.workflows.coding_workflow import build_coding_graph


def test_failure_analyzer_deterministic_parsing():
    sample_pytest_output = (
        "============================= FAILURES =============================\n"
        "_____________________________ test_add _____________________________\n"
        "tests/test_calculator.py:6: in test_add\n"
        "    assert add(2, 3) == 5\n"
        "E   assert -1 == 5\n"
        "E    +  where -1 = add(2, 3)\n"
    )
    analyzer = FailureAnalyzerAgent()
    failures = analyzer.analyze(sample_pytest_output)
    assert len(failures) >= 1
    assert failures[0].test_name == "test_add"
    assert failures[0].file_path == "tests/test_calculator.py"
    assert failures[0].line_number == 6
    assert "assert -1 == 5" in failures[0].message


def test_code_investigator_symbol_gathering(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.app.config.settings.settings.WORKSPACE_ROOT", str(tmp_path))
    calc_file = tmp_path / "calculator.py"
    calc_file.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    import backend.app.services.workspace_service as ws
    def patched_validate(path_str):
        return (tmp_path / path_str).resolve()
    monkeypatch.setattr(ws.WorkspaceService, "validate_path", staticmethod(patched_validate))

    investigator = CodeInvestigatorAgent(llm_provider=MockLLMProvider())
    failure = FailureInfo(test_name="test_add", likely_files=["calculator.py"], message="assert -1 == 5")
    res = investigator.investigate([failure], instruction="Fix calculator add function")

    assert "calculator.py" in res.affected_files
    assert res.confidence >= 0.8


def test_result_judge_success_verdict():
    judge = ResultJudgeAgent()
    failures = [FailureInfo(test_name="test_add", message="assert -1 == 5")]
    post_test = {"exit_code": 0, "passed": True, "counts": {"passed": 1, "failed": 0}, "stdout": "1 passed"}
    verdict = judge.evaluate(failures, post_test)

    assert verdict.verdict == JudgeVerdictType.SUCCESS
    assert "test_add" in verdict.resolved_tests


def test_result_judge_regression_detection():
    judge = ResultJudgeAgent()
    failures = [FailureInfo(test_name="test_add", message="assert -1 == 5")]
    initial_test = {"exit_code": 1, "passed": False, "counts": {"passed": 2, "failed": 1}}
    post_test = {"exit_code": 1, "passed": False, "counts": {"passed": 0, "failed": 3}, "stdout": "3 failed"}

    verdict = judge.evaluate(failures, post_test, initial_test_data=initial_test)
    assert verdict.verdict == JudgeVerdictType.REGRESSION


def test_coding_workflow_graph_structure():
    workflow = build_coding_graph()
    assert workflow is not None
    compiled = workflow.compile()
    assert compiled is not None


def test_failure_analyzer_llm_fallback():
    mock_llm = MockLLMProvider()
    analyzer = FailureAnalyzerAgent(llm_provider=mock_llm)
    failures = analyzer.analyze("non standard error trace without pytest formatting")
    assert len(failures) >= 1
    assert failures[0].test_name == "test_add"


def test_investigator_fallback_when_symbols_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.app.config.settings.settings.WORKSPACE_ROOT", str(tmp_path))
    investigator = CodeInvestigatorAgent(llm_provider=MockLLMProvider())
    failure = FailureInfo(test_name="test_missing", likely_files=["nonexistent.py"], message="error")
    res = investigator.investigate([failure], instruction="Fix issue")
    assert res is not None
    assert len(res.affected_files) >= 1


def test_result_judge_still_failing():
    judge = ResultJudgeAgent()
    failures = [FailureInfo(test_name="test_add", message="assert -1 == 5")]
    post_test = {"exit_code": 1, "passed": False, "counts": {"passed": 0, "failed": 1}, "stdout": "1 failed"}
    verdict = judge.evaluate(failures, post_test)
    assert verdict.verdict == JudgeVerdictType.STILL_FAILING


def test_result_judge_new_failure():
    mock_llm = MockLLMProvider()
    mock_llm.push_json({
        "verdict": "NEW_FAILURE",
        "reasoning": "Original bug fixed, but a new test failed.",
        "confidence": 0.95,
        "tests_passed": 1,
        "tests_failed": 1,
        "newly_failing_tests": ["test_sub"],
        "resolved_tests": ["test_add"],
    })
    judge = ResultJudgeAgent(llm_provider=mock_llm)
    failures = [FailureInfo(test_name="test_add", message="assert -1 == 5")]
    post_test = {
        "exit_code": 1,
        "passed": False,
        "counts": {"passed": 1, "failed": 1},
        "stdout": "FAILED test_other.py::test_sub - AssertionError",
    }
    verdict = judge.evaluate(failures, post_test)
    assert verdict.verdict == JudgeVerdictType.NEW_FAILURE
    assert "test_sub" in verdict.newly_failing_tests


def test_coding_api_endpoints():
    from fastapi.testclient import TestClient
    from backend.app.main import app

    client = TestClient(app)

    # 1. Test 404 for nonexistent task
    resp = client.get("/api/coding/nonexistent-task-id")
    assert resp.status_code == 404

    # 2. Test 404 for nonexistent diagnosis
    resp = client.get("/api/coding/nonexistent-task-id/diagnosis")
    assert resp.status_code == 404

    # 3. Test 404 for nonexistent report
    resp = client.get("/api/coding/nonexistent-task-id/report")
    assert resp.status_code == 404

