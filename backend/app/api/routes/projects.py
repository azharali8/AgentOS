"""Projects reuse workspace validation and the existing Supervisor task API."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from backend.app.auth.service import AuthenticatedUser, get_current_user, require_role, UserRole
from backend.app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["v1-projects"])


class ConnectProject(BaseModel):
    path: str = Field(min_length=1)
    name: str = Field(default="", max_length=200)


@router.get("")
def list_projects(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                  user: AuthenticatedUser = Depends(get_current_user)):
    return ProjectService.list(user.user_id, limit, offset)


@router.post("/connect")
def connect_project(req: ConnectProject, user: AuthenticatedUser = Depends(require_role(UserRole.DEVELOPER))):
    from backend.app.api.routes.v1 import set_workspace_root, WorkspaceSetRootRequest
    result = set_workspace_root(WorkspaceSetRootRequest(path=req.path, name=req.name), user)
    return result["project"]


@router.post("/{project_id}/activate")
def activate_project(project_id: str, user: AuthenticatedUser = Depends(require_role(UserRole.DEVELOPER))):
    project = ProjectService.get(project_id, user.user_id)
    return connect_project(ConnectProject(path=project["workspace_path"], name=project["name"]), user)


@router.get("/{project_id}/conversations")
def conversations(project_id: str, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                  user: AuthenticatedUser = Depends(get_current_user)):
    return ProjectService.conversations(project_id, user.user_id, limit, offset)


@router.get("/{project_id}/conversations/{conversation_id}/tasks")
def conversation_tasks(project_id: str, conversation_id: str, limit: int = Query(50, ge=1, le=100),
                       offset: int = Query(0, ge=0), user: AuthenticatedUser = Depends(get_current_user)):
    from backend.app.api.routes.v1 import get_task
    return [get_task(task.task_id, user) for task in
            ProjectService.tasks(project_id, conversation_id, user.user_id, limit, offset) if task]
