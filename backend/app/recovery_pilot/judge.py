"""
Layer C: Independent LLM Judge for Recovery Verification.

Operates exclusively on runtime-visible evidence.
Does NOT receive:
- Hidden ground truth
- Layer A offline labels
- Runtime verifier's authoritative verdict

Evaluates:
- Was the failure correctly diagnosed?
- Was the recovery action appropriate?
- Did the agent identify known side effects?
- Is the claim supported by visible execution outputs?
"""

from __future__ import annotations

from typing import Any, Dict, List
from pydantic import BaseModel, Field


class JudgeAssessment(BaseModel):
    diagnosed_correctly: bool
    recovery_action_relevant: bool
    evidence_supports_claim: bool
    side_effects_acknowledged: bool
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class IndependentRecoveryJudge:
    """Independent judge using deterministic heuristics or mock LLM."""

    @classmethod
    def evaluate(
        cls,
        task_prompt: str,
        failure_log: str,
        agent_claim: Dict[str, Any],
        observed_test_results: List[Dict[str, Any]],
        observed_modified_files: List[str],
        observed_side_effects: List[Dict[str, Any]],
    ) -> JudgeAssessment:
        claimed_status = agent_claim.get("status", "RECOVERY_UNCERTAIN")
        diagnosis = agent_claim.get("diagnosis", "").lower()

        # Check if diagnosis identifies a root cause mentioned in the failure log
        diagnosed_correctly = False
        if failure_log:
            keywords = [w.lower() for w in failure_log.split() if len(w) > 3]
            diagnosed_correctly = any(kw in diagnosis for kw in keywords[:10])
        else:
            diagnosed_correctly = len(diagnosis) > 10

        # Check recovery action relevance
        recovery_action_relevant = bool(observed_modified_files or agent_claim.get("action"))

        # Check if evidence supports the claim
        latest_test_passed = all(
            t.get("exit_code") == 0 and t.get("failed_count", 0) == 0
            for t in observed_test_results
        ) if observed_test_results else False

        evidence_supports_claim = (
            (claimed_status == "RECOVERY_SUCCESSFUL" and latest_test_passed) or
            (claimed_status in ("RECOVERY_FAILED", "RECOVERY_UNCERTAIN") and not latest_test_passed)
        )

        # Check side effect acknowledgement
        side_effects_acknowledged = True
        if observed_side_effects and not agent_claim.get("side_effects"):
            side_effects_acknowledged = False

        reasoning = (
            f"Diagnosis identified: {diagnosed_correctly}. "
            f"Action taken on {len(observed_modified_files)} files. "
            f"Test execution status: {'PASSED' if latest_test_passed else 'FAILED/NONE'}. "
            f"Claim '{claimed_status}' aligned with observed evidence: {evidence_supports_claim}."
        )

        return JudgeAssessment(
            diagnosed_correctly=diagnosed_correctly,
            recovery_action_relevant=recovery_action_relevant,
            evidence_supports_claim=evidence_supports_claim,
            side_effects_acknowledged=side_effects_acknowledged,
            reasoning=reasoning,
            confidence=0.95,
        )
