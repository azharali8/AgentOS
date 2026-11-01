import pytest
from pathlib import Path
from uuid import uuid4

from backend.app.config.settings import settings
from backend.app.models.multi_agent import AgentType, SubTask
from backend.app.services.project_service import ProjectService
from backend.app.services.workspace_service import WorkspaceService, WorkspaceSecurityError
from backend.app.agents.domain_experts import TestingAgent
from backend.app.db.database import get_db_session
from backend.app.db.models import ProjectModel, ConversationModel, ConversationTaskModel, TaskModel


def test_explicit_task_workspace_propagates_to_testing_agent(tmp_path, monkeypatch):
    """Confirm testing agent uses task's registered project workspace rather than global settings."""
    ws_project = tmp_path / "project_alpha"
    ws_project.mkdir()
    (ws_project / "test_sample.py").write_text("def test_ok(): assert True\n", encoding="utf-8")

    ws_global = tmp_path / "global_default"
    ws_global.mkdir()
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(ws_global))

    task_id = str(uuid4())
    owner_id = "test-owner-1"
    proj_id = str(uuid4())
    conv_id = str(uuid4())

    with get_db_session() as db:
        db.add(ProjectModel(project_id=proj_id, owner_id=owner_id, name="Alpha", workspace_path=str(ws_project)))
        db.add(ConversationModel(conversation_id=conv_id, project_id=proj_id, title="Test conv"))
        db.add(TaskModel(task_id=task_id, user_request="Run tests in alpha", status="PENDING"))
        db.add(ConversationTaskModel(task_id=task_id, conversation_id=conv_id))

    resolved_root = WorkspaceService.get_workspace_root(task_id=task_id)
    assert resolved_root == ws_project.resolve()

    agent = TestingAgent()
    subtask = SubTask(
        task_id=task_id,
        subtask_id="st-test-1",
        description="Run test_sample.py",
        assigned_agent=AgentType.TESTING,
        target_files=["test_sample.py"],
    )
    result = agent.execute(subtask)

    assert agent.runner._root == ws_project.resolve()
    assert result.evidence.get("passed") is True or "test_sample.py" in str(result.evidence)


def test_stale_temporary_workspace_not_selected_when_valid_task_workspace_exists(tmp_path, monkeypatch):
    """Ensure stale temporary dir from settings is bypassed when task has an explicit project workspace."""
    stale_temp = tmp_path / "stale_temp_dir"
    stale_temp.mkdir()
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(stale_temp))

    task_ws = tmp_path / "legit_workspace"
    task_ws.mkdir()

    task_id = str(uuid4())
    owner_id = "test-owner-2"
    proj_id = str(uuid4())
    conv_id = str(uuid4())

    with get_db_session() as db:
        db.add(ProjectModel(project_id=proj_id, owner_id=owner_id, name="Legit", workspace_path=str(task_ws)))
        db.add(ConversationModel(conversation_id=conv_id, project_id=proj_id, title="Legit conv"))
        db.add(TaskModel(task_id=task_id, user_request="Task on legit", status="PENDING"))
        db.add(ConversationTaskModel(task_id=task_id, conversation_id=conv_id))

    resolved = WorkspaceService.get_workspace_root(task_id=task_id)
    assert resolved == task_ws.resolve()
    assert resolved != stale_temp.resolve()


def test_missing_or_invalid_workspace_path_fails_safely(tmp_path):
    """Ensure that if the assigned project workspace directory is missing, WorkspaceSecurityError is raised."""
    missing_dir = tmp_path / "non_existent_project_folder"
    task_id = str(uuid4())
    owner_id = "test-owner-3"
    proj_id = str(uuid4())
    conv_id = str(uuid4())

    with get_db_session() as db:
        db.add(ProjectModel(project_id=proj_id, owner_id=owner_id, name="Ghost", workspace_path=str(missing_dir)))
        db.add(ConversationModel(conversation_id=conv_id, project_id=proj_id, title="Ghost conv"))
        db.add(TaskModel(task_id=task_id, user_request="Task on ghost", status="PENDING"))
        db.add(ConversationTaskModel(task_id=task_id, conversation_id=conv_id))

    with pytest.raises(WorkspaceSecurityError, match="Task workspace directory does not exist or is invalid"):
        WorkspaceService.get_workspace_root(task_id=task_id)


def test_different_tasks_isolated_workspaces(tmp_path):
    """Ensure two tasks attached to different projects cannot share or overwrite workspace context."""
    ws_a = tmp_path / "project_a"
    ws_b = tmp_path / "project_b"
    ws_a.mkdir()
    ws_b.mkdir()

    task_a = str(uuid4())
    task_b = str(uuid4())
    owner_id = "test-owner-4"
    proj_a = str(uuid4())
    proj_b = str(uuid4())
    conv_a = str(uuid4())
    conv_b = str(uuid4())

    with get_db_session() as db:
        db.add(ProjectModel(project_id=proj_a, owner_id=owner_id, name="A", workspace_path=str(ws_a)))
        db.add(ProjectModel(project_id=proj_b, owner_id=owner_id, name="B", workspace_path=str(ws_b)))
        db.add(ConversationModel(conversation_id=conv_a, project_id=proj_a, title="Conv A"))
        db.add(ConversationModel(conversation_id=conv_b, project_id=proj_b, title="Conv B"))
        db.add(TaskModel(task_id=task_a, user_request="Task in A", status="PENDING"))
        db.add(TaskModel(task_id=task_b, user_request="Task in B", status="PENDING"))
        db.add(ConversationTaskModel(task_id=task_a, conversation_id=conv_a))
        db.add(ConversationTaskModel(task_id=task_b, conversation_id=conv_b))

    root_a = WorkspaceService.get_workspace_root(task_id=task_a)
    root_b = WorkspaceService.get_workspace_root(task_id=task_b)

    assert root_a == ws_a.resolve()
    assert root_b == ws_b.resolve()
    assert root_a != root_b
