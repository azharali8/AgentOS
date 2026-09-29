from contextlib import contextmanager
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.app.config.settings import settings
from backend.app.db.database import Base
from backend.app.db.models import TaskModel
from backend.app.api.routes.v1 import (
    WorkspaceSetRootRequest, set_workspace_root, disconnect_workspace_v1,
)


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
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path / "installation")
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(tmp_path / "original"))
    yield session
    engine.dispose()


@pytest.mark.parametrize("status", ["EXECUTING", "WAITING_APPROVAL", "PAUSED"])
def test_project_switch_and_disconnect_reject_active_tasks(workspace_db, tmp_path, status):
    with workspace_db() as db:
        db.add(TaskModel(task_id="active", user_request="Edit project A", status=status))
    project = tmp_path / "project-b"
    project.mkdir()
    before = settings.WORKSPACE_ROOT
    for change in (lambda: set_workspace_root(WorkspaceSetRootRequest(path=str(project))), disconnect_workspace_v1):
        with pytest.raises(HTTPException) as exc:
            change()
        assert exc.value.status_code == 409
        assert settings.WORKSPACE_ROOT == before


def test_connect_change_disconnect_updates_backend_without_env_persistence(workspace_db, tmp_path):
    for name in ("project-a", "project-b"):
        project = tmp_path / name
        project.mkdir()
        response = set_workspace_root(WorkspaceSetRootRequest(path=str(project)))
        assert response["path"] == str(project)
        assert response["persisted"] is False
        assert settings.WORKSPACE_ROOT == str(project)
    response = disconnect_workspace_v1()
    assert response["disconnected"]
    assert settings.WORKSPACE_ROOT == str(tmp_path / "installation" / "workspace")
