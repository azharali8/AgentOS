"""
MockLLMProvider — deterministic LLM provider for testing.

Registered through the factory under LLM_PROVIDER="mock".
Returns structured JSON responses appropriate for:
  - Planner (detects "PLANNER_PROMPT" marker in prompt)
  - Reviewer (detects "REVIEWER_PROMPT" marker in prompt)

For tests that require custom responses, instantiate directly with
a response_queue parameter.
"""

from __future__ import annotations

import json
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from backend.app.llm.base import BaseLLMProvider


_DEFAULT_PLAN = {
    "steps": [
        {
            "step_id": "step-1",
            "tool_name": "filesystem",
            "operation": "list",
            "arguments": {"path": "."},
            "description": "List workspace files",
        }
    ]
}

_DEFAULT_REVIEW_SUCCESS = {
    "verdict": "SUCCESS",
    "reasoning": "Mock: operation completed successfully.",
}

_DEFAULT_REVIEW_RETRYABLE = {
    "verdict": "RETRYABLE",
    "reasoning": "Mock: transient error, please retry.",
}

_DEFAULT_REVIEW_FATAL = {
    "verdict": "FATAL",
    "reasoning": "Mock: unrecoverable error.",
}

_DEFAULT_REPLAN = {
    "steps": [
        {
            "step_id": "step-r1",
            "tool_name": "filesystem",
            "operation": "list",
            "arguments": {"path": "."},
            "description": "Replanned: list workspace files",
        }
    ]
}


class MockLLMProvider(BaseLLMProvider):
    """
    Deterministic mock LLM provider for unit and integration tests.

    Usage in tests:
        provider = MockLLMProvider()                        # uses defaults
        provider = MockLLMProvider(response_queue=[...])    # custom queue
    """

    def __init__(
        self,
        response_queue: Optional[List[str]] = None,
        default_plan: Optional[Dict[str, Any]] = None,
        default_review: Optional[Dict[str, Any]] = None,
        default_replan: Optional[Dict[str, Any]] = None,
    ):
        self._queue: Deque[str] = deque(response_queue or [])
        self._default_plan = default_plan or _DEFAULT_PLAN
        self._default_review = default_review or _DEFAULT_REVIEW_SUCCESS
        self._default_replan = default_replan or _DEFAULT_REPLAN

    # ------------------------------------------------------------------
    # Queue API — tests can push responses in order
    # ------------------------------------------------------------------

    def push(self, response: str) -> None:
        """Enqueue a raw string response (JSON or otherwise)."""
        self._queue.append(response)

    def push_json(self, obj: Any) -> None:
        """Enqueue a dict/list response serialised as JSON."""
        self._queue.append(json.dumps(obj))

    # ------------------------------------------------------------------
    # BaseLLMProvider interface
    # ------------------------------------------------------------------

    def generate(self, prompt: str, **kwargs: Any) -> str:
        # Consume from queue if available
        if self._queue:
            return self._queue.popleft()

        # Detect context from special markers inserted by Planner/Reviewer
        if "PLANNER_PROMPT" in prompt:
            if "REPLAN" in prompt:
                return json.dumps(self._default_replan)
            return json.dumps(self._default_plan)

        if "REVIEWER_PROMPT" in prompt:
            return json.dumps(self._default_review)

        if "TASK_CLASSIFIER_PROMPT" in prompt:
            return json.dumps({
                "task_type": "bug_fix",
                "requires_tests": True,
                "requires_code_change": True,
                "risk_level": "HIGH",
                "reasoning": "Mock classification for bug_fix.",
                "target_files_hint": ["calculator.py"]
            })

        if "FAILURE_ANALYZER_PROMPT" in prompt:
            return json.dumps({
                "test_name": "test_add",
                "failure_type": "AssertionError",
                "file_path": "tests/test_calculator.py",
                "line_number": 10,
                "message": "assert add(2, 3) == 5",
                "likely_files": ["calculator.py"]
            })

        if "INVESTIGATION_PROMPT" in prompt:
            return json.dumps({
                "affected_files": ["calculator.py"],
                "relevant_symbols": [{"name": "add", "type": "function", "line": 1}],
                "evidence": "Found incorrect subtraction operation in add()",
                "suspected_root_cause": "add() function returns a - b instead of a + b",
                "confidence": 0.95,
                "recommended_change": "Change a - b to a + b in calculator.py"
            })

        if "DEBUGGER_PROMPT" in prompt:
            return json.dumps({
                "root_cause": "Function add(a, b) performs subtraction instead of addition",
                "affected_files": ["calculator.py"],
                "affected_symbols": ["add"],
                "explanation": "Operand operator is '-' instead of '+'",
                "recommended_fix": "Replace '-' with '+' in calculator.py",
                "confidence": 0.98,
                "risks": []
            })

        if "JUDGE_PROMPT" in prompt:
            return json.dumps({
                "verdict": "SUCCESS",
                "reasoning": "All tests passed with 0 failures after patch application.",
                "confidence": 0.99,
                "tests_passed": 1,
                "tests_failed": 0,
                "newly_failing_tests": [],
                "resolved_tests": ["test_add"]
            })

        if "MULTI_AGENT_DECOMPOSE_PROMPT" in prompt or "SUPERVISOR_PROMPT" in prompt:
            return json.dumps({
                "subtasks": [
                    {
                        "subtask_id": "subtask_1",
                        "description": "Inspect repository structure and discover test framework",
                        "assigned_agent": "research",
                        "dependencies": [],
                        "target_files": ["calculator.py"],
                    },
                    {
                        "subtask_id": "subtask_2",
                        "description": "Run tests and diagnose failures",
                        "assigned_agent": "debugger",
                        "dependencies": ["subtask_1"],
                        "target_files": ["calculator.py"],
                    },
                    {
                        "subtask_id": "subtask_3",
                        "description": "Formulate and apply validated patch",
                        "assigned_agent": "coding",
                        "dependencies": ["subtask_2"],
                        "target_files": ["calculator.py"],
                    },
                    {
                        "subtask_id": "subtask_4",
                        "description": "Review execution outcome and verify no regressions",
                        "assigned_agent": "reviewer",
                        "dependencies": ["subtask_3"],
                        "target_files": ["calculator.py"],
                    },
                    {
                        "subtask_id": "subtask_5",
                        "description": "Generate final engineering documentation report",
                        "assigned_agent": "documentation",
                        "dependencies": ["subtask_4"],
                        "target_files": [],
                    }
                ]
            })

        if "RESEARCH_PROMPT" in prompt:
            return "Analyzed codebase symbols, imports, and structure. Discovered target files."

        if "DOCUMENTATION_PROMPT" in prompt:
            return "Generated comprehensive markdown engineering report."

        if "SECURITY_AGENT_PROMPT" in prompt:
            return json.dumps({
                "sensitive_files": [],
                "policy_violations": [],
                "risk_rating": "LOW",
                "recommended_action": "APPROVE"
            })

        # Fallback: return empty string
        return ""

    def generate_chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        # Flatten messages and delegate to generate
        combined = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
        )
        return self.generate(combined, **kwargs)
