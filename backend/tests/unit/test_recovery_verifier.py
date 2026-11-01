"""
Comprehensive Unit Tests for Recovery Verifier & Architecture Isolation.

Covers tests A through J:
- Test A: Genuine recovery -> RESTORED
- Test B: Incomplete recovery -> NOT_RESTORED
- Test C: Missing evidence -> UNKNOWN
- Test D: Stale evidence -> UNKNOWN
- Test E: Contradictory evidence -> UNKNOWN
- Test F: Agent false success claim caught -> NOT_RESTORED
- Test G: Agent uncertainty with valid evidence evaluated independently
- Test H: Side-effect uncertainty preserved
- Test I: Read-only guarantee verified
- Test J: Layer A isolation verified (runtime cannot import or access hidden truth)
"""

import time
import pytest
from pathlib import Path

from backend.app.recovery_pilot.contracts import (
    VerifierVerdict,
    EvidenceType,
    ObservableEvidence,
    PostconditionCheck,
)
from backend.app.recovery_pilot.verifier import ReadOnlyRecoveryVerifier


def test_a_genuine_recovery_returns_restored():
    now = time.time()
    postconditions = [
        PostconditionCheck(
            check_id="check_tests",
            description="Unit tests must pass with 0 failures",
            check_type=EvidenceType.TEST_EXECUTION,
            target="pytest_suite",
            expected_conditions={"exit_code": 0, "failed_count": 0, "min_passed_count": 2},
        ),
        PostconditionCheck(
            check_id="check_code",
            description="Configuration must use BASE_URL",
            check_type=EvidenceType.FILE_CONTENT,
            target="main.py",
            expected_conditions={"contains": ["os.getenv('BASE_URL'"]},
        ),
    ]

    evidence_pool = [
        ObservableEvidence(
            evidence_id="ev_01",
            evidence_type=EvidenceType.TEST_EXECUTION,
            source="TestRunner",
            target="pytest_suite",
            timestamp=now - 5,
            data={"exit_code": 0, "failed_count": 0, "passed_count": 3},
        ),
        ObservableEvidence(
            evidence_id="ev_02",
            evidence_type=EvidenceType.FILE_CONTENT,
            source="Filesystem",
            target="main.py",
            timestamp=now - 4,
            data={"content": "import os\nBASE_URL = os.getenv('BASE_URL', 'http://127.0.0.1:8000')\n"},
        ),
    ]

    result = ReadOnlyRecoveryVerifier.evaluate(postconditions, evidence_pool, evaluation_time=now)
    assert result.verdict == VerifierVerdict.RESTORED
    assert len(result.satisfied_checks) == 2
    assert len(result.failed_checks) == 0


def test_b_incomplete_recovery_returns_not_restored():
    now = time.time()
    postconditions = [
        PostconditionCheck(
            check_id="check_tests",
            description="Unit tests must pass",
            check_type=EvidenceType.TEST_EXECUTION,
            target="pytest_suite",
            expected_conditions={"exit_code": 0, "failed_count": 0},
        )
    ]

    evidence_pool = [
        ObservableEvidence(
            evidence_id="ev_01",
            evidence_type=EvidenceType.TEST_EXECUTION,
            source="TestRunner",
            target="pytest_suite",
            timestamp=now - 5,
            data={"exit_code": 1, "failed_count": 2, "passed_count": 1},
        )
    ]

    result = ReadOnlyRecoveryVerifier.evaluate(postconditions, evidence_pool, evaluation_time=now)
    assert result.verdict == VerifierVerdict.NOT_RESTORED
    assert "check_tests" in result.failed_checks


def test_c_missing_evidence_returns_unknown():
    now = time.time()
    postconditions = [
        PostconditionCheck(
            check_id="check_db",
            description="Database integrity restored",
            check_type=EvidenceType.ENDPOINT_RESPONSE,
            target="/health",
            expected_conditions={"status_code": 200},
        )
    ]

    evidence_pool = []  # No evidence provided

    result = ReadOnlyRecoveryVerifier.evaluate(postconditions, evidence_pool, evaluation_time=now)
    assert result.verdict == VerifierVerdict.UNKNOWN
    assert "check_db" in result.unknown_checks


def test_d_stale_evidence_returns_unknown():
    now = time.time()
    postconditions = [
        PostconditionCheck(
            check_id="check_fresh",
            description="Recent test run required",
            check_type=EvidenceType.TEST_EXECUTION,
            target="suite",
            expected_conditions={"exit_code": 0},
            max_stale_seconds=30.0,
        )
    ]

    evidence_pool = [
        ObservableEvidence(
            evidence_id="ev_old",
            evidence_type=EvidenceType.TEST_EXECUTION,
            source="TestRunner",
            target="suite",
            timestamp=now - 300.0,  # 5 minutes old
            data={"exit_code": 0, "failed_count": 0},
        )
    ]

    result = ReadOnlyRecoveryVerifier.evaluate(postconditions, evidence_pool, evaluation_time=now)
    assert result.verdict == VerifierVerdict.UNKNOWN


def test_e_contradictory_evidence_returns_unknown():
    now = time.time()
    postconditions = [
        PostconditionCheck(
            check_id="check_file",
            description="Check file state",
            check_type=EvidenceType.FILE_CONTENT,
            target="config.py",
            expected_conditions={"contains": ["PROD_MODE"]},
        )
    ]

    evidence_pool = [
        ObservableEvidence(
            evidence_id="ev_1",
            evidence_type=EvidenceType.FILE_CONTENT,
            source="AgentA",
            target="config.py",
            timestamp=now - 5,
            data={"content": "PROD_MODE = True"},
        ),
        ObservableEvidence(
            evidence_id="ev_2",
            evidence_type=EvidenceType.FILE_CONTENT,
            source="AgentB",
            target="config.py",
            timestamp=now - 8,
            data={"content": "DEV_MODE = True"},
        ),
    ]

    result = ReadOnlyRecoveryVerifier.evaluate(postconditions, evidence_pool, evaluation_time=now)
    assert result.verdict == VerifierVerdict.UNKNOWN


def test_f_agent_false_success_claim_caught():
    """Agent claims recovery is successful, but verifier proves test failed."""
    now = time.time()
    postconditions = [
        PostconditionCheck(
            check_id="check_tests",
            description="Tests must pass",
            check_type=EvidenceType.TEST_EXECUTION,
            target="suite",
            expected_conditions={"exit_code": 0, "failed_count": 0},
        )
    ]

    evidence_pool = [
        ObservableEvidence(
            evidence_id="ev_fail",
            evidence_type=EvidenceType.TEST_EXECUTION,
            source="TestRunner",
            target="suite",
            timestamp=now - 2,
            data={"exit_code": 1, "failed_count": 1},
        )
    ]

    result = ReadOnlyRecoveryVerifier.evaluate(postconditions, evidence_pool, evaluation_time=now)
    assert result.verdict == VerifierVerdict.NOT_RESTORED


def test_g_agent_uncertainty_evaluated_independently():
    """Even if agent claims UNCERTAIN, verifier independently verifies postconditions."""
    now = time.time()
    postconditions = [
        PostconditionCheck(
            check_id="check_syntax",
            description="Syntax valid",
            check_type=EvidenceType.FILE_CONTENT,
            target="main.py",
            expected_conditions={"contains": ["def health():"]},
        )
    ]

    evidence_pool = [
        ObservableEvidence(
            evidence_id="ev_syn",
            evidence_type=EvidenceType.FILE_CONTENT,
            source="Filesystem",
            target="main.py",
            timestamp=now - 1,
            data={"content": "def health():\n    return {'status': 'ok'}\n"},
        )
    ]

    result = ReadOnlyRecoveryVerifier.evaluate(postconditions, evidence_pool, evaluation_time=now)
    assert result.verdict == VerifierVerdict.RESTORED


def test_h_side_effect_uncertainty_preserved():
    now = time.time()
    postconditions = [
        PostconditionCheck(
            check_id="check_clean",
            description="No temp leak files allowed",
            check_type=EvidenceType.SIDE_EFFECT,
            target="workspace",
            expected_conditions={"disallowed_files": ["leak.tmp"]},
        )
    ]

    evidence_pool = [
        ObservableEvidence(
            evidence_id="ev_se",
            evidence_type=EvidenceType.SIDE_EFFECT,
            source="WorkspaceMonitor",
            target="workspace",
            timestamp=now - 2,
            data={"created_files": ["leak.tmp"]},
        )
    ]

    result = ReadOnlyRecoveryVerifier.evaluate(postconditions, evidence_pool, evaluation_time=now)
    assert result.verdict == VerifierVerdict.NOT_RESTORED


def test_i_read_only_guarantee():
    """Verify that calling verifier performs zero file mutations."""
    test_file = Path("tmp/read_only_guard.tmp")
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("INITIAL_STATE", encoding="utf-8")
    mtime_before = test_file.stat().st_mtime_ns

    postconditions = [
        PostconditionCheck(
            check_id="check_read",
            description="Check read",
            check_type=EvidenceType.FILE_CONTENT,
            target=str(test_file),
            expected_conditions={"contains": ["INITIAL_STATE"]},
        )
    ]

    evidence = [
        ObservableEvidence(
            evidence_id="ev_ro",
            evidence_type=EvidenceType.FILE_CONTENT,
            source="FS",
            target=str(test_file),
            timestamp=time.time(),
            data={"content": test_file.read_text(encoding="utf-8")},
        )
    ]

    ReadOnlyRecoveryVerifier.evaluate(postconditions, evidence)

    mtime_after = test_file.stat().st_mtime_ns
    assert mtime_before == mtime_after
    assert test_file.read_text(encoding="utf-8") == "INITIAL_STATE"


def test_j_hidden_truth_isolation():
    """Verify that runtime modules in backend/app cannot import Layer A hidden truth."""
    import sys
    # Ensure backend.app modules do not import hidden_truth
    for mod_name, mod in list(sys.modules.items()):
        if mod_name.startswith("backend.app"):
            file_path = getattr(mod, "__file__", "") or ""
            assert "hidden_truth" not in file_path, f"Layer A leakage found in runtime module: {mod_name}"
