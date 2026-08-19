"""
Unit and integration tests for Phase 6 Production Platform, Observability & Evaluation.
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.auth.service import AuthService, AuthenticatedUser, UserRole
from backend.app.config.settings import settings
from backend.app.evaluation.benchmark import BenchmarkSuite
from backend.app.evaluation.metrics import MetricsCollector
from backend.app.main import app
from backend.app.observability.context import (
    clear_correlation_context,
    get_correlation_context,
    set_correlation_context,
)
from backend.app.observability.redaction import redact_secrets
from backend.app.security.rate_limit import RateLimiter, RequestGuard
from backend.app.services.backup_service import BackupService
from backend.app.services.llm_usage import LLMUsageService

client = TestClient(app)


# ── 1. Secret Redaction Tests ─────────────────────────────────────────

def test_centralized_secret_redaction():
    text = "User sk-1234567890abcdef1234567890abcdef requested access with api_key='secret123456'"
    redacted = redact_secrets(text)
    assert "[REDACTED_SECRET]" in redacted
    assert "sk-1234567890abcdef" not in redacted
    assert "secret123456" not in redacted

    data = {
        "password": "super-secret-password",
        "nested": {"token": "ghp_123456789012345678901234567890123456"},
    }
    redacted_data = redact_secrets(data)
    assert redacted_data["password"] == "[REDACTED_SECRET]"
    assert redacted_data["nested"]["token"] == "[REDACTED_SECRET]"


# ── 2. Correlation Context Tests ──────────────────────────────────────

def test_correlation_context():
    clear_correlation_context()
    set_correlation_context(request_id="req-test-1", task_id="t-test-1", agent_id="supervisor")
    ctx = get_correlation_context()
    assert ctx["request_id"] == "req-test-1"
    assert ctx["task_id"] == "t-test-1"
    assert ctx["agent_id"] == "supervisor"
    assert ctx["correlation_id"] is not None

    clear_correlation_context()
    assert get_correlation_context()["request_id"] is None


# ── 3. Metrics Collector Tests ────────────────────────────────────────

def test_system_metrics_collector():
    MetricsCollector.reset()
    MetricsCollector.record_task_started()
    MetricsCollector.record_task_completed()
    MetricsCollector.record_tool_call(success=True)
    MetricsCollector.record_tool_call(success=False)
    MetricsCollector.record_approval("APPROVED")

    snapshot = MetricsCollector.get_metrics_snapshot()
    assert snapshot["tasks"]["started"] == 1
    assert snapshot["tasks"]["completed"] == 1
    assert snapshot["tools"]["total_calls"] == 2
    assert snapshot["tools"]["failed_calls"] == 1
    assert snapshot["approvals"]["approved"] == 1


# ── 4. LLM Usage & Cost Tracker Tests ─────────────────────────────────

def test_llm_usage_and_cost_tracking():
    LLMUsageService.reset()
    rec = LLMUsageService.record_usage(
        task_id="task-u1",
        agent_id="research",
        provider="ollama",
        model="llama3",
        input_tokens=500,
        output_tokens=500,
        latency_ms=120.0,
    )
    assert rec.total_tokens == 1000
    assert rec.estimated_cost > 0.0

    task_usage = LLMUsageService.get_task_usage("task-u1")
    assert task_usage["total_tokens"] == 1000
    assert task_usage["invocations_count"] == 1


# ── 5. Rate Limiter Tests ─────────────────────────────────────────────

def test_rate_limiter_enforcement():
    RateLimiter.reset()
    key = "ip-127.0.0.1"

    # Within limit of 3
    RateLimiter.check_rate_limit(key, limit=3, window_seconds=60)
    RateLimiter.check_rate_limit(key, limit=3, window_seconds=60)
    RateLimiter.check_rate_limit(key, limit=3, window_seconds=60)

    # Exceed limit
    with pytest.raises(Exception) as exc:
        RateLimiter.check_rate_limit(key, limit=3, window_seconds=60)
    assert exc.value.status_code == 429


# ── 6. Authentication & RBAC Tests ───────────────────────────────────

def test_api_key_authentication(monkeypatch):
    monkeypatch.setattr("backend.app.config.settings.settings.AUTH_ENABLED", True)
    AuthService.reset()

    # Valid key
    user = AuthService.authenticate_key("test-admin-key")
    assert user is not None
    assert user.role == UserRole.ADMIN

    # Invalid key
    assert AuthService.authenticate_key("invalid-key") is None


# ── 7. Evaluation Benchmark Suite Tests ───────────────────────────────

def test_benchmark_suite_execution():
    results = BenchmarkSuite.run_all()
    assert results["total_cases"] == 12
    assert results["passed_count"] >= 10
    assert results["success_rate_pct"] >= 80.0


# ── 8. Backup and Recovery Tests ──────────────────────────────────────

def test_backup_and_recovery_lifecycle(tmp_path, monkeypatch):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("backend.app.services.backup_service.BackupService.get_backup_dir", lambda: backup_dir)

    res = BackupService.create_backup()
    if res.get("success"):
        assert Path(res["backup_path"]).exists()
        backups = BackupService.list_backups()
        assert len(backups) >= 1


# ── 9. Production API Endpoints Tests ─────────────────────────────────

def test_production_dashboard_and_health_endpoints():
    # 1. Health check
    resp = client.get("/health")
    assert resp.status_code == 200

    # 2. Ready check
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"

    # 3. System status
    resp = client.get("/api/system/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "HEALTHY"

    # 4. Overview dashboard
    resp = client.get("/api/dashboard/overview")
    assert resp.status_code == 200

    # 5. Metrics dashboard
    resp = client.get("/api/dashboard/metrics")
    assert resp.status_code == 200
