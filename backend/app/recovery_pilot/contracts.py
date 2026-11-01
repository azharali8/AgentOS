"""
Layer B: Typed Evidence & Postcondition Contracts for Recovery Verification.

Defines:
- VerifierVerdict: RESTORED, NOT_RESTORED, UNKNOWN
- EvidenceType: Supported observable evidence categories
- ObservableEvidence: Typed, timestamped evidence items with integrity verification
- PostconditionCheck: Pre-registered observable expectation
- RecoveryExperimentRecord: Durable multi-perspective experiment result
"""

from __future__ import annotations

import time
import hashlib
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class VerifierVerdict(str, Enum):
    RESTORED = "RESTORED"
    NOT_RESTORED = "NOT_RESTORED"
    UNKNOWN = "UNKNOWN"


class EvidenceType(str, Enum):
    TEST_EXECUTION = "test_execution"
    FILE_CONTENT = "file_content"
    FILE_HASH = "file_hash"
    ENDPOINT_RESPONSE = "endpoint_response"
    PROCESS_OUTPUT = "process_output"
    SIDE_EFFECT = "side_effect"


class ObservableEvidence(BaseModel):
    evidence_id: str
    evidence_type: EvidenceType
    source: str
    target: str
    timestamp: float = Field(default_factory=time.time)
    task_id: Optional[str] = None
    execution_id: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    provenance_hash: Optional[str] = None

    def compute_hash(self) -> str:
        raw = f"{self.evidence_id}:{self.evidence_type.value}:{self.source}:{self.target}:{self.timestamp}:{sorted(self.data.items())}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def verify_integrity(self) -> bool:
        if not self.provenance_hash:
            return True
        return self.compute_hash() == self.provenance_hash


class PostconditionCheck(BaseModel):
    check_id: str
    description: str
    check_type: EvidenceType
    target: str
    expected_conditions: Dict[str, Any]
    max_stale_seconds: float = 300.0  # Freshness boundary
    is_required: bool = True


class VerificationResult(BaseModel):
    verdict: VerifierVerdict
    evaluated_at: float = Field(default_factory=time.time)
    satisfied_checks: List[str] = Field(default_factory=list)
    failed_checks: List[str] = Field(default_factory=list)
    unknown_checks: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    evidence_ids_used: List[str] = Field(default_factory=list)


class RecoveryExperimentRecord(BaseModel):
    experiment_id: str
    task_id: str
    project_id: str
    scenario_reference: str  # Neutral identifier: e.g. "scen-01"
    started_at: float
    completed_at: float
    initial_state_hash: str
    final_state_hash: str

    # Perspective 1: Agent Self-Report
    agent_claim: Dict[str, Any] = Field(default_factory=dict)

    # Perspective 2: Independent LLM Judge
    judge_assessment: Dict[str, Any] = Field(default_factory=dict)

    # Perspective 3: Authoritative Runtime Verifier
    verifier_verdict: VerifierVerdict
    verification_result: Optional[VerificationResult] = None

    # Side-effect & Intervention tracking
    side_effects: List[Dict[str, Any]] = Field(default_factory=list)
    human_intervention_required: bool = False
    audit_references: Dict[str, Any] = Field(default_factory=dict)
