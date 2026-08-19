import os
from pathlib import Path

base_dir = Path(r"c:\Users\evo\AgentOS")

files_content = {
    "backend/app/models/task.py": """from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime
from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class TaskRequest(BaseModel):
    instruction: str

class TaskResult(BaseModel):
    task_id: str
    status: TaskStatus
    final_response: Optional[str] = None
    error: Optional[str] = None
""",
    "backend/app/models/agent.py": """from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class AgentState(BaseModel):
    task_id: str
    instruction: str
    plan: Optional[Dict[str, Any]] = None
    current_step: Optional[int] = None
    tool_requests: List[Dict[str, Any]] = Field(default_factory=list)
    tool_results: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    status: str = "PENDING"
    final_response: Optional[str] = None

class AgentResponse(BaseModel):
    state: AgentState
""",
    "backend/app/models/tool.py": """from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from enum import Enum

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class ToolRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]

class ToolResult(BaseModel):
    tool_name: str
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None

class ToolMetadata(BaseModel):
    name: str
    description: str
    input_schema: Dict[str, Any]
    risk_level: RiskLevel
    supported_os: list[str] = Field(default_factory=lambda: ["windows", "linux", "macos"])
""",
    "backend/app/models/approval.py": """from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum
from backend.app.models.tool import RiskLevel

class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

class ApprovalRequest(BaseModel):
    approval_id: str
    task_id: str
    tool_name: str
    operation: str
    arguments_summary: Dict[str, Any]
    risk_level: RiskLevel
    reason: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = datetime.utcnow()

class ApprovalResponse(BaseModel):
    approval_id: str
    status: ApprovalStatus
    reason: Optional[str] = None
""",
    "backend/app/security/risk.py": """from backend.app.models.tool import RiskLevel
""",
    "backend/app/security/policies.py": """from backend.app.models.tool import RiskLevel

DEFAULT_POLICIES = {
    "filesystem.read": RiskLevel.LOW,
    "filesystem.list": RiskLevel.LOW,
    "filesystem.create": RiskLevel.MEDIUM,
    "terminal.execute": RiskLevel.MEDIUM,
    "git.status": RiskLevel.LOW,
    "git.branch": RiskLevel.LOW,
    "git.log": RiskLevel.LOW,
    "process.info": RiskLevel.LOW,
}

def get_policy(tool_name: str, operation: str) -> RiskLevel:
    key = f"{tool_name}.{operation}"
    return DEFAULT_POLICIES.get(key, RiskLevel.CRITICAL) # Default to CRITICAL if unknown
""",
    "backend/app/security/permissions.py": """from backend.app.models.tool import RiskLevel
from backend.app.security.policies import get_policy
from backend.app.config.settings import settings

class SecurityManager:
    @staticmethod
    def requires_approval(tool_name: str, operation: str) -> bool:
        if not settings.REQUIRE_APPROVAL_FOR_DANGEROUS_ACTIONS:
            return False
            
        risk = get_policy(tool_name, operation)
        return risk in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        
    @staticmethod
    def is_allowed(tool_name: str, operation: str) -> bool:
        # For now, everything not CRITICAL is "allowed" to be attempted, but might need approval.
        # Unknown operations default to CRITICAL and thus will be strictly controlled.
        risk = get_policy(tool_name, operation)
        if risk == RiskLevel.CRITICAL:
            return False # Deny completely
        return True
""",
    "backend/app/security/approval.py": """from backend.app.models.approval import ApprovalRequest, ApprovalStatus
from typing import Dict
import uuid

class ApprovalManager:
    _approvals: Dict[str, ApprovalRequest] = {}

    @classmethod
    def request_approval(cls, request: ApprovalRequest) -> str:
        cls._approvals[request.approval_id] = request
        return request.approval_id
        
    @classmethod
    def get_approval(cls, approval_id: str) -> ApprovalRequest:
        return cls._approvals.get(approval_id)

    @classmethod
    def resolve_approval(cls, approval_id: str, status: ApprovalStatus, reason: str = "") -> bool:
        if approval_id in cls._approvals:
            cls._approvals[approval_id].status = status
            cls._approvals[approval_id].reason = reason
            return True
        return False
""",
    "backend/app/services/workspace_service.py": """import os
from pathlib import Path
from backend.app.config.settings import settings

class WorkspaceService:
    @staticmethod
    def get_workspace_root() -> Path:
        return Path(settings.WORKSPACE_ROOT).resolve()

    @staticmethod
    def validate_path(requested_path: str) -> Path:
        root = WorkspaceService.get_workspace_root()
        # Resolve the requested path relative to the workspace root if it's not absolute
        # If it is absolute, ensure it starts with the workspace root
        if not os.path.isabs(requested_path):
            target = (root / requested_path).resolve()
        else:
            target = Path(requested_path).resolve()
            
        try:
            target.relative_to(root)
        except ValueError:
            raise ValueError(f"Path traversal detected or path outside workspace: {requested_path}")
            
        return target
""",
    "backend/app/tools/registry.py": """from typing import Dict, Type
from backend.app.models.tool import ToolMetadata

class ToolRegistry:
    _tools: Dict[str, 'BaseTool'] = {}

    @classmethod
    def register(cls, tool_instance: 'BaseTool'):
        cls._tools[tool_instance.metadata.name] = tool_instance

    @classmethod
    def get_tool(cls, name: str) -> 'BaseTool':
        return cls._tools.get(name)

    @classmethod
    def list_tools(cls) -> list[ToolMetadata]:
        return [tool.metadata for tool in cls._tools.values()]
""",
    "backend/app/tools/base.py": """from abc import ABC, abstractmethod
from backend.app.models.tool import ToolRequest, ToolResult, ToolMetadata
from typing import Any

class BaseTool(ABC):
    def __init__(self, metadata: ToolMetadata):
        self.metadata = metadata

    @abstractmethod
    def execute(self, request: ToolRequest) -> ToolResult:
        pass
""",
    "backend/app/tools/executor.py": """from backend.app.models.tool import ToolRequest, ToolResult
from backend.app.tools.registry import ToolRegistry
from backend.app.security.permissions import SecurityManager
from backend.app.security.approval import ApprovalManager
from backend.app.models.approval import ApprovalRequest, ApprovalStatus
from backend.app.models.tool import RiskLevel
from backend.app.security.policies import get_policy
import uuid
import time

class ToolExecutor:
    @staticmethod
    def execute(request: ToolRequest, task_id: str) -> ToolResult:
        tool = ToolRegistry.get_tool(request.tool_name)
        if not tool:
            return ToolResult(tool_name=request.tool_name, success=False, error="Tool not found in registry")
            
        operation = request.arguments.get('operation', 'default')
        
        if not SecurityManager.is_allowed(request.tool_name, operation):
            return ToolResult(tool_name=request.tool_name, success=False, error="Security: Operation DENIED by policy")
            
        if SecurityManager.requires_approval(request.tool_name, operation):
            approval_id = str(uuid.uuid4())
            app_req = ApprovalRequest(
                approval_id=approval_id,
                task_id=task_id,
                tool_name=request.tool_name,
                operation=operation,
                arguments_summary=request.arguments,
                risk_level=get_policy(request.tool_name, operation),
                reason="Requires approval"
            )
            ApprovalManager.request_approval(app_req)
            return ToolResult(tool_name=request.tool_name, success=False, error=f"Requires approval. Approval ID: {approval_id}")

        try:
            return tool.execute(request)
        except Exception as e:
            return ToolResult(tool_name=request.tool_name, success=False, error=str(e))
""",
    "backend/app/tools/filesystem.py": """from backend.app.tools.base import BaseTool
from backend.app.models.tool import ToolMetadata, RiskLevel, ToolRequest, ToolResult
from backend.app.services.workspace_service import WorkspaceService
import os

class FilesystemTool(BaseTool):
    def __init__(self):
        super().__init__(ToolMetadata(
            name="filesystem",
            description="Perform filesystem operations",
            input_schema={"type": "object", "properties": {"operation": {"type": "string"}, "path": {"type": "string"}, "content": {"type": "string"}}},
            risk_level=RiskLevel.MEDIUM
        ))

    def execute(self, request: ToolRequest) -> ToolResult:
        op = request.arguments.get("operation")
        path_str = request.arguments.get("path")
        
        if not op or not path_str:
            return ToolResult(tool_name=self.metadata.name, success=False, error="Missing operation or path")
            
        try:
            target_path = WorkspaceService.validate_path(path_str)
        except ValueError as e:
            return ToolResult(tool_name=self.metadata.name, success=False, error=str(e))
            
        try:
            if op == "read":
                with open(target_path, 'r') as f:
                    return ToolResult(tool_name=self.metadata.name, success=True, data=f.read())
            elif op == "list":
                items = os.listdir(target_path)
                return ToolResult(tool_name=self.metadata.name, success=True, data=items)
            elif op == "create":
                content = request.arguments.get("content", "")
                with open(target_path, 'w') as f:
                    f.write(content)
                return ToolResult(tool_name=self.metadata.name, success=True, data="File created")
            else:
                return ToolResult(tool_name=self.metadata.name, success=False, error=f"Unknown operation: {op}")
        except Exception as e:
            return ToolResult(tool_name=self.metadata.name, success=False, error=str(e))

from backend.app.tools.registry import ToolRegistry
ToolRegistry.register(FilesystemTool())
""",
    "backend/app/tools/terminal.py": """from backend.app.tools.base import BaseTool
from backend.app.models.tool import ToolMetadata, RiskLevel, ToolRequest, ToolResult
import subprocess
import platform

class TerminalTool(BaseTool):
    def __init__(self):
        super().__init__(ToolMetadata(
            name="terminal",
            description="Execute basic terminal commands safely",
            input_schema={"type": "object", "properties": {"operation": {"type": "string", "enum": ["execute"]}, "command": {"type": "string"}}},
            risk_level=RiskLevel.MEDIUM
        ))
        
    def execute(self, request: ToolRequest) -> ToolResult:
        command = request.arguments.get("command", "")
        if not command:
            return ToolResult(tool_name=self.metadata.name, success=False, error="Missing command")
            
        allowlist = ["echo", "whoami", "dir", "ls", "pwd"]
        cmd_base = command.split(" ")[0]
        if cmd_base not in allowlist:
            return ToolResult(tool_name=self.metadata.name, success=False, error=f"Command {cmd_base} not in allowlist")
            
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                return ToolResult(tool_name=self.metadata.name, success=True, data=result.stdout)
            else:
                return ToolResult(tool_name=self.metadata.name, success=False, error=result.stderr)
        except Exception as e:
            return ToolResult(tool_name=self.metadata.name, success=False, error=str(e))

from backend.app.tools.registry import ToolRegistry
ToolRegistry.register(TerminalTool())
""",
    "backend/app/api/health.py": """from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
def health_check():
    return {"status": "ok"}
""",
    "backend/app/api/tools.py": """from fastapi import APIRouter
from backend.app.tools.registry import ToolRegistry

router = APIRouter()

@router.get("/tools")
def list_tools():
    return {"tools": [t.dict() for t in ToolRegistry.list_tools()]}
""",
    "backend/app/main.py": """from fastapi import FastAPI
from backend.app.api.health import router as health_router
from backend.app.api.tools import router as tools_router
import backend.app.tools.filesystem  # trigger registration
import backend.app.tools.terminal  # trigger registration

app = FastAPI(title="AgentOS")

app.include_router(health_router)
app.include_router(tools_router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "AgentOS is running"}
"""
}

for fpath, content in files_content.items():
    p = base_dir / fpath
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)

print("Scaffolded python files successfully.")
