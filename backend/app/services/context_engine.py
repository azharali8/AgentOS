"""
AgentOS Phase 13 — Bounded Context Engine.

Intelligently manages context assembly for specialized agents:
- Repository-aware context retrieval (files, AST symbols, entry points)
- Agent-specific context prioritization (Testing gets tests/configs, Coding gets targets/diagnoses)
- Explains WHY each file/symbol was chosen for complete auditability
- Enforces strict token budgets and dynamic compression
- Prevents context bloat and duplicates
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.app.models.multi_agent import AgentType
from backend.app.services.repo_intelligence import RepoIntelligence

logger = logging.getLogger("agentos.context_engine")


class FileContext(BaseModel):
    relative_path: str
    relevance_score: int
    why_selected: str
    content_snippet: str
    symbols: List[str] = Field(default_factory=list)
    line_count: int = 0


class ContextBundle(BaseModel):
    task_id: str
    target_agent: str
    files: Dict[str, FileContext]
    previous_events: List[Dict[str, Any]] = Field(default_factory=list)
    total_tokens_estimated: int = 0
    token_budget: int = 4000
    budget_exceeded: bool = False
    selection_rationale: Dict[str, str] = Field(default_factory=dict)


class ContextEngine:
    """Production-grade context assembly with audit explanation."""

    def __init__(self) -> None:
        self.intelligence = RepoIntelligence()

    def assemble_context(
        self,
        task_id: str,
        instruction: str,
        target_agent: AgentType,
        token_budget: int = 4000,
        explicit_files: Optional[List[str]] = None,
        recent_events: Optional[List[Dict[str, Any]]] = None,
    ) -> ContextBundle:
        """Construct bounded, prioritized context bundle tailored to agent role."""
        files_dict: Dict[str, FileContext] = {}
        rationale_dict: Dict[str, str] = {}
        total_tokens = 0

        # 1. Resolve relevant files
        candidate_files = explicit_files or []
        if not candidate_files:
            candidate_files = self.intelligence.find_relevant_files(instruction, max_files=4)
        if not candidate_files:
            # Dynamically discover the first available file in the workspace
            # instead of assuming a hardcoded filename like calculator.py
            candidate_files = self.intelligence.get_first_workspace_files(max_files=2)


        # 2. Agent-specific prioritization filter
        for rel_path in candidate_files:
            why = ""
            score = 3
            if target_agent == AgentType.TESTING and ("test" in rel_path.lower() or "tests/" in rel_path):
                score += 5
                why = "Test file targeted for verification and test harness execution"
            elif target_agent == AgentType.CODING:
                score += 4
                why = "Source file identified for patch formulation and logic modifications"
            elif target_agent == AgentType.DEBUGGER:
                score += 5
                why = "Suspect source or test file analyzed for root cause diagnosis"
            elif target_agent == AgentType.DEVOPS and any(k in rel_path.lower() for k in ("docker", "compose", ".github", "yaml", "toml")):
                score += 6
                why = "Infrastructure / CI configuration file detected"
            else:
                why = "Keyword relevance match against user task instruction"

            # Fetch content and symbols
            content_str = ""
            sym_names = []
            try:
                read_res = self.intelligence.reader.read(rel_path, start_line=1, end_line=60)
                content_str = "\n".join(read_res.lines) if read_res.lines else ""
                if rel_path.endswith(".py"):
                    syms = self.intelligence.extract_file_symbols(rel_path)
                    sym_names = [s["name"] for s in syms.get("symbols", [])]
            except Exception:
                pass

            # Estimate tokens (~4 chars per token)
            est_tokens = len(content_str) // 4 + len(sym_names) * 3
            if total_tokens + est_tokens > token_budget and len(files_dict) >= 1:
                # Truncate to fit budget
                available_chars = max(100, (token_budget - total_tokens) * 4)
                content_str = content_str[:available_chars] + "\n... [Context truncated to fit token budget]"
                est_tokens = len(content_str) // 4

            total_tokens += est_tokens
            rationale_dict[rel_path] = why
            files_dict[rel_path] = FileContext(
                relative_path=rel_path,
                relevance_score=score,
                why_selected=why,
                content_snippet=content_str,
                symbols=sym_names,
                line_count=len(content_str.splitlines()),
            )

        return ContextBundle(
            task_id=task_id,
            target_agent=target_agent.value if hasattr(target_agent, "value") else str(target_agent),
            files=files_dict,
            previous_events=recent_events or [],
            total_tokens_estimated=total_tokens,
            token_budget=token_budget,
            budget_exceeded=total_tokens > token_budget,
            selection_rationale=rationale_dict,
        )
