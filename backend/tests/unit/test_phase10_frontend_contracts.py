"""
AgentOS Phase 10 — Frontend Contract & Integration Test Suite.

Validates that all frontend-facing API v1 endpoints, schemas, WebSocket streaming,
RBAC visibility rules, and Supervisor status contracts are fully satisfied.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.auth.service import AuthService
from backend.app.config.settings import settings

client = TestClient(app)


# ── 1. Frontend Dashboard Telemetry Contract ─────────────────────────────────

def test_frontend_dashboard_overview():
    resp = client.get("/api/v1/system/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "HEALTHY"

    readiness = client.get("/api/v1/system/readiness")
    assert readiness.status_code == 200
    assert readiness.json()["ready"] is True


# ── 2. Frontend Task Center Contract ─────────────────────────────────────────

def test_frontend_task_center_flow():
    # 1. Create task from UI
    create_res = client.post(
        "/api/v1/tasks",
        json={"task": "Frontend Task Center test submission", "priority": 2},
    )
    assert create_res.status_code == 201
    task = create_res.json()
    task_id = task["task_id"]

    # 2. List tasks for UI table
    list_res = client.get("/api/v1/tasks?limit=10&offset=0")
    assert list_res.status_code == 200
    task_ids = [t["task_id"] for t in list_res.json()]
    assert task_id in task_ids

    # 3. Retrieve task execution details for timeline
    detail_res = client.get(f"/api/v1/tasks/{task_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["instruction"] == "Frontend Task Center test submission"


# ── 3. Frontend Real-Time Streaming Contract ─────────────────────────────────

def test_frontend_websocket_streaming_contract():
    with client.websocket_connect("/api/v1/events/stream/test-frontend-stream-id") as ws:
        data = ws.receive_json()
        assert data["event_type"] == "STREAM_CONNECTED"
        assert data["task_id"] == "test-frontend-stream-id"


# ── 4. Frontend Agent Center & Direct Invocation Contract ────────────────────

def test_frontend_agent_center_catalog():
    resp = client.get("/api/v1/agents")
    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) >= 8

    # Verify Data Engineer card metadata
    de = next((a for a in agents if a["name"] == "data_engineer"), None)
    assert de is not None
    assert "data_cleaning" in [str(c) for c in de["capabilities"]]


def test_frontend_agent_invocation():
    resp = client.post(
        "/api/v1/agents/data_engineer/invoke",
        json={"instruction": "Profile sample dataset from frontend UI"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["agent"] == "data_engineer"


# ── 5. Frontend RBAC & Security Enforcement Contract ─────────────────────────

def test_frontend_security_rbac_visibility(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    AuthService.reset()

    # Viewer cannot access evaluations
    viewer_eval = client.get("/api/v1/evaluations/benchmarks", headers={"X-API-Key": "test-viewer-key"})
    assert viewer_eval.status_code == 403

    # Developer can access evaluations
    dev_eval = client.get("/api/v1/evaluations/benchmarks", headers={"X-API-Key": "test-dev-key"})
    assert dev_eval.status_code == 200

    # Developer cannot invoke cybersecurity
    dev_cyber = client.post(
        "/api/v1/agents/cybersecurity/invoke",
        json={"instruction": "Audit"},
        headers={"X-API-Key": "test-dev-key"},
    )
    assert dev_cyber.status_code == 403

    # Admin can invoke cybersecurity
    admin_cyber = client.post(
        "/api/v1/agents/cybersecurity/invoke",
        json={"instruction": "Audit"},
        headers={"X-API-Key": "test-admin-key"},
    )
    assert admin_cyber.status_code == 200


# ── 6. Frontend CORS Preflight Contract ──────────────────────────────────────

def test_frontend_cors_preflight():
    response = client.options(
        "/api/v1/agents",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


# ── 7. Workspace Explorer Contract ───────────────────────────────────────────

def test_frontend_workspace_explorer_contract():
    # 1. Directory Tree Listing
    tree_res = client.get("/api/v1/workspace/tree")
    assert tree_res.status_code == 200
    data = tree_res.json()
    assert "items" in data
    assert "current_path" in data

    # 2. Sensitive Path Denial
    sensitive_res = client.get("/api/v1/workspace/file?path=.env")
    assert sensitive_res.status_code == 403


# ── 8. Approvals & System Models Contract ────────────────────────────────────

def test_frontend_approvals_and_models_contract():
    # 1. Models Probing
    models_res = client.get("/api/v1/system/models")
    assert models_res.status_code == 200
    m_data = models_res.json()
    assert "models" in m_data
    assert len(m_data["models"]) >= 1

    # 2. Approvals Listing
    appr_res = client.get("/api/v1/approvals")
    assert appr_res.status_code == 200
    assert isinstance(appr_res.json(), list)


# ── 9. Authentication & User Profile Contract ────────────────────────────────

def test_frontend_auth_login_me_flow(monkeypatch):
    # Enable real auth path (not the dev bypass)
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    AuthService.reset()

    # 1. Invalid Credentials
    bad_login = client.post(
        "/api/v1/auth/login",
        json={"email": "azhar@agentos.local", "password": "wrongpassword"},
    )
    assert bad_login.status_code == 401

    # 2. Valid Login
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "azhar@agentos.local", "password": "agentos123"},
    )
    assert login_res.status_code == 200
    auth_data = login_res.json()
    assert "token" in auth_data
    assert auth_data["username"] == "Azhar Ali"
    assert auth_data["role"] == "user"

    token = auth_data["token"]

    # 3. Authenticated Profile /me
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    profile = me_res.json()
    assert profile["username"] == "Azhar Ali"
    assert profile["role"] == "user"
    assert profile["is_authenticated"] is True

    # 4. Logout
    logout_res = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_res.status_code == 200

