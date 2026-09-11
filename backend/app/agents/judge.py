"""
AgentOS Phase 4 — Result Judge Agent.

Evaluates post-patch test execution results in comparison with pre-patch test states.
Determines:
- SUCCESS: All target tests pass and no regression occurred.
- STILL_FAILING: The original test failure persists.
- REGRESSION: Previously passing tests are now failing.
- NEW_FAILURE: An unexpected new error or exception was introduced.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from backend.app.llm.base import BaseLLMProvider
from backend.app.llm.factory import get_llm_provider
from backend.app.models.coding import FailureInfo, JudgeVerdict, JudgeVerdictType

logger = logging.getLogger("agentos.judge")

JUDGE_PROMPT = """JUDGE_PROMPT:
You are an expert Test Result Judge Agent for AgentOS.
Analyze the pre-patch and post-patch test results to issue a final verdict.

Output ONLY a JSON object:
{
    "verdict": "SUCCESS" | "STILL_FAILING" | "REGRESSION" | "NEW_FAILURE",
    "reasoning": "Clear explanation of verdict",
    "confidence": 0.98,
    "tests_passed": 1,
    "tests_failed": 0,
    "newly_failing_tests": [],
    "resolved_tests": ["test_add"]
}

Pre-patch test summary:
"""


class ResultJudgeAgent:
    """Evaluates post-patch test execution against initial failures."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None) -> None:
        self.llm = llm_provider or get_llm_provider()

    def evaluate(
        self,
        initial_failures: List[FailureInfo],
        post_patch_test_data: Dict[str, Any],
        initial_test_data: Optional[Dict[str, Any]] = None,
    ) -> JudgeVerdict:
        """Deterministically evaluate test results, using LLM verification as needed."""
        exit_code = post_patch_test_data.get("exit_code", 1)
        passed_flag = post_patch_test_data.get("passed", False)
        counts = post_patch_test_data.get("counts", {})
        passed_count = counts.get("passed") or (1 if exit_code == 0 else 0)
        failed_count = counts.get("failed") or (0 if exit_code == 0 else 1)

        # 1. Deterministic SUCCESS check
        if exit_code == 0 and passed_flag is True and failed_count == 0:
            resolved = [f.test_name for f in initial_failures]
            return JudgeVerdict(
                verdict=JudgeVerdictType.SUCCESS,
                reasoning=f"All tests passed with exit code 0. Resolved {len(resolved)} failing test(s).",
                confidence=1.0,
                tests_passed=passed_count,
                tests_failed=0,
                newly_failing_tests=[],
                resolved_tests=resolved,
            )

        # 2. Check for regression vs still failing
        init_exit_code = initial_test_data.get("exit_code", 1) if initial_test_data else 1
        init_counts = initial_test_data.get("counts", {}) if initial_test_data else {}
        init_failed = init_counts.get("failed") or 1

        if failed_count > init_failed:
            return JudgeVerdict(
                verdict=JudgeVerdictType.REGRESSION,
                reasoning=f"Regression detected: failing test count increased from {init_failed} to {failed_count}.",
                confidence=0.95,
                tests_passed=passed_count,
                tests_failed=failed_count,
                newly_failing_tests=["additional_failing_test"],
                resolved_tests=[],
            )

        # 3. LLM verification for nuanced failures
        prompt = (
            f"{JUDGE_PROMPT}\n"
            f"Initial failures: {json.dumps([f.model_dump() for f in initial_failures])}\n"
            f"Post-patch test output:\n{post_patch_test_data.get('stdout', '')[:2000]}"
        )
        try:
            raw_res = self.llm.generate(prompt)
            text = raw_res.strip()
            if text.startswith("```"):
                lines = text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()

            parsed = json.loads(text)
            verdict = JudgeVerdict(**parsed)
            if verdict.verdict == JudgeVerdictType.SUCCESS:
                raise ValueError("Model success contradicts the failing test execution evidence")
            return verdict
        except Exception as exc:
            logger.warning("Judge LLM fallback error: %s", exc)
            return JudgeVerdict(
                verdict=JudgeVerdictType.STILL_FAILING,
                reasoning="Test evaluation completed via deterministic rules.",
                confidence=0.9,
                tests_passed=passed_count,
                tests_failed=failed_count,
                newly_failing_tests=[],
                resolved_tests=[],
            )
