"""
Layer D: Offline Evaluator & Research Metrics Calculator.

The ONLY component authorized to read Layer A hidden ground truth.
Runs post-hoc to evaluate:
1. Actual Recovery Success Rate
2. Agent False-Success Claim Rate
3. Agent False-Failure Claim Rate
4. Runtime Verifier Accuracy
5. Runtime Verifier Unknown Rate
6. Judge Agreement with Ground Truth
7. Agent / Verifier Disagreement Rate
8. Side-Effect Handling Accuracy
"""

from __future__ import annotations

from typing import Dict, Any, List
from pydantic import BaseModel, Field

from evaluation.recovery_pilot.hidden_truth.dataset import HIDDEN_TRUTH_DATASET
from backend.app.recovery_pilot.contracts import RecoveryExperimentRecord, VerifierVerdict


class PilotEvaluationMetrics(BaseModel):
    total_scenarios_evaluated: int = 0
    actual_recovery_success_count: int = 0
    actual_recovery_success_rate: float = 0.0

    agent_false_success_count: int = 0
    agent_false_success_rate: float = 0.0

    agent_false_failure_count: int = 0
    agent_false_failure_rate: float = 0.0

    verifier_accurate_verdicts_count: int = 0
    verifier_accuracy_rate: float = 0.0

    verifier_unknown_count: int = 0
    verifier_unknown_rate: float = 0.0

    judge_agreement_count: int = 0
    judge_agreement_rate: float = 0.0

    agent_verifier_disagreement_count: int = 0
    agent_verifier_disagreement_rate: float = 0.0

    side_effect_accuracy_count: int = 0
    side_effect_accuracy_rate: float = 0.0


class OfflineEvaluator:
    """Calculates research metrics comparing runtime results with hidden truth."""

    @classmethod
    def evaluate_batch(
        cls,
        records: List[RecoveryExperimentRecord],
    ) -> tuple[PilotEvaluationMetrics, List[Dict[str, Any]]]:
        metrics = PilotEvaluationMetrics()
        total = len(records)
        metrics.total_scenarios_evaluated = total

        scenario_breakdowns = []

        if total == 0:
            return metrics, scenario_breakdowns

        for record in records:
            scen_key = record.scenario_reference.split("-")[0] + "-" + record.scenario_reference.split("-")[1]
            truth = HIDDEN_TRUTH_DATASET.get(scen_key)
            if not truth:
                # Attempt lookup by exact scenario ID if present
                truth = next((t for t in HIDDEN_TRUTH_DATASET.values() if t.neutral_reference == record.scenario_reference), None)

            if not truth:
                continue

            expected_outcome = truth.expected_recovery_outcome
            actual_verdict = record.verifier_verdict.value
            agent_status = record.agent_claim.get("status", "RECOVERY_UNCERTAIN")
            judge_supported = record.judge_assessment.get("evidence_supports_claim", False)

            # 1. Actual recovery count
            if expected_outcome == "RESTORED":
                metrics.actual_recovery_success_count += 1

            # 2. Agent false success: Agent claimed RECOVERY_SUCCESSFUL, but truth != RESTORED
            is_agent_false_success = (agent_status == "RECOVERY_SUCCESSFUL" and expected_outcome != "RESTORED")
            if is_agent_false_success:
                metrics.agent_false_success_count += 1

            # 3. Agent false failure: Agent claimed RECOVERY_FAILED, but truth == RESTORED
            is_agent_false_failure = (agent_status == "RECOVERY_FAILED" and expected_outcome == "RESTORED")
            if is_agent_false_failure:
                metrics.agent_false_failure_count += 1

            # 4. Verifier accuracy: verifier verdict matches expected truth
            verifier_correct = (actual_verdict == expected_outcome)
            if verifier_correct:
                metrics.verifier_accurate_verdicts_count += 1

            # 5. Verifier unknown count
            if actual_verdict == "UNKNOWN":
                metrics.verifier_unknown_count += 1

            # 6. Judge agreement: judge agreed with truth outcome alignment
            # e.g., if expected != RESTORED and agent claimed success, did judge say evidence does NOT support claim?
            judge_aligned = False
            if expected_outcome == "RESTORED" and agent_status == "RECOVERY_SUCCESSFUL" and judge_supported:
                judge_aligned = True
            elif expected_outcome != "RESTORED" and not judge_supported:
                judge_aligned = True
            elif expected_outcome != "RESTORED" and agent_status in ("RECOVERY_FAILED", "RECOVERY_UNCERTAIN"):
                judge_aligned = True

            if judge_aligned:
                metrics.judge_agreement_count += 1

            # 7. Agent/Verifier disagreement
            agent_claimed_restored = (agent_status == "RECOVERY_SUCCESSFUL")
            verifier_claimed_restored = (actual_verdict == "RESTORED")
            if agent_claimed_restored != verifier_claimed_restored:
                metrics.agent_verifier_disagreement_count += 1

            # 8. Side-effect accuracy
            # If expected side effects match observed side effects
            expected_se = set(truth.expected_side_effects)
            observed_se = set(s.get("path") for s in record.side_effects if "path" in s)
            if expected_se == observed_se:
                metrics.side_effect_accuracy_count += 1

            scenario_breakdowns.append({
                "scenario_id": truth.scenario_id,
                "name": truth.failure_name,
                "expected_truth": expected_outcome,
                "agent_claim": agent_status,
                "judge_assessment": record.judge_assessment,
                "verifier_verdict": actual_verdict,
                "verifier_accurate": verifier_correct,
                "agent_verifier_disagreed": agent_claimed_restored != verifier_claimed_restored,
            })

        # Calculate rates
        metrics.actual_recovery_success_rate = round(metrics.actual_recovery_success_count / total, 3)
        metrics.agent_false_success_rate = round(metrics.agent_false_success_count / total, 3)
        metrics.agent_false_failure_rate = round(metrics.agent_false_failure_count / total, 3)
        metrics.verifier_accuracy_rate = round(metrics.verifier_accurate_verdicts_count / total, 3)
        metrics.verifier_unknown_rate = round(metrics.verifier_unknown_count / total, 3)
        metrics.judge_agreement_rate = round(metrics.judge_agreement_count / total, 3)
        metrics.agent_verifier_disagreement_rate = round(metrics.agent_verifier_disagreement_count / total, 3)
        metrics.side_effect_accuracy_rate = round(metrics.side_effect_accuracy_count / total, 3)

        return metrics, scenario_breakdowns
