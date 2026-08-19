"""
AgentOS Phase 4 — Task Classifier Agent.

Classifies incoming user software engineering requests into structured categories
(e.g., test_failure, bug_fix, repository_analysis) using structured LLM outputs.
Read-only static analysis; never directly executes commands or modifies files.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from backend.app.llm.base import BaseLLMProvider
from backend.app.llm.factory import get_llm_provider
from backend.app.models.coding import TaskClassification, TaskType

logger = logging.getLogger("agentos.task_classifier")

TASK_CLASSIFIER_PROMPT = """TASK_CLASSIFIER_PROMPT:
You are an expert Software Engineering Task Classifier for AgentOS.
Analyze the user instruction and classify it into one of the following task types:
- "test_failure": When tests are failing or need to be run and fixed.
- "bug_fix": When a bug or incorrect behavior needs investigation and resolution.
- "repository_analysis": When the user asks to inspect, summarize, or analyze the codebase.
- "code_explanation": When the user wants to understand how code works.
- "code_change": Generic feature or refactoring change.

Return ONLY a JSON object with this exact schema:
{
    "task_type": "bug_fix" | "test_failure" | "repository_analysis" | "code_explanation" | "code_change",
    "requires_tests": true | false,
    "requires_code_change": true | false,
    "risk_level": "LOW" | "MEDIUM" | "HIGH",
    "reasoning": "brief explanation",
    "target_files_hint": ["optional/file/path.py"]
}

User instruction:
"""


class TaskClassifierAgent:
    """Classifies user requests into strongly-typed TaskClassification models."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None) -> None:
        self.llm = llm_provider or get_llm_provider()

    def classify(self, instruction: str) -> TaskClassification:
        """Classify user instruction."""
        prompt = f"{TASK_CLASSIFIER_PROMPT}\n{instruction.strip()}"
        try:
            raw_response = self.llm.generate(prompt)
            # Clean possible markdown wrapping
            text = raw_response.strip()
            if text.startswith("```"):
                lines = text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()

            parsed = json.loads(text)
            return TaskClassification(**parsed)
        except Exception as exc:
            logger.warning("Task classification fallback due to error: %s", exc)
            # Deterministic heuristic fallback
            inst_lower = instruction.lower()
            if "test" in inst_lower and ("fail" in inst_lower or "fix" in inst_lower or "run" in inst_lower):
                return TaskClassification(
                    task_type=TaskType.TEST_FAILURE,
                    requires_tests=True,
                    requires_code_change=True,
                    risk_level="HIGH",
                    reasoning="Heuristic match: test failure detected.",
                )
            elif "fix" in inst_lower or "bug" in inst_lower or "error" in inst_lower:
                return TaskClassification(
                    task_type=TaskType.BUG_FIX,
                    requires_tests=True,
                    requires_code_change=True,
                    risk_level="HIGH",
                    reasoning="Heuristic match: bug fix detected.",
                )
            elif "scan" in inst_lower or "analyze" in inst_lower or "structure" in inst_lower:
                return TaskClassification(
                    task_type=TaskType.REPOSITORY_ANALYSIS,
                    requires_tests=False,
                    requires_code_change=False,
                    risk_level="LOW",
                    reasoning="Heuristic match: repository analysis detected.",
                )
            else:
                return TaskClassification(
                    task_type=TaskType.BUG_FIX,
                    requires_tests=True,
                    requires_code_change=True,
                    risk_level="HIGH",
                    reasoning="Default classification fallback.",
                )
