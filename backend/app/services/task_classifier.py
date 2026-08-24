"""
AgentOS Phase 13 — Task Classifier.

Understands task complexity, required agents, risk levels, and approval requirements
BEFORE execution begins. Eliminates hardcoded, one-size-fits-all workflows.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

from backend.app.models.multi_agent import AgentType

logger = logging.getLogger("agentos.task_classifier")


class TaskCategory(str, Enum):
    SIMPLE_CODING = "SIMPLE_CODING"
    MULTI_FILE_CODING = "MULTI_FILE_CODING"
    DEBUGGING = "DEBUGGING"
    REFACTORING = "REFACTORING"
    TESTING = "TESTING"
    SECURITY_AUDIT = "SECURITY_AUDIT"
    DATA_ENGINEERING = "DATA_ENGINEERING"
    DEVOPS = "DEVOPS"
    DOCUMENTATION = "DOCUMENTATION"
    REPO_ANALYSIS = "REPO_ANALYSIS"
    ARCHITECTURE = "ARCHITECTURE"


class TaskClassification(BaseModel):
    category: TaskCategory
    required_agents: List[AgentType]
    complexity: str  # simple, medium, complex
    estimated_steps: int
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    requires_approval: bool
    requires_testing: bool
    recovery_strategy: str  # RETRY, REROUTE, REPLAN, ABORT
    rationale: str


class TaskClassifier:
    """Classifies user engineering requests and structures adaptive execution plans."""

    @classmethod
    def classify(cls, instruction: str) -> TaskClassification:
        inst_lower = instruction.lower()

        # 1. Security / Cybersecurity
        if any(w in inst_lower for w in ("security audit", "vulnerability", "credential", "threat", "cybersecurity", "cve")):
            return TaskClassification(
                category=TaskCategory.SECURITY_AUDIT,
                required_agents=[AgentType.SECURITY, AgentType.CYBERSECURITY, AgentType.SUPERVISOR],
                complexity="complex",
                estimated_steps=4,
                risk_level="CRITICAL",
                requires_approval=True,
                requires_testing=False,
                recovery_strategy="ABORT",
                rationale="Security audit requested; requires strict policy evaluation and administrative privileges.",
            )

        # 2. Data Engineering
        if any(w in inst_lower for w in ("dataset", "csv", "data pipeline", "cleaning", "profiling", "schema validation", "etl")):
            return TaskClassification(
                category=TaskCategory.DATA_ENGINEERING,
                required_agents=[AgentType.DATA_ENGINEER, AgentType.RESEARCH, AgentType.SUPERVISOR],
                complexity="medium",
                estimated_steps=3,
                risk_level="LOW",
                requires_approval=False,
                requires_testing=False,
                recovery_strategy="RETRY",
                rationale="Data engineering and dataset profiling request detected.",
            )

        # 3. DevOps & CI/CD
        if any(w in inst_lower for w in ("docker", "container", "ci/cd", "pipeline", "kubernetes", "workflow", "infra", "deploy")):
            return TaskClassification(
                category=TaskCategory.DEVOPS,
                required_agents=[AgentType.DEVOPS, AgentType.RESEARCH, AgentType.SUPERVISOR],
                complexity="medium",
                estimated_steps=3,
                risk_level="MEDIUM",
                requires_approval=True,
                requires_testing=False,
                recovery_strategy="RETRY",
                rationale="Infrastructure and container configuration request detected.",
            )

        # 4. Debugging & Root Cause Analysis
        if any(w in inst_lower for w in ("bug", "diagnose", "root cause", "fix failing", "traceback", "exception", "error in")):
            return TaskClassification(
                category=TaskCategory.DEBUGGING,
                required_agents=[AgentType.DEBUGGER, AgentType.CODING, AgentType.TESTING, AgentType.REVIEWER, AgentType.SUPERVISOR],
                complexity="complex",
                estimated_steps=5,
                risk_level="HIGH",
                requires_approval=True,
                requires_testing=True,
                recovery_strategy="REROUTE",
                rationale="Defect diagnosis requested; involves testing probe, root-cause diagnosis, and patch formulation.",
            )

        # 5. Testing
        if any(w in inst_lower for w in ("test suite", "run tests", "pytest", "unit test", "regression test", "coverage")):
            return TaskClassification(
                category=TaskCategory.TESTING,
                required_agents=[AgentType.TESTING, AgentType.RESEARCH, AgentType.SUPERVISOR],
                complexity="simple",
                estimated_steps=2,
                risk_level="LOW",
                requires_approval=False,
                requires_testing=True,
                recovery_strategy="REROUTE",
                rationale="Test harness execution and regression coverage requested.",
            )

        # 6. Multi-file coding / Refactoring
        if any(w in inst_lower for w in ("refactor", "across files", "multi-file", "restructure", "architecture")):
            return TaskClassification(
                category=TaskCategory.MULTI_FILE_CODING,
                required_agents=[AgentType.RESEARCH, AgentType.CODING, AgentType.TESTING, AgentType.REVIEWER, AgentType.SUPERVISOR],
                complexity="complex",
                estimated_steps=5,
                risk_level="HIGH",
                requires_approval=True,
                requires_testing=True,
                recovery_strategy="REPLAN",
                rationale="Complex multi-file modification or refactoring requested.",
            )

        # 7. Documentation
        if any(w in inst_lower for w in ("document", "readme", "architecture guide", "markdown", "docstring")):
            return TaskClassification(
                category=TaskCategory.DOCUMENTATION,
                required_agents=[AgentType.RESEARCH, AgentType.DOCUMENTATION, AgentType.SUPERVISOR],
                complexity="simple",
                estimated_steps=2,
                risk_level="LOW",
                requires_approval=False,
                requires_testing=False,
                recovery_strategy="RETRY",
                rationale="Documentation synthesis requested.",
            )

        # Default: Simple Coding
        return TaskClassification(
            category=TaskCategory.SIMPLE_CODING,
            required_agents=[AgentType.CODING, AgentType.TESTING, AgentType.REVIEWER, AgentType.SUPERVISOR],
            complexity="simple",
            estimated_steps=4,
            risk_level="MEDIUM",
            requires_approval=True,
            requires_testing=True,
            recovery_strategy="RETRY",
            rationale="Standard feature implementation or single-file logic update.",
        )
