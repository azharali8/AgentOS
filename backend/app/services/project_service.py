"""Durable project/conversation membership over the existing task engine.

Workspace activation continues to use the existing validated, idle-only route.
Legacy tasks are deliberately not assigned to a project by guessing their path.
"""
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from backend.app.config.settings import settings
from backend.app.db.database import get_db_session
from backend.app.db.models import ProjectModel, ConversationModel, ConversationTaskModel, WorkspacePreferenceModel, TaskModel


class ProjectService:
    @staticmethod
    def _owned(db, project_id, owner_id):
        project = db.get(ProjectModel, project_id)
        if project is None or project.owner_id != owner_id:
            raise HTTPException(404, "Project not found")
        return project

    @staticmethod
    def _data(project):
        return dict(project_id=project.project_id, name=project.name,
                    workspace_path=project.workspace_path, created_at=project.created_at)

    @classmethod
    def register(cls, path, name, owner_id):
        canonical = str(Path(path).resolve())
        with get_db_session() as db:
            project = db.query(ProjectModel).filter_by(owner_id=owner_id, workspace_path=canonical).first()
            if project is None:
                project = ProjectModel(project_id=str(uuid4()), owner_id=owner_id,
                                       name=(name.strip() or Path(canonical).name)[:200], workspace_path=canonical)
                db.add(project)
                db.flush()
            cls._select(db, owner_id, project.project_id)
            return cls._data(project)

    @staticmethod
    def _select(db, owner_id, project_id):
        key = f"project:{owner_id}"
        preference = db.get(WorkspacePreferenceModel, key)
        if preference is None:
            db.add(WorkspacePreferenceModel(key=key, value={"project_id": project_id}))
        else:
            preference.value = {"project_id": project_id}

    @classmethod
    def deselect(cls, owner_id):
        with get_db_session() as db:
            cls._select(db, owner_id, None)

    @classmethod
    def list(cls, owner_id, limit=50, offset=0):
        with get_db_session() as db:
            projects = db.query(ProjectModel).filter_by(owner_id=owner_id).order_by(
                ProjectModel.created_at.desc(), ProjectModel.project_id).offset(offset).limit(limit).all()
            preference = db.get(WorkspacePreferenceModel, f"project:{owner_id}")
            selected = (preference.value or {}).get("project_id") if preference else None
            current = db.get(ProjectModel, selected) if selected else None
            # A different user or legacy API may have switched the shared engine.
            if not current or Path(current.workspace_path).resolve() != Path(settings.WORKSPACE_ROOT).resolve():
                selected = None
            return {"projects": [cls._data(p) for p in projects], "active_project_id": selected}

    @classmethod
    def get(cls, project_id, owner_id):
        with get_db_session() as db:
            return cls._data(cls._owned(db, project_id, owner_id))

    @classmethod
    def conversations(cls, project_id, owner_id, limit=50, offset=0):
        with get_db_session() as db:
            cls._owned(db, project_id, owner_id)
            return [dict(conversation_id=c.conversation_id, project_id=c.project_id,
                         title=c.title, created_at=c.created_at)
                    for c in db.query(ConversationModel).filter_by(project_id=project_id).order_by(
                        ConversationModel.created_at.desc(), ConversationModel.conversation_id).offset(offset).limit(limit)]

    @classmethod
    def validate_submission(cls, project_id, conversation_id, owner_id):
        with get_db_session() as db:
            project = cls._owned(db, project_id, owner_id)
            root = Path(project.workspace_path)
            if not root.is_dir() or root.resolve() != Path(settings.WORKSPACE_ROOT).resolve():
                raise HTTPException(409, "Select this available project before submitting work")
            if conversation_id:
                conversation = db.get(ConversationModel, conversation_id)
                if not conversation or conversation.project_id != project_id:
                    raise HTTPException(404, "Conversation not found in this project")

    @classmethod
    def attach_task(cls, task_id, project_id, conversation_id, owner_id, title):
        cls.validate_submission(project_id, conversation_id, owner_id)
        with get_db_session() as db:
            if not conversation_id:
                conversation_id = str(uuid4())
                db.add(ConversationModel(conversation_id=conversation_id, project_id=project_id, title=title[:200]))
                db.flush()
            db.add(ConversationTaskModel(task_id=task_id, conversation_id=conversation_id))
            task = db.get(TaskModel, task_id)
            task.task_metadata = {**(task.task_metadata or {}), "project_id": project_id,
                                  "conversation_id": conversation_id, "project_owner": owner_id}
            return conversation_id

    @classmethod
    def task_scope(cls, task_id, owner_id=None):
        with get_db_session() as db:
            row = db.query(ProjectModel, ConversationModel).join(
                ConversationModel, ConversationModel.project_id == ProjectModel.project_id).join(
                ConversationTaskModel, ConversationTaskModel.conversation_id == ConversationModel.conversation_id).filter(
                ConversationTaskModel.task_id == task_id).first()
            if not row:
                return {}
            project, conversation = row
            if owner_id is not None and project.owner_id != owner_id:
                raise HTTPException(404, "Task not found")
            return {"project_id": project.project_id, "conversation_id": conversation.conversation_id}

    @classmethod
    def tasks(cls, project_id, conversation_id, owner_id, limit=50, offset=0):
        with get_db_session() as db:
            cls._owned(db, project_id, owner_id)
            conversation = db.get(ConversationModel, conversation_id)
            if not conversation or conversation.project_id != project_id:
                raise HTTPException(404, "Conversation not found in this project")
            ids = [row.task_id for row in db.query(ConversationTaskModel).filter_by(
                conversation_id=conversation_id).order_by(ConversationTaskModel.created_at, ConversationTaskModel.task_id).offset(offset).limit(limit)]
        from backend.app.services.task_service import TaskService
        return [TaskService.get_task(task_id) for task_id in ids]
