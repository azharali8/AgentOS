from contextlib import contextmanager
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.app.config.settings import settings
from backend.app.db.database import Base
from datetime import datetime, timedelta, timezone
from backend.app.db.models import ApprovalModel, QueueEntryModel, TaskLeaseModel, TaskModel
from backend.app.auth.service import AuthenticatedUser, UserRole

USER = AuthenticatedUser(user_id="workspace-test", username="workspace-test", role=UserRole.DEVELOPER)
from backend.app.api.routes.v1 import (
    WorkspaceSetRootRequest, set_workspace_root, disconnect_workspace_v1,
)
from backend.app.services.workspace_transition import admit_workspace_task, release_workspace_task


@pytest.fixture
def workspace_db(tmp_path, monkeypatch):
    from backend.app.db import database
    from backend.app.config import settings as config
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    @contextmanager
    def session():
        with Session(engine) as db:
            yield db
            db.commit()
    monkeypatch.setattr(database, "get_db_session", session)
    monkeypatch.setattr("backend.app.services.project_service.get_db_session", session)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path / "installation")
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(tmp_path / "original"))
    yield session
    engine.dispose()


@pytest.mark.parametrize("status", ["EXECUTING", "WAITING_APPROVAL", "PAUSED", "RECOVERY_REQUIRED"])
def test_project_switch_and_disconnect_reject_active_tasks(workspace_db, tmp_path, status):
    with workspace_db() as db:
        db.add(TaskModel(task_id="active", user_request="Edit project A", status=status))
    project = tmp_path / "project-b"
    project.mkdir()
    before = settings.WORKSPACE_ROOT
    for change in (lambda: set_workspace_root(WorkspaceSetRootRequest(path=str(project)), USER), lambda: disconnect_workspace_v1(USER)):
        with pytest.raises(HTTPException) as exc:
            change()
        assert exc.value.status_code == 409
        assert settings.WORKSPACE_ROOT == before


def test_selecting_current_workspace_is_safe_while_approval_is_pending(workspace_db, tmp_path):
    current = tmp_path / "original"
    current.mkdir()
    with workspace_db() as db:
        db.add(TaskModel(task_id="approval", user_request="Await approval", status="WAITING_APPROVAL"))
        db.add(ApprovalModel(
            approval_id="approval-current", task_id="approval", step_id="apply", tool_name="patch.apply",
            operation="apply", arguments_hash="0" * 64, arguments_summary={}, risk_level="HIGH", status="PENDING",
        ))
    response = set_workspace_root(WorkspaceSetRootRequest(path=str(current)), USER)
    assert response["path"] == str(current)
    assert settings.WORKSPACE_ROOT == str(current)


def test_unadmitted_pending_task_does_not_block_workspace_change(workspace_db, tmp_path):
    with workspace_db() as db:
        db.add(TaskModel(task_id="historical-pending", user_request="Never admitted", status="PENDING"))
    project = tmp_path / "project-b"
    project.mkdir()
    response = set_workspace_root(WorkspaceSetRootRequest(path=str(project)), USER)
    assert response["path"] == str(project)


def test_admitted_pending_task_blocks_connect_and_disconnect(workspace_db, tmp_path):
    with workspace_db() as db:
        db.add(TaskModel(task_id="admitted", user_request="Worker is starting", status="PENDING"))
    admit_workspace_task("admitted")
    project = tmp_path / "project-b"
    project.mkdir()
    try:
        with pytest.raises(HTTPException) as exc:
            set_workspace_root(WorkspaceSetRootRequest(path=str(project)), USER)
        assert exc.value.status_code == 409
        with pytest.raises(HTTPException) as exc:
            disconnect_workspace_v1(USER)
        assert exc.value.status_code == 409
    finally:
        release_workspace_task("admitted")


def test_failed_worker_does_not_leave_admission_reservation(workspace_db, tmp_path):
    with workspace_db() as db:
        db.add(TaskModel(task_id="failed-start", user_request="Worker failed", status="FAILED"))
    # Simulates the route worker exception path: a stale in-memory reservation
    # for a terminal task is discarded by the guard.
    admit_workspace_task("failed-start")
    project = tmp_path / "project-b"
    project.mkdir()
    response = set_workspace_root(WorkspaceSetRootRequest(path=str(project)), USER)
    assert response["path"] == str(project)


def test_registration_failure_leaves_process_workspace_unchanged(workspace_db, tmp_path, monkeypatch):
    project = tmp_path / "project-b"
    project.mkdir()
    before = settings.WORKSPACE_ROOT
    monkeypatch.setattr(
        "backend.app.services.project_service.ProjectService.register",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    with pytest.raises(RuntimeError, match="database unavailable"):
        set_workspace_root(WorkspaceSetRootRequest(path=str(project)), USER)
    assert settings.WORKSPACE_ROOT == before


def test_queued_pending_task_blocks_workspace_change(workspace_db, tmp_path):
    with workspace_db() as db:
        db.add(TaskModel(task_id="queued", user_request="Await worker", status="PENDING"))
        db.add(QueueEntryModel(queue_id="queue-1", task_id="queued", priority=2, status="QUEUED", required_capabilities=[]))
    project = tmp_path / "project-b"
    project.mkdir()
    with pytest.raises(HTTPException) as exc:
        set_workspace_root(WorkspaceSetRootRequest(path=str(project)), USER)
    assert exc.value.status_code == 409


def test_pending_approval_blocks_even_when_task_status_is_stale(workspace_db, tmp_path):
    with workspace_db() as db:
        db.add(TaskModel(task_id="approval", user_request="Await approval", status="PENDING"))
        db.add(ApprovalModel(
            approval_id="approval-1", task_id="approval", step_id="apply", tool_name="patch.apply",
            operation="apply", arguments_hash="0" * 64, arguments_summary={}, risk_level="HIGH", status="PENDING",
        ))
    project = tmp_path / "project-b"
    project.mkdir()
    with pytest.raises(HTTPException) as exc:
        set_workspace_root(WorkspaceSetRootRequest(path=str(project)), USER)
    assert exc.value.status_code == 409


def test_terminal_task_stale_queue_entry_does_not_block(workspace_db, tmp_path):
    with workspace_db() as db:
        db.add(TaskModel(task_id="finished", user_request="Finished", status="COMPLETED"))
        db.add(QueueEntryModel(queue_id="queue-finished", task_id="finished", priority=2, status="QUEUED", required_capabilities=[]))
    project = tmp_path / "project-b"
    project.mkdir()
    assert set_workspace_root(WorkspaceSetRootRequest(path=str(project)), USER)["path"] == str(project)


def test_expired_lease_does_not_block_but_live_lease_does(workspace_db, tmp_path):
    now = datetime.now(timezone.utc)
    with workspace_db() as db:
        db.add(TaskModel(task_id="expired", user_request="Expired", status="PENDING"))
        db.add(TaskLeaseModel(lease_id="lease-expired", task_id="expired", worker_id="w1", fencing_token=1,
                              lease_expires_at=now - timedelta(seconds=1), status="ACTIVE"))
    project = tmp_path / "project-b"
    project.mkdir()
    assert set_workspace_root(WorkspaceSetRootRequest(path=str(project)), USER)["path"] == str(project)
    with workspace_db() as db:
        db.add(TaskModel(task_id="live", user_request="Live", status="PENDING"))
        db.add(TaskLeaseModel(lease_id="lease-live", task_id="live", worker_id="w1", fencing_token=1,
                              lease_expires_at=now + timedelta(minutes=1), status="ACTIVE"))
    with pytest.raises(HTTPException) as exc:
        disconnect_workspace_v1(USER)
    assert exc.value.status_code == 409


def test_builtin_workspace_is_the_only_allowed_installation_subdirectory(workspace_db, tmp_path):
    installation = tmp_path / "installation"
    builtin = installation / "workspace"
    builtin.mkdir(parents=True)
    response = set_workspace_root(WorkspaceSetRootRequest(path=str(builtin)), USER)
    assert response["path"] == str(builtin)


def test_connect_change_disconnect_updates_backend_without_env_persistence(workspace_db, tmp_path):
    for name in ("project-a", "project-b"):
        project = tmp_path / name
        project.mkdir()
        response = set_workspace_root(WorkspaceSetRootRequest(path=str(project)), USER)
        assert response["path"] == str(project)
        assert response["persisted"] is False
        assert settings.WORKSPACE_ROOT == str(project)
    response = disconnect_workspace_v1(USER)
    assert response["disconnected"]
    assert settings.WORKSPACE_ROOT == str(tmp_path / "installation" / "workspace")
