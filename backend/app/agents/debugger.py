"""
AgentOS Phase 4 — Debugger Agent with structured Root Cause Diagnosis.

Iterative debugging cycle & structured diagnosis:
1. Takes failure evidence and code investigation results.
2. Synthesizes structured DebugDiagnosis (root cause, affected files/symbols, fix).
3. Connects to PatchValidator and PatchApplier for safe mutation execution.
4. Strictly read-only analysis during diagnosis — zero direct file modification.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from backend.app.code.patch.applier import PatchApplier, ApplyResult, RollbackResult
from backend.app.code.patch.models import Patch, PatchFile, PatchHunk, PatchRollbackRecord, PatchStatus, compute_file_hash, compute_patch_hash
from backend.app.code.patch.validator import PatchValidator
from backend.app.config.settings import settings
from backend.app.llm.base import BaseLLMProvider
from backend.app.llm.factory import get_llm_provider
from backend.app.models.coding import DebugDiagnosis, FailureInfo, InvestigationResult
from backend.app.models.tool import ToolRequest
from backend.app.services.test_service import TestService
from backend.app.tools.registry import ToolRegistry

logger = logging.getLogger("agentos.debugger")

DEBUGGER_PROMPT = """DEBUGGER_PROMPT:
You are an expert Software Debugger Agent for AgentOS.
Analyze the test failure and code investigation evidence to produce a structured diagnosis and recommended fix.

Output ONLY a JSON object:
{
    "root_cause": "Clear statement of the underlying bug",
    "affected_files": ["calculator.py"],
    "affected_symbols": ["add"],
    "explanation": "Technical explanation of how the bug manifests and affects test execution",
    "recommended_fix": "Concrete implementation instructions",
    "confidence": 0.95,
    "risks": []
}

Evidence:
"""


from dataclasses import dataclass, field

@dataclass
class DebuggerState:
    resolved: bool = False
    iterations: int = 0
    patches_applied: List[str] = field(default_factory=list)


class DebuggerAgent:
    """Automates diagnosis, patch formulation, validation, and safe application."""

    def __init__(
        self,
        task_id: str = "debug-task",
        llm_provider: Optional[BaseLLMProvider] = None,
        max_iterations: int = 3,
        framework: str = "pytest",
        strict: bool = False,
    ) -> None:
        self.task_id = task_id
        self.llm = llm_provider or get_llm_provider()
        self.max_iterations = min(max_iterations, 5)
        self.framework = framework
        self.strict = strict
        self.validator = PatchValidator()
        self.applier = PatchApplier()
        self.state = DebuggerState()
        self._last_patch: Optional[Patch] = None
        self._last_rollback: Optional[PatchRollbackRecord] = None

    def run_tests(self, path: Optional[str] = None) -> Dict[str, Any]:
        """Run tests using test service or registered tool."""
        return TestService.run_tests(framework=self.framework, path=path)

    def diagnose(self, failures: List[FailureInfo], investigation: InvestigationResult) -> DebugDiagnosis:
        """Formulate a structured DebugDiagnosis without modifying any code."""
        prompt = (
            f"{DEBUGGER_PROMPT}\n"
            f"Failures: {json.dumps([f.model_dump(exclude={'traceback'}) for f in failures[:5]])}\n"
            f"Investigation: {json.dumps(investigation.model_dump())}"
        )
        try:
            from backend.app.llm.structured import generate_structured
            return generate_structured(self.llm, prompt, DebugDiagnosis)
        except Exception as exc:
            if self.strict:
                raise RuntimeError(f"Model diagnosis unavailable: {exc}") from exc
            logger.warning("Debugger diagnosis LLM fallback: %s", exc)
            return DebugDiagnosis(
                root_cause=investigation.suspected_root_cause or "Assertion mismatch in implementation",
                affected_files=investigation.affected_files or [],
                affected_symbols=[s.get("name", "") for s in investigation.relevant_symbols if isinstance(s, dict)],
                explanation=investigation.evidence or "Test assertions failed against current code.",
                recommended_fix=investigation.recommended_change or "Update function logic to satisfy tests.",
                confidence=0.85,
                risks=[],
            )

    def validate_proposed_patch(self, patch: Patch) -> Dict[str, Any]:
        """Validate proposed patch through PatchValidator."""
        val_result = self.validator.validate(patch)
        if val_result.valid:
            patch.patch_hash = val_result.patch_hash
            patch.status = PatchStatus.VALIDATED
            self._last_patch = patch
        else:
            patch.status = PatchStatus.FAILED

        return {
            "valid": val_result.valid,
            "patch_hash": val_result.patch_hash,
            "errors": val_result.errors,
        }

    def apply_patch(self, patch_or_hash: Any, approved_patch_hash: Optional[str] = None) -> ApplyResult:
        """Apply approved patch to workspace using PatchApplier."""
        if isinstance(patch_or_hash, Patch):
            patch = patch_or_hash
            p_hash = approved_patch_hash or patch.patch_hash or ""
        else:
            p_hash = str(patch_or_hash)
            patch = self._last_patch or Patch(patch_id="p-latest", task_id=self.task_id, description="Auto patch", files=[])

        res = self.applier.apply(patch, p_hash)
        if res.success:
            self.state.patches_applied.append(p_hash)
            if res.rollback_record:
                self._last_rollback = res.rollback_record
        return res

    def verify_fix(self, path: Optional[str] = None) -> bool:
        """Run tests to verify if patch resolved issues."""
        res = self.run_tests(path)
        passed = bool(res.get("success") and res.get("data", {}).get("passed", False))
        if passed:
            self.state.resolved = True
        return passed

    def rollback(self, rollback_record: Optional[PatchRollbackRecord] = None) -> RollbackResult:
        """Roll back patch safely."""
        rb = rollback_record or self._last_rollback
        if not rb:
            return RollbackResult(success=False, error="No rollback record available")
        return self.applier.rollback(rb, self.task_id)
