from uuid import uuid4
import pytest
from fastapi import HTTPException
from backend.app.config.settings import settings
from backend.app.services.project_service import ProjectService
from backend.app.services.task_service import TaskService
from backend.app.services.event_service import EventService
from backend.app.models.task import TaskRequest, TaskStatus


@pytest.fixture
def projects(tmp_path, monkeypatch):
    owner = uuid4().hex
    a, b = tmp_path / 'A', tmp_path / 'B'
    a.mkdir(); b.mkdir()
    monkeypatch.setattr(settings, 'WORKSPACE_ROOT', str(a))
    first = ProjectService.register(a, 'Project A', owner)
    second = ProjectService.register(b, 'Project B', owner)
    return owner, first, second


def test_project_conversation_task_evidence_isolation(projects):
    owner, a, b = projects
    task = TaskService.create_task(TaskRequest(instruction='Inspect Project A'))
    conversation = ProjectService.attach_task(task.task_id, a['project_id'], None, owner, task.user_request)
    EventService.record_event(task.task_id, 'FILE_READ', payload={'path': 'main.py'})
    TaskService.update_task_status(task.task_id, TaskStatus.COMPLETED)
    assert ProjectService.conversations(b['project_id'], owner) == []
    with pytest.raises(HTTPException) as error:
        ProjectService.tasks(b['project_id'], conversation, owner)
    assert error.value.status_code == 404
    restored = ProjectService.tasks(a['project_id'], conversation, owner)
    assert restored[0].status == TaskStatus.COMPLETED
    event = EventService.list_events(task.task_id)[0]
    assert event['project_id'] == a['project_id'] and event['conversation_id'] == conversation
    assert event['payload']['path'] == 'main.py'


def test_other_user_cannot_read_project_or_task(projects):
    owner, a, _ = projects
    task = TaskService.create_task(TaskRequest(instruction='Read project'))
    ProjectService.attach_task(task.task_id, a['project_id'], None, owner, 'Read')
    assert ProjectService.list('other-user')['projects'] == []
    for call in [lambda: ProjectService.get(a['project_id'], 'other-user'),
                 lambda: ProjectService.task_scope(task.task_id, 'other-user')]:
        with pytest.raises(HTTPException) as error:
            call()
        assert error.value.status_code == 404


def test_submission_rejects_wrong_or_missing_workspace(projects, monkeypatch):
    owner, a, b = projects
    with pytest.raises(HTTPException) as error:
        ProjectService.validate_submission(b['project_id'], None, owner)
    assert error.value.status_code == 409
    monkeypatch.setattr(settings, 'WORKSPACE_ROOT', b['workspace_path'])
    with pytest.raises(HTTPException):
        ProjectService.validate_submission(a['project_id'], None, owner)


def test_project_registry_is_durable_and_disconnect_preserves_history(projects):
    owner, a, _ = projects
    again = ProjectService.register(a['workspace_path'], a['name'], owner)
    assert again['project_id'] == a['project_id']
    assert ProjectService.list(owner)['active_project_id'] == a['project_id']
    ProjectService.deselect(owner)
    restored = ProjectService.list(owner)
    assert restored['active_project_id'] is None and len(restored['projects']) == 2


def test_legacy_tasks_are_not_guessed_into_project(projects):
    owner, a, _ = projects
    task = TaskService.create_task(TaskRequest(instruction='Old task without project'))
    assert ProjectService.task_scope(task.task_id) == {}
    assert ProjectService.conversations(a['project_id'], owner) == []


def test_equal_timestamp_event_order_is_stable(projects):
    from backend.app.db.database import get_db_session
    from backend.app.db.models import EventModel
    from datetime import datetime, timezone
    task = TaskService.create_task(TaskRequest(instruction='Ordered task'))
    stamp = datetime.now(timezone.utc)
    with get_db_session() as db:
        for event_id in ['z', 'a', 'm']:
            db.add(EventModel(event_id=uuid4().hex[:20]+event_id, task_id=task.task_id,
                              event_type='STATUS', timestamp=stamp))
    whole = EventService.list_events(task.task_id)
    pages = [EventService.list_events(task.task_id, 1, offset)[0] for offset in range(3)]
    assert [e['event_id'] for e in pages] == sorted(e['event_id'] for e in whole)


def test_additive_migration_preserves_legacy_task_and_foreign_keys():
    import importlib
    from sqlalchemy import create_engine, text, inspect
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    migration = importlib.import_module('backend.app.db.migrations.versions.f2a3b4c5d6e7_project_conversations')
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('PRAGMA foreign_keys=ON'))
        connection.execute(text('CREATE TABLE tasks (task_id VARCHAR(36) PRIMARY KEY, user_request TEXT)'))
        connection.execute(text("INSERT INTO tasks VALUES ('legacy', 'Keep original evidence')"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert connection.execute(text('SELECT user_request FROM tasks')).scalar() == 'Keep original evidence'
        assert len(inspect(connection).get_foreign_keys('conversation_tasks')) == 2
        assert connection.execute(text('SELECT count(*) FROM conversation_tasks')).scalar() == 0
    engine.dispose()


def test_project_api_scopes_tasks_events_and_artifacts(projects):
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app.auth.service import get_current_user, AuthenticatedUser, UserRole
    from backend.app.services.artifact_service import ArtifactService, ArtifactType
    owner, a, b = projects
    user = AuthenticatedUser(user_id=owner, username='project-test', role=UserRole.DEVELOPER)
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        client = TestClient(app)
        response = client.post('/api/v1/tasks', json={'task': 'Inspect calculator', 'project_id': a['project_id'], 'auto_start': False})
        assert response.status_code == 201, response.text
        task = response.json()
        conversation = task['metadata']['conversation_id']
        task_id = task['task_id']
        artifact = ArtifactService.save(task_id=task_id, agent_id='testing', artifact_type=ArtifactType.TEST_REPORT, content={'passed': False, 'failed_count': 1})
        events = client.get(f'/api/v1/tasks/{task_id}/events').json()
        assert events[0]['project_id'] == a['project_id']
        assert client.get(f"/api/v1/projects/{a['project_id']}/conversations/{conversation}/tasks").json()[0]['task_id'] == task_id
        assert client.get(f"/api/v1/projects/{b['project_id']}/conversations/{conversation}/tasks").status_code == 404
        assert client.post('/api/v1/tasks', json={'task': 'Wrong conversation', 'project_id': b['project_id'], 'conversation_id': conversation, 'auto_start': False}).status_code in (404, 409)
        from backend.app.security.approval import ApprovalManager
        from backend.app.models.approval import ApprovalRequest
        from backend.app.models.tool import RiskLevel
        approval_id = str(uuid4())
        ApprovalManager.request_approval(ApprovalRequest(
            approval_id=approval_id, task_id=task_id, step_id='step', tool_name='file_editor',
            operation='apply_patch', arguments_hash='', arguments_summary={'files': ['calculator.py']},
            risk_level=RiskLevel.HIGH, reason='Project-specific patch'))
        assert client.get(f'/api/v1/approvals/{approval_id}').json()['task_id'] == task_id
        user = AuthenticatedUser(user_id='other-owner' , username='other', role=UserRole.ADMIN)
        assert client.get(f'/api/v1/approvals/{approval_id}').status_code == 404
        assert client.post(f'/api/v1/approvals/{approval_id}/resolve', json={'approved': True}).status_code == 404
        assert all(item['approval_id'] != approval_id for item in client.get('/api/v1/approvals').json())
        assert ApprovalManager.get_approval(approval_id).status.value == 'PENDING'
        for route in [f'/api/v1/tasks/{task_id}', f'/api/v1/tasks/{task_id}/events', f'/api/v1/tasks/{task_id}/artifacts', f'/api/v1/artifacts/{artifact.artifact_id}']:
            assert client.get(route).status_code == 404, route
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
