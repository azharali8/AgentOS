"""
AgentOS Phase 4 — Code Investigator Agent.

Uses Phase 3 codebase intelligence tools (code.search, code.read, code.symbols, git.diff)
to investigate suspected buggy functions, inspect source definitions, and assemble
structured evidence for root-cause diagnosis.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from backend.app.llm.base import BaseLLMProvider
from backend.app.llm.factory import get_llm_provider
from backend.app.models.coding import FailureInfo, InvestigationResult
from backend.app.models.tool import ToolRequest
from backend.app.tools.registry import ToolRegistry

logger = logging.getLogger("agentos.investigator")

INVESTIGATION_PROMPT = """INVESTIGATION_PROMPT:
You are an expert Code Investigator for AgentOS.
Given the test failure and the code snippets retrieved from the repository,
formulate structured investigation evidence.

Output ONLY a JSON object:
{
    "affected_files": ["calculator.py"],
    "relevant_symbols": [{"name": "add", "type": "function", "line": 1}],
    "evidence": "Detailed explanation of what is buggy in the implementation",
    "suspected_root_cause": "Specific bug explanation",
    "confidence": 0.95,
    "recommended_change": "Clear description of the code correction"
}

Failure information:
"""


class CodeInvestigatorAgent:
    """Investigates source code context using safe codebase tools and forms evidence."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None) -> None:
        self.llm = llm_provider or get_llm_provider()

    def investigate(self, failures: List[FailureInfo], instruction: str = "") -> InvestigationResult:
        """Gather code snippets using code tools and summarize investigation."""
        code_tool = ToolRegistry.get("code")
        gathered_evidence: List[str] = []
        affected_files: List[str] = []
        symbols: List[Dict[str, Any]] = []

        for fail in failures:
            for target_file in fail.likely_files:
                if target_file not in affected_files:
                    affected_files.append(target_file)

                # Extract symbols
                if code_tool and target_file.endswith(".py"):
                    sym_req = ToolRequest(
                        tool_name="code",
                        arguments={"operation": "symbols", "path": target_file}
                    )
                    sym_res = code_tool.execute(sym_req)
                    if sym_res.success and sym_res.data:
                        symbols.extend(sym_res.data.get("symbols", []))

                # Read source snippet
                if code_tool:
                    read_req = ToolRequest(
                        tool_name="code",
                        arguments={"operation": "read", "path": target_file, "start_line": 1, "end_line": 50}
                    )
                    read_res = code_tool.execute(read_req)
                    if read_res.success and read_res.data:
                        lines = read_res.data.get("lines", [])
                        snippet = "\n".join(f"{l['line']}: {l['content']}" for l in lines)
                        gathered_evidence.append(f"File {target_file}:\n{snippet}")

        # Assemble prompt for LLM investigation synthesis
        fail_summary = "\n".join(f"Test: {f.test_name}, Error: {f.message}, File: {f.file_path}" for f in failures)
        code_context = "\n\n".join(gathered_evidence)
        prompt = (
            f"{INVESTIGATION_PROMPT}\n"
            f"Instruction: {instruction}\n"
            f"Failures:\n{fail_summary}\n\n"
            f"Code Context:\n{code_context}"
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
            return InvestigationResult(**parsed)
        except Exception as exc:
            logger.warning("Investigation LLM synthesis error: %s", exc)
            return InvestigationResult(
                affected_files=affected_files or ["calculator.py"],
                relevant_symbols=symbols,
                evidence=f"Retrieved {len(gathered_evidence)} code sections.",
                suspected_root_cause=failures[0].message if failures else "Unknown issue",
                confidence=0.8,
                recommended_change="Review and correct function implementation according to tests.",
            )
