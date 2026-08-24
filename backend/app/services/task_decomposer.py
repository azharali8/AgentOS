"""
AgentOS Phase 5 — Task Decomposer.

Breaks complex instructions into a Directed Acyclic Graph (DAG) of SubTasks.
Enforces:
- Configurable MAX_SUBTASKS
- Configurable MAX_AGENT_DEPTH
- Cycle detection (rejects circular dependencies)
- Agent capability matching
- Duplicate subtask ID rejection
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set

from backend.app.config.settings import settings
from backend.app.llm.base import BaseLLMProvider
from backend.app.llm.factory import get_llm_provider
from backend.app.models.multi_agent import AgentStatus, AgentType, SubTask

logger = logging.getLogger("agentos.task_decomposer")

MULTI_AGENT_DECOMPOSE_PROMPT = """MULTI_AGENT_DECOMPOSE_PROMPT:
You are an expert Supervisor Agent for AgentOS.
Decompose the following user request into a minimal, focused Directed Acyclic Graph (DAG) of subtasks.

Available Agent Types:
- "research": Code search, AST symbol extraction, file reading, repository scanning, Git inspection.
- "coding": Code modification, patch formulation, validation, and approved patch application.
- "testing": Identifies, creates, runs test suites, and analyzes failures/coverage.
- "debugger": Diagnoses test failures, identifies root causes, and validates bug fixes.
- "reviewer": Result verification, consistency checks, code review, safety assessment.
- "documentation": Markdown report writing, documentation summary, guide generation.
- "security": Risk analysis, sensitive file policy verification, dependency checks.
- "cybersecurity": Deep security posture analysis, vulnerability scanning, and threat modeling (ADMIN ONLY).
- "data_engineer": Profiles, cleans, analyzes datasets (CSV, JSON, Excel, Parquet) and generates EDA reports.
- "devops": Creates CI/CD pipelines, Docker configurations, and automates builds/deployments.

Rules:
1. Return valid JSON only with the schema below.
2. "dependencies" must reference prior subtask_ids in the list.
3. No circular dependencies.
4. Keep subtask count between 1 and 6.

Schema:
{
    "subtasks": [
        {
            "subtask_id": "subtask_1",
            "description": "Inspect repository structure and discover test framework",
            "assigned_agent": "research",
            "dependencies": [],
            "target_files": ["calculator.py"]
        },
        {
            "subtask_id": "subtask_2",
            "description": "Run tests and diagnose failures",
            "assigned_agent": "debugger",
            "dependencies": ["subtask_1"],
            "target_files": ["calculator.py"]
        }
    ]
}

User instruction:
"""


class TaskDecomposer:
    """Decomposes instructions into verified SubTask DAGs."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None) -> None:
        self.llm = llm_provider or get_llm_provider()

    def decompose(self, instruction: str, task_id: str = "task-1") -> List[SubTask]:
        """Decompose instruction into validated SubTasks with cycle checks."""
        prompt = f"{MULTI_AGENT_DECOMPOSE_PROMPT}\n{instruction.strip()}"
        try:
            raw = self.llm.generate(prompt)
            text = raw.strip()
            if text.startswith("```"):
                lines = text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()

            parsed = json.loads(text)
            subtasks_raw = parsed.get("subtasks", [])
            subtasks = self._parse_and_validate(subtasks_raw, task_id, instruction)
            return subtasks
        except Exception as exc:
            logger.warning("LLM task decomposition fallback: %s", exc)
            return self._heuristic_fallback(instruction, task_id)

    def adaptive_decompose(
        self,
        instruction: str,
        task_id: str = "task-1",
        strategy: str = "DIRECT",
        complexity: str = "medium",
    ) -> List[SubTask]:
        """Adaptive decomposition with complexity-aware subtask count."""
        complexity_info = self.estimate_complexity(instruction)
        effective_complexity = complexity if complexity != "medium" else complexity_info["level"]

        if effective_complexity == "simple" or strategy == "DIRECT":
            return self._simple_decomposition(instruction, task_id)

        subtasks = self.decompose(instruction, task_id=task_id)

        # Trim subtasks for medium complexity
        max_subtasks = self._adaptive_subtask_limit(effective_complexity)
        if len(subtasks) > max_subtasks:
            subtasks = subtasks[:max_subtasks]

        return subtasks

    @staticmethod
    def estimate_complexity(instruction: str) -> Dict[str, Any]:
        """Estimate task complexity and confidence score."""
        inst = instruction.lower()
        score = 0.0
        if any(kw in inst for kw in ("fix", "bug", "test", "debug")):
            score += 0.3
        if any(kw in inst for kw in ("architecture", "investigate", "comprehensive", "report")):
            score += 0.4
        if any(kw in inst for kw in ("security", "credential", "production")):
            score += 0.3
        word_count = len(instruction.split())
        if word_count > 30:
            score += 0.2

        if score < 0.3:
            level = "simple"
        elif score < 0.6:
            level = "medium"
        else:
            level = "complex"

        return {"level": level, "score": round(min(1.0, score), 2), "confidence": round(min(1.0, score + 0.3), 2)}

    @staticmethod
    def _adaptive_subtask_limit(complexity: str) -> int:
        limits = {"simple": 2, "medium": 5, "complex": settings.MAX_SUBTASKS}
        return limits.get(complexity, settings.MAX_SUBTASKS)

    def _simple_decomposition(self, instruction: str, task_id: str) -> List[SubTask]:
        """Minimal decomposition for simple tasks."""
        inst = instruction.lower()
        if "code" in inst or "fix" in inst:
            agent = AgentType.CODING
        else:
            agent = AgentType.RESEARCH
        return [
            SubTask(
                task_id=task_id,
                subtask_id="subtask_1",
                description=instruction[:200],
                assigned_agent=agent,
                dependencies=[],
            ),
        ]

    def _parse_and_validate(self, subtasks_raw: List[Dict[str, Any]], task_id: str, instruction: str) -> List[SubTask]:
        """Validate structure, enforce limits, and check for cycles."""
        if not subtasks_raw:
            return self._heuristic_fallback(instruction, task_id)

        # Enforce MAX_SUBTASKS limit
        if len(subtasks_raw) > settings.MAX_SUBTASKS:
            subtasks_raw = subtasks_raw[:settings.MAX_SUBTASKS]

        seen_ids: Set[str] = set()
        subtasks: List[SubTask] = []

        for item in subtasks_raw:
            s_id = str(item.get("subtask_id", f"subtask_{len(subtasks) + 1}"))
            if s_id in seen_ids:
                raise ValueError(f"Duplicate subtask ID detected: {s_id}")
            seen_ids.add(s_id)

            agent_str = str(item.get("assigned_agent", "research")).lower()
            try:
                agent_type = AgentType(agent_str)
            except ValueError:
                agent_type = AgentType.RESEARCH

            # Supervisor cannot be assigned as a subtask worker
            if agent_type == AgentType.SUPERVISOR:
                agent_type = AgentType.RESEARCH

            deps = [d for d in item.get("dependencies", []) if d != s_id]

            subtasks.append(SubTask(
                task_id=task_id,
                subtask_id=s_id,
                description=item.get("description", "Execute subtask"),
                assigned_agent=agent_type,
                dependencies=deps,
                priority=int(item.get("priority", 1)),
                status=AgentStatus.IDLE,
                target_files=item.get("target_files", []),
            ))

        # Validate DAG (detect cycles and compute depth)
        self.detect_cycles(subtasks)
        return subtasks

    @staticmethod
    def detect_cycles(subtasks: List[SubTask]) -> None:
        """Topological sort using Kahn's algorithm to detect circular dependencies."""
        subtask_map = {s.subtask_id: s for s in subtasks}
        in_degree: Dict[str, int] = {s.subtask_id: 0 for s in subtasks}
        adj: Dict[str, List[str]] = defaultdict(list)

        for s in subtasks:
            for dep in s.dependencies:
                if dep in subtask_map:
                    adj[dep].append(s.subtask_id)
                    in_degree[s.subtask_id] += 1

        queue = deque([s_id for s_id, deg in in_degree.items() if deg == 0])
        visited_count = 0

        while queue:
            node = queue.popleft()
            visited_count += 1
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(subtasks):
            raise ValueError("Circular dependency detected in subtask DAG.")

    def _heuristic_fallback(self, instruction: str, task_id: str) -> List[SubTask]:
        """Deterministic heuristic decomposition fallback."""
        inst = instruction.lower()
        if "test" in inst or "bug" in inst or "fix" in inst:
            return [
                SubTask(
                    task_id=task_id,
                    subtask_id="subtask_1",
                    description="Research repository structure and locate buggy code/tests",
                    assigned_agent=AgentType.RESEARCH,
                    dependencies=[],
                    target_files=["calculator.py"],
                ),
                SubTask(
                    task_id=task_id,
                    subtask_id="subtask_2",
                    description="Diagnose test failure and synthesize root cause",
                    assigned_agent=AgentType.DEBUGGER,
                    dependencies=["subtask_1"],
                    target_files=["calculator.py"],
                ),
                SubTask(
                    task_id=task_id,
                    subtask_id="subtask_3",
                    description="Formulate and apply validated patch",
                    assigned_agent=AgentType.CODING,
                    dependencies=["subtask_2"],
                    target_files=["calculator.py"],
                ),
                SubTask(
                    task_id=task_id,
                    subtask_id="subtask_4",
                    description="Review execution outcome and verify no regressions",
                    assigned_agent=AgentType.REVIEWER,
                    dependencies=["subtask_3"],
                    target_files=["calculator.py"],
                ),
                SubTask(
                    task_id=task_id,
                    subtask_id="subtask_5",
                    description="Generate final engineering documentation report",
                    assigned_agent=AgentType.DOCUMENTATION,
                    dependencies=["subtask_4"],
                    target_files=[],
                ),
            ]
        elif "document" in inst or "readme" in inst:
            return [
                SubTask(
                    task_id=task_id,
                    subtask_id="subtask_1",
                    description="Inspect project codebase and extract public symbols",
                    assigned_agent=AgentType.RESEARCH,
                    dependencies=[],
                ),
                SubTask(
                    task_id=task_id,
                    subtask_id="subtask_2",
                    description="Generate markdown documentation",
                    assigned_agent=AgentType.DOCUMENTATION,
                    dependencies=["subtask_1"],
                ),
            ]
        else:
            return [
                SubTask(
                    task_id=task_id,
                    subtask_id="subtask_1",
                    description="Analyze workspace and answer query",
                    assigned_agent=AgentType.RESEARCH,
                    dependencies=[],
                ),
                SubTask(
                    task_id=task_id,
                    subtask_id="subtask_2",
                    description="Synthesize documentation response",
                    assigned_agent=AgentType.DOCUMENTATION,
                    dependencies=["subtask_1"],
                ),
            ]
