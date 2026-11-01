"""
H-01 Legacy API Authorization Tests
=====================================
Verifies that the legacy task endpoints at /api/tasks/* and the multi-agent
endpoints at /api/multi-agent/* correctly enforce authentication and
cross-user ownership isolation.

Test cases:
  1.  User A reads their own project-linked task               → 200 OK
  2.  User B reads their own project-linked task               → 200 OK
  3.  User A attempts to read User B's task                    → 404
  4.  User A attempts to read User B's task events             → 404
  5.  User A attempts to cancel User B's task                  → 404
  6.  User A changes task_id in URL to User B's task_id        → 404
  7.  Unauthenticated request to task list                     → 401
  8.  Unauthenticated request to task detail                   → 401
  9.  User A lists tasks — only sees own tasks, not B's        → filtered
  10. v1 project-scoped endpoints remain intact                → 200 OK
  11. Multi-agent run requires auth                            → 401 unauthenticated
  12. Multi-agent run succeeds when authenticated              → 200
  13. User A reads multi-agent state for User B's task        → 404
  14. User A reads multi-agent subtasks for User B's task     → 404
  15. User A reads multi-agent messages for User B's task     → 404
  16. User A reads multi-agent report for User B's task       → 404
  17. User A resolves multi-agent approval for User B's task  → 404
  18. Legacy unscoped tasks are inaccessible to normal users   → 404
"""

from uuid import uuid4
import pytest

from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.auth.service import AuthenticatedUser, AuthService, UserRole, get_current_user
from backend.app.config.settings import settings
from backend.app.main import app
from backend.app.models.task import TaskRequest, TaskStatus
from backend.app.services.project_service import ProjectService
from backend.app.services.task_service import TaskService


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def two_users_with_tasks(tmp_path, monkeypatch):
    """Create two isolated users (A and B), each with a project and one task."""
    user_a_id = f"u-alpha-{uuid4().hex[:6]}"
    user_b_id = f"u-beta-{uuid4().hex[:6]}"

    # Separate workspace directories per user project.
    ws_a = tmp_path / "ws_a"
    ws_b = tmp_path / "ws_b"
    ws_a.mkdir()
    ws_b.mkdir()

    # Register projects for each user.
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(ws_a))
    project_a = ProjectService.register(ws_a, "Project A", user_a_id)

    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(ws_b))
    project_b = ProjectService.register(ws_b, "Project B", user_b_id)

    # Create tasks for each user and attach to their project.
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(ws_a))
    task_a = TaskService.create_task(TaskRequest(instruction="Task belonging to user A"))
    ProjectService.attach_task(task_a.task_id, project_a["project_id"], None, user_a_id, "Task A")

    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(ws_b))
    task_b = TaskService.create_task(TaskRequest(instruction="Task belonging to user B"))
    ProjectService.attach_task(task_b.task_id, project_b["project_id"], None, user_b_id, "Task B")

    return {
        "user_a_id": user_a_id,
        "user_b_id": user_b_id,
        "task_a_id": task_a.task_id,
        "task_b_id": task_b.task_id,
        "project_a": project_a,
        "project_b": project_b,
    }


def _make_user(user_id: str, role: UserRole = UserRole.USER) -> AuthenticatedUser:
    return AuthenticatedUser(user_id=user_id, username=user_id, role=role)


def _client_as(user: AuthenticatedUser) -> TestClient:
    """Return a TestClient that authenticates all requests as *user*."""
    overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestLegacyTaskEndpointsAuth:
    """Tests covering /api/tasks/* endpoints."""

    # 1. User A reads their own task — allowed
    def test_user_a_can_read_own_task(self, two_users_with_tasks):
        ctx = two_users_with_tasks
        user_a = _make_user(ctx["user_a_id"])
        previous = dict(app.dependency_overrides)
        try:
            client = _client_as(user_a)
            resp = client.get(f"/api/tasks/{ctx['task_a_id']}")
            assert resp.status_code == 200, resp.text
            assert resp.json()["task_id"] == ctx["task_a_id"]
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)

    # 2. User B reads their own task — allowed
    def test_user_b_can_read_own_task(self, two_users_with_tasks):
        ctx = two_users_with_tasks
        user_b = _make_user(ctx["user_b_id"])
        previous = dict(app.dependency_overrides)
        try:
            client = _client_as(user_b)
            resp = client.get(f"/api/tasks/{ctx['task_b_id']}")
            assert resp.status_code == 200, resp.text
            assert resp.json()["task_id"] == ctx["task_b_id"]
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)

    # 3. User A attempts to read User B's task — blocked
    def test_user_a_cannot_read_user_b_task(self, two_users_with_tasks):
        ctx = two_users_with_tasks
        user_a = _make_user(ctx["user_a_id"])
        previous = dict(app.dependency_overrides)
        try:
            client = _client_as(user_a)
            resp = client.get(f"/api/tasks/{ctx['task_b_id']}")
            assert resp.status_code == 404, (
                f"Expected 404 but got {resp.status_code}: {resp.text}"
            )
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)

    # 4. User A attempts to read User B's task events — blocked
    def test_user_a_cannot_read_user_b_task_history(self, two_users_with_tasks):
        ctx = two_users_with_tasks
        user_a = _make_user(ctx["user_a_id"])
        previous = dict(app.dependency_overrides)
        try:
            client = _client_as(user_a)
            resp = client.get(f"/api/tasks/{ctx['task_b_id']}/history")
            assert resp.status_code == 404, (
                f"Expected 404 but got {resp.status_code}: {resp.text}"
            )
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)

    # 5. User A attempts to cancel User B's task — blocked
    def test_user_a_cannot_cancel_user_b_task(self, two_users_with_tasks):
        ctx = two_users_with_tasks
        user_a = _make_user(ctx["user_a_id"])
        previous = dict(app.dependency_overrides)
        try:
            client = _client_as(user_a)
            resp = client.post(f"/api/tasks/{ctx['task_b_id']}/cancel")
            assert resp.status_code == 404, (
                f"Expected 404 but got {resp.status_code}: {resp.text}"
            )
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)

    # 6. Swapping task_id in URL to another user's task — blocked (same as test 3)
    def test_task_id_substitution_is_blocked(self, two_users_with_tasks):
        ctx = two_users_with_tasks
        user_a = _make_user(ctx["user_a_id"])
        previous = dict(app.dependency_overrides)
        try:
            client = _client_as(user_a)
            # User A deliberately supplies B's task_id.
            resp = client.get(f"/api/tasks/{ctx['task_b_id']}")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)

    # 7. Unauthenticated request to task list — 401
    def test_unauthenticated_task_list_is_rejected(self):
        # Do NOT override get_current_user so real auth logic runs.
        previous = dict(app.dependency_overrides)
        try:
            app.dependency_overrides.pop(get_current_user, None)
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/tasks")
            assert resp.status_code == 401, (
                f"Expected 401 but got {resp.status_code}: {resp.text}"
            )
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)

    # 8. Unauthenticated request to task detail — 401
    def test_unauthenticated_task_detail_is_rejected(self, two_users_with_tasks):
        ctx = two_users_with_tasks
        previous = dict(app.dependency_overrides)
        try:
            app.dependency_overrides.pop(get_current_user, None)
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(f"/api/tasks/{ctx['task_a_id']}")
            assert resp.status_code == 401, (
                f"Expected 401 but got {resp.status_code}: {resp.text}"
            )
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)

    # 9. Task list is filtered — user A sees only their tasks
    def test_task_list_is_filtered_per_user(self, two_users_with_tasks):
        ctx = two_users_with_tasks
        user_a = _make_user(ctx["user_a_id"])
        previous = dict(app.dependency_overrides)
        try:
            client = _client_as(user_a)
            resp = client.get("/api/tasks")
            assert resp.status_code == 200, resp.text
            task_ids = [t["task_id"] for t in resp.json()]
            assert ctx["task_a_id"] in task_ids, "User A's task must be visible"
            assert ctx["task_b_id"] not in task_ids, "User B's task must NOT be visible"
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)

    # 18. Legacy unscoped tasks are inaccessible to non-admin users
    def test_legacy_unscoped_task_is_hidden_from_normal_user(self):
        """A task with no project attachment must not be readable by a regular user."""
        legacy_task = TaskService.create_task(TaskRequest(instruction="Legacy unscoped task"))
        user = _make_user(f"u-anon-{uuid4().hex[:6]}")
        previous = dict(app.dependency_overrides)
        try:
            client = _client_as(user)
            resp = client.get(f"/api/tasks/{legacy_task.task_id}")
            assert resp.status_code == 404, (
                f"Expected 404 for unscoped task, got {resp.status_code}: {resp.text}"
            )
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)


class TestV1TaskEndpointsUnchanged:
    """Regression: v1 project-scoped task endpoints remain functional for authorised users."""

    # 10. v1 task detail for owner — 200
    def test_v1_task_detail_accessible_to_owner(self, two_users_with_tasks):
        ctx = two_users_with_tasks
        user_a = _make_user(ctx["user_a_id"])
        previous = dict(app.dependency_overrides)
        try:
            client = _client_as(user_a)
            resp = client.get(f"/api/v1/tasks/{ctx['task_a_id']}")
            assert resp.status_code == 200, resp.text
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)

    # v1 cross-user access still blocked
    def test_v1_task_detail_blocked_for_non_owner(self, two_users_with_tasks):
        ctx = two_users_with_tasks
        user_a = _make_user(ctx["user_a_id"])
        previous = dict(app.dependency_overrides)
        try:
            client = _client_as(user_a)
            resp = client.get(f"/api/v1/tasks/{ctx['task_b_id']}")
            assert resp.status_code == 404, resp.text
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)


class TestMultiAgentEndpointsAuth:
    """Tests covering /api/multi-agent/* endpoints."""

    # 11. Multi-agent run requires auth — 401 unauthenticated
    def test_multi_agent_run_requires_auth(self):
        previous = dict(app.dependency_overrides)
        try:
            app.dependency_overrides.pop(get_current_user, None)
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/api/multi-agent/run", json={"instruction": "Do something"})
            assert resp.status_code == 401, (
                f"Expected 401 but got {resp.status_code}: {resp.text}"
            )
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)

    # 12. Authenticated user can reach the run endpoint (task may fail due to mock
    #     LLM, but auth is accepted: 200 or 400/500, NOT 401/403).
    def test_multi_agent_run_accepted_when_authenticated(self):
        user = _make_user(f"u-runner-{uuid4().hex[:6]}", role=UserRole.USER)
        previous = dict(app.dependency_overrides)
        try:
            client = _client_as(user)
            resp = client.post("/api/multi-agent/run", json={"instruction": "Do something", "sync": False})
            # Auth passed — task was created or returned whatever the mock LLM does.
            # We accept any non-auth error code (not 401 / 403).
            assert resp.status_code not in (401, 403), (
                f"Expected auth to be accepted, got {resp.status_code}: {resp.text}"
            )
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)

    def _cross_user_multi_agent_check(self, ctx, endpoint_path: str, method: str = "get"):
        """Helper: User A tries to access User B's task at the given multi-agent route."""
        user_a = _make_user(ctx["user_a_id"])
        previous = dict(app.dependency_overrides)
        try:
            client = _client_as(user_a)
            fn = getattr(client, method)
            resp = fn(endpoint_path)
            assert resp.status_code == 404, (
                f"Expected 404 for cross-user access to {endpoint_path}, "
                f"got {resp.status_code}: {resp.text}"
            )
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)

    # 13. User A reads multi-agent state for User B's task → 404
    def test_cross_user_multi_agent_status_blocked(self, two_users_with_tasks):
        ctx = two_users_with_tasks
        self._cross_user_multi_agent_check(ctx, f"/api/multi-agent/{ctx['task_b_id']}")

    # 14. User A reads multi-agent subtasks for User B's task → 404
    def test_cross_user_multi_agent_subtasks_blocked(self, two_users_with_tasks):
        ctx = two_users_with_tasks
        self._cross_user_multi_agent_check(ctx, f"/api/multi-agent/{ctx['task_b_id']}/subtasks")

    # 15. User A reads multi-agent messages for User B's task → 404
    def test_cross_user_multi_agent_messages_blocked(self, two_users_with_tasks):
        ctx = two_users_with_tasks
        self._cross_user_multi_agent_check(ctx, f"/api/multi-agent/{ctx['task_b_id']}/messages")

    # 16. User A reads multi-agent report for User B's task → 404
    def test_cross_user_multi_agent_report_blocked(self, two_users_with_tasks):
        ctx = two_users_with_tasks
        self._cross_user_multi_agent_check(ctx, f"/api/multi-agent/{ctx['task_b_id']}/report")

    # 17. User A resolves approval on User B's task → 404
    def test_cross_user_multi_agent_resolve_blocked(self, two_users_with_tasks):
        ctx = two_users_with_tasks
        self._cross_user_multi_agent_check(
            ctx,
            f"/api/multi-agent/{ctx['task_b_id']}/resolve",
            method="post",
        )

    # Multi-agent task — unauthenticated state access is rejected
    def test_multi_agent_status_requires_auth(self, two_users_with_tasks):
        ctx = two_users_with_tasks
        previous = dict(app.dependency_overrides)
        try:
            app.dependency_overrides.pop(get_current_user, None)
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(f"/api/multi-agent/{ctx['task_a_id']}")
            assert resp.status_code == 401, (
                f"Expected 401 but got {resp.status_code}: {resp.text}"
            )
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)
