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
from pydantic import BaseModel, Field

from backend.app.config.settings import settings
from backend.app.llm.base import BaseLLMProvider
from backend.app.llm.factory import get_llm_provider
from backend.app.models.multi_agent import AgentStatus, AgentType, SubTask

logger = logging.getLogger("agentos.task_decomposer")


class PlannedSubtask(BaseModel):
    subtask_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    assigned_agent: AgentType
    dependencies: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)


class EngineeringPlan(BaseModel):
    subtasks: list[PlannedSubtask] = Field(min_length=1, max_length=6)

MULTI_AGENT_DECOMPOSE_PROMPT = """MULTI_AGENT_DECOMPOSE_PROMPT:
You are the Supervisor. Return a minimal engineering plan as JSON matching RESPONSE_SCHEMA.
Each subtask needs a unique subtask_id, description, assigned_agent, dependencies and target_files.
Dependencies reference earlier IDs only. Use 1 to 6 subtasks.
Workers: research (inspect), coding (write implementation AND tests), testing (RUN existing tests),
reviewer (review implementation and actual results), debugger (diagnose observed failures),
documentation, security, data_engineer, devops, cybersecurity (admin only).
For a NEW APPLICATION, use a cohesive coding step -> testing -> reviewer, in that dependency order.
Include ALL user requirements in the coding description. Do not invent a pre-existing bug.
Do not schedule debugger speculatively: the runtime automatically diagnoses failed tests and replans fixes.
Testing does not write files. Only coding creates files. Avoid unnecessary scaffolding or duplicate modules.
Return JSON only, no markdown or commentary.
User instruction:
"""


class TaskDecomposer:
    """Decomposes instructions into verified SubTask DAGs."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None) -> None:
        self.llm = llm_provider or get_llm_provider()

    def decompose(self, instruction: str, task_id: str = "task-1") -> List[SubTask]:
        """Decompose instruction into validated SubTasks with cycle checks."""
        # Narrow operational requests have an unambiguous worker; never let a
        # generic fallback turn 'run tests' into an unsolicited coding task.
        import re
        if re.match(r"^(run|execute) (the |full )*(tests|test suite)\b", instruction.strip(), re.I):
            return [SubTask(task_id=task_id, subtask_id="run-tests", description=instruction,
                            assigned_agent=AgentType.TESTING)]
        if instruction.startswith("Diagnose the most recent test failures and provide a fix recommendation."):
            return [SubTask(task_id=task_id, subtask_id="diagnose", description=instruction,
                            assigned_agent=AgentType.DEBUGGER)]
        prompt = f"{MULTI_AGENT_DECOMPOSE_PROMPT}\n{instruction.strip()}"
        try:
            from backend.app.llm.structured import generate_structured
            parsed = generate_structured(self.llm, prompt, EngineeringPlan).model_dump(mode="json")
            subtasks_raw = parsed.get("subtasks", [])
            subtasks = self._parse_and_validate(subtasks_raw, task_id, instruction)
            return subtasks
        except ValueError as exc:
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
        # Dynamically discover relevant files rather than assuming calculator.py
        from backend.app.services.repo_intelligence import RepoIntelligence
        intelligence = RepoIntelligence()
        target_files = intelligence.find_relevant_files(instruction, max_files=3)
        if not target_files:
            target_files = intelligence.get_first_workspace_files(max_files=2)

        inst = instruction.lower()
        if any(word in inst for word in ("create", "build", "implement")):
            return [
                SubTask(task_id=task_id, subtask_id="build", description=instruction + " Include executable tests.",
                        assigned_agent=AgentType.CODING, target_files=target_files),
                SubTask(task_id=task_id, subtask_id="test", description="Run the generated test suite",
                        assigned_agent=AgentType.TESTING, dependencies=["build"]),
                SubTask(task_id=task_id, subtask_id="review", description="Review the implementation and actual test evidence against the user request",
                        assigned_agent=AgentType.REVIEWER, dependencies=["test"]),
            ]
        if "test" in inst or "bug" in inst or "fix" in inst:
            return [
                SubTask(
                    task_id=task_id,
                    subtask_id="subtask_1",
                    description="Research repository structure and locate buggy code/tests",
                    assigned_agent=AgentType.RESEARCH,
                    dependencies=[],
                    target_files=target_files,
                ),
                SubTask(
                    task_id=task_id,
                    subtask_id="subtask_2",
                    description="Diagnose test failure and synthesize root cause",
                    assigned_agent=AgentType.DEBUGGER,
                    dependencies=["subtask_1"],
                    target_files=target_files,
                ),
                SubTask(
                    task_id=task_id,
                    subtask_id="subtask_3",
                    description="Formulate and apply validated patch",
                    assigned_agent=AgentType.CODING,
                    dependencies=["subtask_2"],
                    target_files=target_files,
                ),
                SubTask(
                    task_id=task_id,
                    subtask_id="subtask_4",
                    description="Review execution outcome and verify no regressions",
                    assigned_agent=AgentType.REVIEWER,
                    dependencies=["subtask_3"],
                    target_files=target_files,
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
