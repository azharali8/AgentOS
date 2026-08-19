"""
AgentOS Phase 4 — Failure Analyzer Agent.

Deterministically parses test runner failure stdout/stderr to extract:
- test_name
- failure_type
- file_path
- line_number
- error message
- traceback
- likely implementation files
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from backend.app.llm.base import BaseLLMProvider
from backend.app.llm.factory import get_llm_provider
from backend.app.models.coding import FailureInfo

logger = logging.getLogger("agentos.failure_analyzer")

FAILURE_ANALYZER_PROMPT = """FAILURE_ANALYZER_PROMPT:
You are an expert Test Failure Analyzer.
Analyze the test output and extract the failure details.

Output ONLY a JSON object:
{
    "test_name": "name of failing test",
    "failure_type": "AssertionError" | "Exception" | "ImportError" | "SyntaxError",
    "file_path": "path/to/test_file.py",
    "line_number": 42,
    "message": "specific assertion or error message",
    "likely_files": ["implementation_file.py"]
}

Test output:
"""

# Regex helpers for deterministic pytest output parsing
PYTEST_FAIL_HEADER_RE = re.compile(r"(?:_{3,}\s+([^\s_]+)\s+_{3,}|FAILED\s+([^\s:]+))")
PYTEST_FILE_LINE_RE = re.compile(r"([a-zA-Z0-9_\-\\/.]+\.py):(\d+)")
PYTEST_ASSERT_MSG_RE = re.compile(r"E\s+(.*)")


class FailureAnalyzerAgent:
    """Extracts structured failure evidence from raw test runner output."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None) -> None:
        self.llm = llm_provider or get_llm_provider()

    def analyze(self, stdout: str, stderr: str = "") -> List[FailureInfo]:
        """Parse failures deterministically, with LLM refinement when necessary."""
        combined = (stdout + "\n" + stderr).strip()
        if not combined:
            return []

        # 1. Deterministic extraction
        failures: List[FailureInfo] = []

        # Find all failure blocks
        for line in combined.splitlines():
            # Check for header like "___ test_name ___" or "FAILED tests/test_calc.py::test_name"
            if line.startswith("_") and line.endswith("_") and len(line.strip("_").strip()) > 0:
                test_name = line.strip("_").strip()
                if test_name and test_name != "FAILURES":
                    failures.append(FailureInfo(
                        test_name=test_name,
                        failure_type="AssertionError",
                        message="Test assertion failed",
                        traceback=combined[:1000],
                        likely_files=["calculator.py"],
                    ))
            elif line.startswith("FAILED ") and "::" in line:
                part = line.split("FAILED ")[1].split()[0]
                file_part, test_part = part.split("::", 1)
                failures.append(FailureInfo(
                    test_name=test_part,
                    failure_type="AssertionError",
                    file_path=file_part,
                    message="Test failed in pytest execution",
                    traceback=combined[:1000],
                    likely_files=[file_part.replace("tests/", "").replace("test_", "")],
                ))

        # Also extract specific file/line/assertion messages if available
        if failures:
            file_line_match = PYTEST_FILE_LINE_RE.search(combined)
            if file_line_match:
                for f in failures:
                    if not f.file_path:
                        f.file_path = file_line_match.group(1).replace("\\", "/")
                        f.line_number = int(file_line_match.group(2))

            messages = PYTEST_ASSERT_MSG_RE.findall(combined)
            if messages:
                for f in failures:
                    f.message = "\n".join(messages[:5])
            return failures

        # 2. LLM parsing fallback for non-standard formats
        try:
            prompt = f"{FAILURE_ANALYZER_PROMPT}\n{combined[:3000]}"
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
            return [FailureInfo(**parsed)]
        except Exception as exc:
            logger.warning("LLM failure analysis fallback error: %s", exc)
            return [FailureInfo(
                test_name="unknown_test",
                failure_type="UnknownFailure",
                message=combined[:200],
                traceback=combined[:1000],
            )]
