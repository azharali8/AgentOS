"""
Tests for backend/app/agents/task_classifier.py
"""

import json
import pytest

from backend.app.agents.task_classifier import TaskClassifierAgent
from backend.app.llm.mock import MockLLMProvider
from backend.app.models.coding import TaskType


def test_task_classifier_mock_success():
    provider = MockLLMProvider()
    agent = TaskClassifierAgent(llm_provider=provider)
    res = agent.classify("Fix the failing test in calculator.py")
    assert res.task_type == TaskType.BUG_FIX
    assert res.requires_tests is True
    assert res.risk_level == "HIGH"
    assert "calculator.py" in res.target_files_hint


def test_task_classifier_custom_response():
    provider = MockLLMProvider()
    provider.push_json({
        "task_type": "repository_analysis",
        "requires_tests": False,
        "requires_code_change": False,
        "risk_level": "LOW",
        "reasoning": "User asked to scan repo structure.",
        "target_files_hint": []
    })
    agent = TaskClassifierAgent(llm_provider=provider)
    res = agent.classify("Please analyze the repository layout and structure")
    assert res.task_type == TaskType.REPOSITORY_ANALYSIS
    assert res.requires_tests is False
    assert res.risk_level == "LOW"


def test_task_classifier_fallback_on_malformed_llm_output():
    provider = MockLLMProvider()
    provider.push("Not valid JSON output")
    agent = TaskClassifierAgent(llm_provider=provider)
    res = agent.classify("Fix failing pytest suite in backend")
    assert res.task_type == TaskType.TEST_FAILURE
    assert res.requires_tests is True
