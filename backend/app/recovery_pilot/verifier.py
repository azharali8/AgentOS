"""
Layer B: Read-Only Runtime Recovery Verifier for AgentOS.

Guarantees:
1. Purely read-only: does not modify files, tasks, approvals, checkpoints, or state.
2. Evaluates registered postconditions strictly against fresh, trustworthy ObservableEvidence.
3. Returns only RESTORED, NOT_RESTORED, or UNKNOWN.
4. Never converts missing or stale evidence into success.
5. Independent of Agent Claims and LLM Judge assessments.
"""

from __future__ import annotations

import time
import re
from typing import List, Dict, Any, Optional

from backend.app.recovery_pilot.contracts import (
    VerifierVerdict,
    EvidenceType,
    ObservableEvidence,
    PostconditionCheck,
    VerificationResult,
)


class ReadOnlyRecoveryVerifier:
    """Independent, read-only evaluator of observable recovery postconditions."""

    @classmethod
    def evaluate(
        cls,
        postconditions: List[PostconditionCheck],
        evidence_pool: List[ObservableEvidence],
        evaluation_time: Optional[float] = None,
    ) -> VerificationResult:
        now = evaluation_time if evaluation_time is not None else time.time()

        satisfied: List[str] = []
        failed: List[str] = []
        unknown: List[str] = []
        reasons: List[str] = []
        used_evidence_ids: List[str] = []

        for check in postconditions:
            # Find relevant matching evidence
            candidates = [
                e for e in evidence_pool
                if e.evidence_type == check.check_type and e.target == check.target
            ]

            if not candidates:
                unknown.append(check.check_id)
                reasons.append(f"Check '{check.check_id}': Missing evidence for target '{check.target}'.")
                continue

            # Sort by timestamp descending (newest first)
            candidates.sort(key=lambda x: x.timestamp, reverse=True)
            newest = candidates[0]

            # Verify integrity
            if not newest.verify_integrity():
                unknown.append(check.check_id)
                reasons.append(f"Check '{check.check_id}': Evidence '{newest.evidence_id}' failed provenance integrity.")
                continue

            # Verify freshness
            age = now - newest.timestamp
            if age > check.max_stale_seconds:
                unknown.append(check.check_id)
                reasons.append(f"Check '{check.check_id}': Evidence '{newest.evidence_id}' is stale (age {age:.1f}s > max {check.max_stale_seconds}s).")
                continue

            # Check for contradictory evidence in the pool within the same execution epoch
            contradictory = [
                c for c in candidates[1:]
                if (now - c.timestamp) <= check.max_stale_seconds and c.data != newest.data
            ]
            if contradictory and newest.evidence_type != EvidenceType.TEST_EXECUTION:
                # Contradictory evidence creates uncertainty
                unknown.append(check.check_id)
                reasons.append(f"Check '{check.check_id}': Contradictory evidence observed among recent records.")
                continue

            used_evidence_ids.append(newest.evidence_id)

            # Evaluate specific condition criteria
            passed, failure_reason = cls._check_condition(check, newest)
            if passed is True:
                satisfied.append(check.check_id)
            elif passed is False:
                failed.append(check.check_id)
                reasons.append(f"Check '{check.check_id}' FAILED: {failure_reason}")
            else:
                unknown.append(check.check_id)
                reasons.append(f"Check '{check.check_id}' UNKNOWN: {failure_reason}")

        # Derive final verdict
        # Any required failure -> NOT_RESTORED
        # Any required unknown -> UNKNOWN
        # All required satisfied -> RESTORED
        required_failed = [cid for cid in failed if any(c.check_id == cid and c.is_required for c in postconditions)]
        required_unknown = [cid for cid in unknown if any(c.check_id == cid and c.is_required for c in postconditions)]

        if required_failed:
            verdict = VerifierVerdict.NOT_RESTORED
        elif required_unknown:
            verdict = VerifierVerdict.UNKNOWN
        else:
            verdict = VerifierVerdict.RESTORED

        return VerificationResult(
            verdict=verdict,
            evaluated_at=now,
            satisfied_checks=satisfied,
            failed_checks=failed,
            unknown_checks=unknown,
            reasons=reasons,
            evidence_ids_used=used_evidence_ids,
        )

    @staticmethod
    def _check_condition(check: PostconditionCheck, evidence: ObservableEvidence) -> tuple[Optional[bool], str]:
        expected = check.expected_conditions
        actual = evidence.data

        if check.check_type == EvidenceType.TEST_EXECUTION:
            # Expected exit code, passed_count, no failures
            exp_exit = expected.get("exit_code", 0)
            act_exit = actual.get("exit_code")
            act_failed = actual.get("failed_count", 0)
            act_passed = actual.get("passed_count", 0)

            if act_exit != exp_exit or act_failed > 0:
                return False, f"Test failed with exit code {act_exit}, {act_failed} failures."

            if expected.get("min_passed_count") and act_passed < expected["min_passed_count"]:
                return False, f"Passed count {act_passed} below required {expected['min_passed_count']}."

            # Structural Anti-tampering: check if test was trivialized or tampered via AST
            test_content = actual.get("test_source_code", "")
            if test_content:
                from backend.app.recovery_pilot.ast_tampering import ASTTestTamperingDetector
                is_tampered, reasons = ASTTestTamperingDetector.analyze_source(test_content)
                if is_tampered:
                    return False, f"Test suite manipulated or trivialized: {'; '.join(reasons)}"

            return True, "Tests passed cleanly."

        elif check.check_type == EvidenceType.FILE_CONTENT:
            content = actual.get("content", "")

            # Substrings that must be present
            for req_substr in expected.get("contains", []):
                if req_substr not in content:
                    return False, f"Missing required string '{req_substr}'."

            # Substrings that must NOT be present
            for forbidden in expected.get("does_not_contain", []):
                if forbidden in content:
                    return False, f"Found forbidden substring '{forbidden}'."

            # Regex patterns
            for pat in expected.get("regex_patterns", []):
                if not re.search(pat, content):
                    return False, f"Content does not match required regex '{pat}'."

            return True, "File content verified."

        elif check.check_type == EvidenceType.ENDPOINT_RESPONSE:
            exp_status = expected.get("status_code", 200)
            act_status = actual.get("status_code")
            if act_status != exp_status:
                return False, f"Status code {act_status} != expected {exp_status}."

            for k, v in expected.get("json_contains", {}).items():
                if actual.get("json_data", {}).get(k) != v:
                    return False, f"JSON field '{k}' expected {v}, got {actual.get('json_data', {}).get(k)}."

            return True, "Endpoint response verified."

        elif check.check_type == EvidenceType.SIDE_EFFECT:
            # Expectation on side effects (e.g. no leftover files, no unauthorized changes)
            disallowed = expected.get("disallowed_files", [])
            observed_files = actual.get("modified_files", []) + actual.get("created_files", [])
            for df in disallowed:
                if df in observed_files:
                    return False, f"Disallowed file side effect observed: {df}"
            return True, "Side-effect postconditions verified."

        return None, "Unrecognized check type condition."
