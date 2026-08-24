"""
AgentOS Phase 9 — Production Platform & SDK Benchmark Suite.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List
from pydantic import BaseModel
from fastapi.testclient import TestClient

import sys
from pathlib import Path

# Ensure sdk is resolvable when run standalone
_sdk_path = str(Path(__file__).resolve().parent.parent.parent.parent / "sdk")
if _sdk_path not in sys.path:
    sys.path.insert(0, _sdk_path)

from backend.app.main import app
from backend.app.auth.service import AuthService
from agentos.client import AgentOS
from agentos.exceptions import AuthenticationError, AuthorizationError, NotFoundError

client = TestClient(app)


class BenchmarkResult(BaseModel):
    case_id: str
    name: str
    passed: bool
    duration_seconds: float = 0.0
    error: str | None = None


class ProductionPlatformBenchmarkSuite:
    """Deterministic Phase 9 benchmark suite validating platform contracts."""

    @classmethod
    def run_all(cls) -> Dict[str, Any]:
        cases = [
            cls._case_health_probe,
            cls._case_readiness_probe,
            cls._case_version_contract,
            cls._case_task_creation_lifecycle,
            cls._case_task_status_endpoint,
            cls._case_task_events_endpoint,
            cls._case_task_cancellation,
            cls._case_agent_listing_v1,
            cls._case_agent_capabilities_v1,
            cls._case_agent_metrics_v1,
            cls._case_sdk_task_lifecycle,
            cls._case_sdk_agent_invocation,
            cls._case_sdk_typed_error_handling,
            cls._case_cybersecurity_admin_enforcement_v1,
            cls._case_system_metrics_v1,
        ]

        results: List[BenchmarkResult] = []
        for case_fn in cases:
            start = time.perf_counter()
            try:
                res = case_fn()
                res.duration_seconds = round(time.perf_counter() - start, 4)
                results.append(res)
            except Exception as exc:
                results.append(
                    BenchmarkResult(
                        case_id=case_fn.__name__,
                        name=case_fn.__name__,
                        passed=False,
                        duration_seconds=round(time.perf_counter() - start, 4),
                        error=str(exc),
                    )
                )

        passed_count = sum(1 for r in results if r.passed)
        total = len(results)
        return {
            "total_cases": total,
            "passed_count": passed_count,
            "failed_count": total - passed_count,
            "success_rate_pct": round((passed_count / max(1, total)) * 100, 1),
            "results": [r.model_dump() for r in results],
        }

    @staticmethod
    def _case_health_probe() -> BenchmarkResult:
        resp = client.get("/api/v1/system/health")
        passed = resp.status_code == 200 and resp.json().get("status") == "HEALTHY"
        return BenchmarkResult(case_id="P9-01", name="System Health Probe", passed=passed)

    @staticmethod
    def _case_readiness_probe() -> BenchmarkResult:
        resp = client.get("/api/v1/system/readiness")
        passed = resp.status_code == 200 and resp.json().get("ready") is True
        return BenchmarkResult(case_id="P9-02", name="System Readiness Probe", passed=passed)

    @staticmethod
    def _case_version_contract() -> BenchmarkResult:
        resp = client.get("/api/v1/system/version")
        passed = resp.status_code == 200 and resp.json().get("api_version") == "v1"
        return BenchmarkResult(case_id="P9-03", name="API Version Contract", passed=passed)

    @staticmethod
    def _case_task_creation_lifecycle() -> BenchmarkResult:
        resp = client.post("/api/v1/tasks", json={"task": "Benchmark task execution lifecycle"})
        passed = resp.status_code == 201 and "task_id" in resp.json() and resp.json().get("status") == "PENDING"
        return BenchmarkResult(case_id="P9-04", name="Task Creation Lifecycle", passed=passed)

    @staticmethod
    def _case_task_status_endpoint() -> BenchmarkResult:
        create_resp = client.post("/api/v1/tasks", json={"task": "Benchmark status inspection"})
        task_id = create_resp.json()["task_id"]
        status_resp = client.get(f"/api/v1/tasks/{task_id}/status")
        passed = status_resp.status_code == 200 and status_resp.json().get("task_id") == task_id
        return BenchmarkResult(case_id="P9-05", name="Task Status Query", passed=passed)

    @staticmethod
    def _case_task_events_endpoint() -> BenchmarkResult:
        create_resp = client.post("/api/v1/tasks", json={"task": "Benchmark events capture"})
        task_id = create_resp.json()["task_id"]
        events_resp = client.get(f"/api/v1/tasks/{task_id}/events")
        passed = events_resp.status_code == 200 and isinstance(events_resp.json(), list) and len(events_resp.json()) >= 1
        return BenchmarkResult(case_id="P9-06", name="Task Events Stream Query", passed=passed)

    @staticmethod
    def _case_task_cancellation() -> BenchmarkResult:
        create_resp = client.post("/api/v1/tasks", json={"task": "Benchmark cancellation"})
        task_id = create_resp.json()["task_id"]
        cancel_resp = client.post(f"/api/v1/tasks/{task_id}/cancel")
        passed = cancel_resp.status_code == 200 and cancel_resp.json().get("status") == "CANCELLED"
        return BenchmarkResult(case_id="P9-07", name="Task Cancellation", passed=passed)

    @staticmethod
    def _case_agent_listing_v1() -> BenchmarkResult:
        resp = client.get("/api/v1/agents")
        passed = resp.status_code == 200 and len(resp.json()) >= 8
        return BenchmarkResult(case_id="P9-08", name="Agent Listing v1", passed=passed)

    @staticmethod
    def _case_agent_capabilities_v1() -> BenchmarkResult:
        resp = client.get("/api/v1/agents/data_engineer/capabilities")
        passed = resp.status_code == 200 and "data_cleaning" in resp.json()
        return BenchmarkResult(case_id="P9-09", name="Agent Capabilities Query", passed=passed)

    @staticmethod
    def _case_agent_metrics_v1() -> BenchmarkResult:
        resp = client.get("/api/v1/agents/coding/metrics")
        passed = resp.status_code == 200 and "agent_type" in resp.json()
        return BenchmarkResult(case_id="P9-10", name="Agent Metrics Query", passed=passed)

    @staticmethod
    def _case_sdk_task_lifecycle() -> BenchmarkResult:
        sdk = AgentOS(app=app)
        task = sdk.tasks.create("SDK benchmark task lifecycle test")
        status = sdk.tasks.status(task.task_id)
        passed = task.task_id is not None and status.task_id == task.task_id
        return BenchmarkResult(case_id="P9-11", name="SDK Task Lifecycle", passed=passed)

    @staticmethod
    def _case_sdk_agent_invocation() -> BenchmarkResult:
        sdk = AgentOS(app=app)
        res = sdk.agents.invoke(
            agent_id="data_engineer",
            instruction="Profile dataset benchmark test",
        )
        passed = res.status == "completed" and res.agent == "data_engineer"
        return BenchmarkResult(case_id="P9-12", name="SDK Agent Invocation", passed=passed)

    @staticmethod
    def _case_sdk_typed_error_handling() -> BenchmarkResult:
        sdk = AgentOS(app=app)
        error_caught = False
        try:
            sdk.tasks.get("non-existent-task-id-12345")
        except NotFoundError:
            error_caught = True
        return BenchmarkResult(case_id="P9-13", name="SDK Typed Exception Handling", passed=error_caught)

    @staticmethod
    def _case_cybersecurity_admin_enforcement_v1() -> BenchmarkResult:
        # Check non-admin block
        headers_user = {"X-API-Key": "test-dev-key"}
        # Ensure auth active
        from backend.app.config.settings import settings
        original_auth = settings.AUTH_ENABLED
        settings.AUTH_ENABLED = True
        AuthService.reset()
        
        try:
            resp_denied = client.post(
                "/api/v1/agents/cybersecurity/invoke",
                json={"instruction": "Audit"},
                headers=headers_user,
            )
            
            headers_admin = {"X-API-Key": "test-admin-key"}
            resp_allowed = client.post(
                "/api/v1/agents/cybersecurity/invoke",
                json={"instruction": "Audit"},
                headers=headers_admin,
            )
            passed = resp_denied.status_code == 403 and resp_allowed.status_code == 200
        finally:
            settings.AUTH_ENABLED = original_auth

        return BenchmarkResult(case_id="P9-14", name="Cybersecurity ADMIN RBAC Enforcement", passed=passed)

    @staticmethod
    def _case_system_metrics_v1() -> BenchmarkResult:
        resp = client.get("/api/v1/system/metrics")
        passed = resp.status_code == 200 and "system_metrics" in resp.json()
        return BenchmarkResult(case_id="P9-15", name="System & LLM Metrics Snapshot", passed=passed)


if __name__ == "__main__":
    import json
    print(json.dumps(ProductionPlatformBenchmarkSuite.run_all(), indent=2))
