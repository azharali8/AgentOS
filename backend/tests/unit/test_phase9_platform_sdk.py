"""
AgentOS Phase 9 — Production Platform, SDK & API Unit Tests.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.auth.service import AuthService
from backend.app.config.settings import settings
from agentos.client import AgentOS
from agentos.exceptions import (
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    ValidationError,
)

client = TestClient(app)


# ── 1. API v1 Health, Readiness & Version Contracts ──────────────────────────

def test_api_v1_health():
    resp = client.get("/api/v1/system/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "HEALTHY"
    assert "version" in data


def test_api_v1_readiness():
    resp = client.get("/api/v1/system/readiness")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ready"] is True
    assert data["database"] == "connected"
    assert data["security_manager"] == "active"


def test_api_v1_version():
    resp = client.get("/api/v1/system/version")
    assert resp.status_code == 200
    assert resp.json()["api_version"] == "v1"


# ── 2. Unified Tasks API v1 ──────────────────────────────────────────────────

def test_api_v1_task_lifecycle():
    # 1. Create Task
    create_resp = client.post(
        "/api/v1/tasks",
        json={
            "task": "Perform repository inspection",
            "priority": 3,
            "metadata": {"source": "unit_test"},
        }
    )
    assert create_resp.status_code == 201
    task_data = create_resp.json()
    task_id = task_data["task_id"]
    assert task_data["instruction"] == "Perform repository inspection"
    assert task_data["status"] == "PENDING"

    # 2. Get Task
    get_resp = client.get(f"/api/v1/tasks/{task_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["task_id"] == task_id

    # 3. Get Task Status
    status_resp = client.get(f"/api/v1/tasks/{task_id}/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["is_active"] is True

    # 4. Get Task Result
    result_resp = client.get(f"/api/v1/tasks/{task_id}/result")
    assert result_resp.status_code == 200
    assert "status" in result_resp.json()

    # 5. Get Task Events
    events_resp = client.get(f"/api/v1/tasks/{task_id}/events")
    assert events_resp.status_code == 200
    events = events_resp.json()
    assert len(events) >= 1
    assert events[0]["event_type"] == "TASK_CREATED"

    # 6. Cancel Task
    cancel_resp = client.post(f"/api/v1/tasks/{task_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"


def test_api_v1_task_not_found():
    resp = client.get("/api/v1/tasks/non-existent-task-999")
    assert resp.status_code == 404


def test_api_v1_task_validation_error():
    resp = client.post("/api/v1/tasks", json={"task": "x"})  # min_length is 3
    assert resp.status_code == 422


# ── 3. Specialized Agents API v1 ─────────────────────────────────────────────

def test_api_v1_agents_list():
    resp = client.get("/api/v1/agents")
    assert resp.status_code == 200
    agents = resp.json()
    names = [a["name"] for a in agents]
    assert "data_engineer" in names
    assert "devops" in names
    assert "coding" in names
    assert "cybersecurity" in names


def test_api_v1_agent_details():
    resp = client.get("/api/v1/agents/devops")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "devops"
    assert "ci_cd" in [str(c) for c in data["capabilities"]]


def test_api_v1_agent_capabilities():
    resp = client.get("/api/v1/agents/data_engineer/capabilities")
    assert resp.status_code == 200
    assert "data_profiling" in resp.json()


def test_api_v1_agent_status():
    resp = client.get("/api/v1/agents/coding/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "available"


def test_api_v1_agent_metrics():
    resp = client.get("/api/v1/agents/debugger/metrics")
    assert resp.status_code == 200
    assert "agent_type" in resp.json()


def test_api_v1_agent_invoke_public():
    resp = client.post(
        "/api/v1/agents/devops/invoke",
        json={"instruction": "Generate Dockerfile", "task_id": "test-devops-task"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["agent"] == "devops"


def test_api_v1_cybersecurity_admin_rbac(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    AuthService.reset()

    # 1. Unauthenticated
    resp = client.post(
        "/api/v1/agents/cybersecurity/invoke",
        json={"instruction": "Deep security audit"},
    )
    assert resp.status_code == 401

    # 2. Developer/User role (Forbidden)
    resp = client.post(
        "/api/v1/agents/cybersecurity/invoke",
        json={"instruction": "Deep security audit"},
        headers={"X-API-Key": "test-dev-key"},
    )
    assert resp.status_code == 403

    # 3. Admin role (Allowed)
    resp = client.post(
        "/api/v1/agents/cybersecurity/invoke",
        json={"instruction": "Deep security audit"},
        headers={"X-API-Key": "test-admin-key"},
    )
    assert resp.status_code == 200
    assert resp.json()["agent"] == "cybersecurity"


# ── 4. Official Python SDK Tests ─────────────────────────────────────────────

def test_sdk_task_lifecycle():
    with AgentOS(app=app) as sdk:
        # Create
        task = sdk.tasks.create(task="SDK unit test lifecycle task", priority=1)
        assert task.task_id is not None
        assert task.instruction == "SDK unit test lifecycle task"

        # Get
        fetched = sdk.tasks.get(task.task_id)
        assert fetched.task_id == task.task_id

        # Status
        status = sdk.tasks.status(task.task_id)
        assert status.task_id == task.task_id
        assert status.is_active is True

        # Events
        events = sdk.tasks.events(task.task_id)
        assert len(events) >= 1

        # Cancel
        res = sdk.tasks.cancel(task.task_id)
        assert res["status"] == "CANCELLED"


def test_sdk_agents_client():
    with AgentOS(app=app) as sdk:
        # List
        agents = sdk.agents.list()
        assert len(agents) >= 8
        agent_names = [a.name for a in agents]
        assert "data_engineer" in agent_names

        # Get
        de = sdk.agents.get("data_engineer")
        assert de.name == "data_engineer"

        # Capabilities
        caps = sdk.agents.capabilities("data_engineer")
        assert "data_cleaning" in caps

        # Invoke
        res = sdk.agents.invoke("data_engineer", instruction="Analyze dataset")
        assert res.status == "completed"
        assert res.agent == "data_engineer"


def test_sdk_system_client():
    with AgentOS(app=app) as sdk:
        health = sdk.system.health()
        assert health.status == "HEALTHY"

        readiness = sdk.system.readiness()
        assert readiness.ready is True

        version = sdk.system.version()
        assert version["api_version"] == "v1"

        metrics = sdk.system.metrics()
        assert "system_metrics" in metrics


def test_sdk_typed_exceptions():
    with AgentOS(app=app) as sdk:
        # Not found error
        with pytest.raises(NotFoundError):
            sdk.tasks.get("invalid-id-xyz")

        # Validation error
        with pytest.raises(ValidationError):
            sdk.tasks.create("x")  # min length 3


def test_websocket_event_streaming():
    with client.websocket_connect("/api/v1/events/stream/test-stream-task-id") as ws:
        # First message is connection confirmation
        data = ws.receive_json()
        assert data["event_type"] == "STREAM_CONNECTED"
        assert data["task_id"] == "test-stream-task-id"


def test_api_v1_task_list_pagination():
    resp = client.get("/api/v1/tasks?limit=5&offset=0")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_api_v1_evaluations_benchmarks_rbac(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    AuthService.reset()

    # Unauthorized for regular viewer
    resp_viewer = client.get("/api/v1/evaluations/benchmarks", headers={"X-API-Key": "test-viewer-key"})
    assert resp_viewer.status_code == 403

    # Authorized for developer/admin
    resp_dev = client.get("/api/v1/evaluations/benchmarks", headers={"X-API-Key": "test-dev-key"})
    assert resp_dev.status_code == 200
    assert "phase6_benchmark" in resp_dev.json()


def test_api_v1_system_metrics():
    resp = client.get("/api/v1/system/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "system_metrics" in data
    assert "llm_usage" in data


def test_sdk_context_manager():
    with AgentOS(app=app) as sdk:
        assert sdk.base_url == "http://localhost:8000"

