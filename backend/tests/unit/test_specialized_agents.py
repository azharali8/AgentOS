"""
Phase 8 — Specialized Agents Platform Benchmarks & Tests
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.agents.domain_experts import CybersecurityAgent, DataEngineerAgent, DevOpsAgent, TestingAgent
from backend.app.agents.registry import AgentRegistry
from backend.app.agents.supervisor import SupervisorAgent
from backend.app.auth.service import AuthService, AuthenticatedUser, UserRole
from backend.app.config.settings import settings
from backend.app.main import app
from backend.app.models.multi_agent import AgentCapability, AgentStatus, AgentType, SubTask

client = TestClient(app)


# ── 1. Specialized Agent Contract & Registry ───────────────────────────────

def test_registry_contains_new_domain_agents():
    assert AgentRegistry.get("testing") is not None
    assert AgentRegistry.get("data_engineer") is not None
    assert AgentRegistry.get("devops") is not None
    assert AgentRegistry.get("cybersecurity") is not None

def test_registry_resolves_capabilities():
    agents = AgentRegistry.resolve_by_capability(AgentCapability.DATA_CLEANING)
    assert len(agents) == 1
    assert agents[0].name == "data_engineer"
    
    ci_agents = AgentRegistry.resolve_by_capability(AgentCapability.CI_CD)
    assert len(ci_agents) == 1
    assert ci_agents[0].name == "devops"
    
    cyber_agents = AgentRegistry.resolve_by_capability(AgentCapability.CYBER_AUDIT)
    assert len(cyber_agents) == 1
    assert cyber_agents[0].name == "cybersecurity"

# ── 2. Supervisor Routing & Execution ──────────────────────────────────────

def test_supervisor_routes_to_testing_agent():
    supervisor = SupervisorAgent()
    st = SubTask(task_id="t1", subtask_id="s1", description="Run tests", assigned_agent=AgentType.TESTING)
    res = supervisor.execute_subtask(st)
    assert res.agent_type == AgentType.TESTING
    assert res.status in (AgentStatus.COMPLETED, AgentStatus.FAILED)

def test_supervisor_routes_to_data_engineer():
    supervisor = SupervisorAgent()
    st = SubTask(task_id="t1", subtask_id="s1", description="Clean data", assigned_agent=AgentType.DATA_ENGINEER)
    res = supervisor.execute_subtask(st)
    assert res.agent_type == AgentType.DATA_ENGINEER
    assert res.status == AgentStatus.COMPLETED

def test_supervisor_routes_to_devops():
    supervisor = SupervisorAgent()
    st = SubTask(task_id="t1", subtask_id="s1", description="Build Dockerfile", assigned_agent=AgentType.DEVOPS)
    res = supervisor.execute_subtask(st)
    assert res.agent_type == AgentType.DEVOPS
    assert res.status == AgentStatus.COMPLETED

def test_supervisor_routes_to_cybersecurity():
    supervisor = SupervisorAgent()
    st = SubTask(task_id="t1", subtask_id="s1", description="Audit security", assigned_agent=AgentType.CYBERSECURITY)
    res = supervisor.execute_subtask(st)
    assert res.agent_type == AgentType.CYBERSECURITY
    assert res.status == AgentStatus.COMPLETED

# ── 3. API Endpoints ───────────────────────────────────────────────────────

def test_api_agents_registry():
    resp = client.get("/api/agents/registry")
    assert resp.status_code == 200
    names = [a["name"] for a in resp.json()]
    assert "data_engineer" in names
    assert "devops" in names
    assert "testing" in names

def test_api_agent_capabilities():
    resp = client.get("/api/agents/data_engineer/capabilities")
    assert resp.status_code == 200
    caps = resp.json()
    assert "data_cleaning" in caps

def test_api_agent_metrics():
    resp = client.get("/api/agents/devops/metrics")
    assert resp.status_code == 200
    assert resp.json()["agent_type"] == "devops"

def test_api_agent_status():
    resp = client.get("/api/agents/cybersecurity/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "READY"

# ── 4. Cybersecurity Access Control ────────────────────────────────────────

def test_invoke_cybersecurity_requires_admin(monkeypatch):
    monkeypatch.setattr("backend.app.config.settings.settings.AUTH_ENABLED", True)
    AuthService.reset()
    
    # 1. Without auth
    resp = client.post("/api/agents/cybersecurity/invoke", json={"task_id": "test"})
    assert resp.status_code == 401
    
    # 2. With developer role (should fail)
    headers = {"X-API-Key": "test-dev-key"}
    resp = client.post("/api/agents/cybersecurity/invoke", json={"task_id": "test"}, headers=headers)
    assert resp.status_code == 403
    
    # 3. With admin role (should pass)
    headers_admin = {"X-API-Key": "test-admin-key"}
    resp = client.post("/api/agents/cybersecurity/invoke", json={"task_id": "test"}, headers=headers_admin)
    assert resp.status_code == 200
    assert resp.json()["agent"] == "cybersecurity"

def test_invoke_devops_public():
    # DevOps does not require admin, though it still requires standard auth if enabled
    # When AUTH_ENABLED=False (default for testing), it should pass
    resp = client.post("/api/agents/devops/invoke", json={"task_id": "test"})
    assert resp.status_code == 200
    assert resp.json()["agent"] == "devops"
