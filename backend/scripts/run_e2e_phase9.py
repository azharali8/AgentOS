"""
AgentOS Phase 9 — End-to-End Demonstrations.

Demonstrates:
E2E #1: SDK Task Submission & Lifecycle Query
E2E #2: Task Execution Event Streaming (WebSocket/SSE)
E2E #3: Specialized Agent Invocation (Data Engineer) via SDK
E2E #4: Multi-Agent Software Engineering Task via SDK
E2E #5: Security & RBAC Enforcement (Cybersecurity Admin Restriction)
"""

import sys
from pathlib import Path

# Ensure SDK is in sys.path
_repo_root = Path(__file__).resolve().parent.parent.parent
_sdk_path = str(_repo_root / "sdk")
if _sdk_path not in sys.path:
    sys.path.insert(0, _sdk_path)
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from backend.app.main import app
from backend.app.auth.service import AuthService
from backend.app.config.settings import settings
from agentos.client import AgentOS
from agentos.exceptions import AuthorizationError


def run_phase9_e2e_demonstrations():
    print("=" * 60)
    print("AgentOS Phase 9 — End-to-End Platform Demonstrations")
    print("=" * 60)

    with AgentOS(app=app) as client:
        # ─────────────────────────────────────────────────────────────
        # E2E #1 — SDK Task Submission & Lifecycle
        # ─────────────────────────────────────────────────────────────
        print("\n[E2E #1] Executing Python SDK Task Submission & Lifecycle...")
        task = client.tasks.create(
            task="Audit codebase symbols and scan for sensitive files",
            priority=2,
            metadata={"environment": "e2e_demo"},
        )
        print(f" -> Task Created: ID={task.task_id} | Status={task.status}")

        status = client.tasks.status(task.task_id)
        print(f" -> Task Status Queried: is_active={status.is_active} | Status={status.status}")

        events = client.tasks.events(task.task_id)
        print(f" -> Recorded Task Events Count: {len(events)} (First: {events[0].event_type})")
        assert len(events) >= 1, "Expected at least 1 task event"
        print(" -> E2E #1 PASSED")

        # ─────────────────────────────────────────────────────────────
        # E2E #2 — WebSocket Event Streaming
        # ─────────────────────────────────────────────────────────────
        print("\n[E2E #2] Executing Event Stream Verification...")
        from fastapi.testclient import TestClient
        test_client = TestClient(app)
        with test_client.websocket_connect(f"/api/v1/events/stream/{task.task_id}") as ws:
            conn_msg = ws.receive_json()
            print(f" -> Received stream connection payload: {conn_msg.get('event_type')}")
            assert conn_msg.get("event_type") == "STREAM_CONNECTED"
            assert conn_msg.get("task_id") == task.task_id
        print(" -> E2E #2 PASSED")

        # ─────────────────────────────────────────────────────────────
        # E2E #3 — Specialized Agent Invocation (Data Engineer)
        # ─────────────────────────────────────────────────────────────
        print("\n[E2E #3] Executing Data Engineer Agent Invocation via SDK...")
        de_res = client.agents.invoke(
            agent_id="data_engineer",
            instruction="Profile datasets for schema consistency and missing values",
            target_files=["dataset_sample.csv"],
        )
        print(f" -> Agent Result: Status={de_res.status} | Agent={de_res.agent}")
        print(f" -> Summary: {de_res.summary}")
        assert de_res.status == "completed"
        print(" -> E2E #3 PASSED")

        # ─────────────────────────────────────────────────────────────
        # E2E #4 — Multi-Agent Task Orchestration
        # ─────────────────────────────────────────────────────────────
        print("\n[E2E #4] Executing Multi-Agent Engineering Task via SDK...")
        devops_res = client.agents.invoke(
            agent_id="devops",
            instruction="Create multi-stage container deployment pipeline",
        )
        print(f" -> DevOps Stage Result: Status={devops_res.status} | Summary={devops_res.summary}")

        testing_res = client.agents.invoke(
            agent_id="testing",
            instruction="Discover and execute regression test suite",
        )
        print(f" -> Testing Stage Result: Status={testing_res.status} | Summary={testing_res.summary}")
        assert devops_res.status == "completed"
        print(" -> E2E #4 PASSED")

        # ─────────────────────────────────────────────────────────────
        # E2E #5 — Security & RBAC Enforcement (Cybersecurity Admin Restriction)
        # ─────────────────────────────────────────────────────────────
        print("\n[E2E #5] Executing Cybersecurity ADMIN RBAC Security Enforcement...")
        orig_auth = settings.AUTH_ENABLED
        settings.AUTH_ENABLED = True
        AuthService.reset()

        try:
            # 1. Non-Admin (Developer) Attempt -> Blocked (403)
            with AgentOS(app=app, api_key="test-dev-key") as dev_client:
                blocked = False
                try:
                    dev_client.agents.invoke(
                        agent_id="cybersecurity",
                        instruction="Execute threat modeling audit",
                    )
                except AuthorizationError as exc:
                    blocked = True
                    print(f" -> Non-admin invocation correctly BLOCKED: {exc.message}")
                assert blocked is True, "Cybersecurity invocation must be blocked for non-admin"

            # 2. Admin Attempt -> Allowed (200)
            with AgentOS(app=app, api_key="test-admin-key") as admin_client:
                admin_res = admin_client.agents.invoke(
                    agent_id="cybersecurity",
                    instruction="Execute threat modeling audit",
                )
                print(f" -> Admin invocation ALLOWED: Status={admin_res.status} | Agent={admin_res.agent}")
                assert admin_res.status == "completed"
        finally:
            settings.AUTH_ENABLED = orig_auth

        print(" -> E2E #5 PASSED")

    print("\n" + "=" * 60)
    print("ALL 5 PHASE 9 END-TO-END DEMONSTRATIONS COMPLETED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    run_phase9_e2e_demonstrations()
