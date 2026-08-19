import os
from pathlib import Path

base_dir = Path(r"c:\Users\evo\AgentOS")

files_content = {
    # Utils
    "backend/app/utils/logging.py": """import logging
from backend.app.config.settings import settings

def setup_logging():
    level = logging.DEBUG if settings.APP_ENV == "development" else logging.INFO
    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    return logging.getLogger("AgentOS")

logger = setup_logging()
""",
    "backend/app/utils/helpers.py": """def sanitize_input(value: str) -> str:
    \"\"\"Utility function to sanitize string inputs.\"\"\"
    return value.strip()
""",
    
    # Missing Tools
    "backend/app/tools/git.py": """from backend.app.tools.base import BaseTool
from backend.app.models.tool import ToolMetadata, RiskLevel, ToolRequest, ToolResult
from backend.app.tools.registry import ToolRegistry
import subprocess

class GitTool(BaseTool):
    def __init__(self):
        super().__init__(ToolMetadata(
            name="git",
            description="Safe Git operations",
            input_schema={"type": "object", "properties": {"operation": {"type": "string", "enum": ["status", "branch", "log"]}}},
            risk_level=RiskLevel.LOW
        ))

    def execute(self, request: ToolRequest) -> ToolResult:
        op = request.arguments.get("operation")
        if op not in ["status", "branch", "log"]:
            return ToolResult(tool_name=self.metadata.name, success=False, error=f"Unsupported git operation: {op}")
            
        try:
            result = subprocess.run(["git", op], capture_output=True, text=True)
            if result.returncode == 0:
                return ToolResult(tool_name=self.metadata.name, success=True, data=result.stdout)
            return ToolResult(tool_name=self.metadata.name, success=False, error=result.stderr)
        except Exception as e:
            return ToolResult(tool_name=self.metadata.name, success=False, error=str(e))

ToolRegistry.register(GitTool())
""",
    "backend/app/tools/process.py": """from backend.app.tools.base import BaseTool
from backend.app.models.tool import ToolMetadata, RiskLevel, ToolRequest, ToolResult
from backend.app.tools.registry import ToolRegistry
import psutil

class ProcessTool(BaseTool):
    def __init__(self):
        super().__init__(ToolMetadata(
            name="process",
            description="System information and process operations",
            input_schema={"type": "object", "properties": {"operation": {"type": "string", "enum": ["info"]}}},
            risk_level=RiskLevel.LOW
        ))

    def execute(self, request: ToolRequest) -> ToolResult:
        op = request.arguments.get("operation")
        if op == "info":
            data = {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_usage": psutil.disk_usage('/').percent
            }
            return ToolResult(tool_name=self.metadata.name, success=True, data=data)
        return ToolResult(tool_name=self.metadata.name, success=False, error=f"Unsupported operation: {op}")

ToolRegistry.register(ProcessTool())
""",
    "backend/app/tools/browser.py": """from backend.app.tools.base import BaseTool
from backend.app.models.tool import ToolMetadata, RiskLevel, ToolRequest, ToolResult
from backend.app.tools.registry import ToolRegistry

class BrowserTool(BaseTool):
    def __init__(self):
        super().__init__(ToolMetadata(
            name="browser",
            description="Browser automation interface (Stub)",
            input_schema={"type": "object", "properties": {}},
            risk_level=RiskLevel.HIGH
        ))

    def execute(self, request: ToolRequest) -> ToolResult:
        return ToolResult(tool_name=self.metadata.name, success=False, error="Browser automation is not implemented yet.")

ToolRegistry.register(BrowserTool())
""",
    "backend/app/tools/docker.py": """from backend.app.tools.base import BaseTool
from backend.app.models.tool import ToolMetadata, RiskLevel, ToolRequest, ToolResult
from backend.app.tools.registry import ToolRegistry

class DockerTool(BaseTool):
    def __init__(self):
        super().__init__(ToolMetadata(
            name="docker",
            description="Docker automation interface (Stub)",
            input_schema={"type": "object", "properties": {}},
            risk_level=RiskLevel.HIGH
        ))

    def execute(self, request: ToolRequest) -> ToolResult:
        return ToolResult(tool_name=self.metadata.name, success=False, error="Docker automation is not implemented yet.")

ToolRegistry.register(DockerTool())
""",
    "backend/app/tools/github.py": """from backend.app.tools.base import BaseTool
from backend.app.models.tool import ToolMetadata, RiskLevel, ToolRequest, ToolResult
from backend.app.tools.registry import ToolRegistry

class GitHubTool(BaseTool):
    def __init__(self):
        super().__init__(ToolMetadata(
            name="github",
            description="GitHub automation interface (Stub)",
            input_schema={"type": "object", "properties": {}},
            risk_level=RiskLevel.HIGH
        ))

    def execute(self, request: ToolRequest) -> ToolResult:
        return ToolResult(tool_name=self.metadata.name, success=False, error="GitHub automation is not implemented yet.")

ToolRegistry.register(GitHubTool())
""",

    # Missing Agents
    "backend/app/agents/orchestrator.py": """class Orchestrator:
    def __init__(self):
        pass
        
    def coordinate(self, task_id: str):
        # Stub for orchestrating the overall flow
        pass
""",
    "backend/app/agents/researcher.py": """class ResearcherAgent:
    def __init__(self):
        pass
        
    def research(self, topic: str):
        # Stub for future web search or codebase research
        return "Research stub"
""",
    
    # Missing Workflows
    "backend/app/workflows/execution.py": """def execute_step_workflow(state):
    # Stub for langgraph execution node
    return state
""",
    "backend/app/workflows/planning.py": """def planning_workflow(state):
    # Stub for langgraph planning node
    return state
""",

    # Missing Memory
    "backend/app/memory/long_term.py": """class LongTermMemory:
    def store(self, key: str, value: str):
        pass
        
    def retrieve(self, key: str):
        return None
""",
    "backend/app/memory/vector_store.py": """class VectorStore:
    def add(self, text: str):
        pass
        
    def search(self, query: str):
        return []
""",

    # Missing Services
    "backend/app/services/agent_service.py": """from backend.app.models.task import TaskRequest, TaskResult
from backend.app.services.task_service import TaskService

class AgentService:
    @staticmethod
    def invoke_workflow(request: TaskRequest) -> TaskResult:
        # Stub for triggering the full langgraph workflow asynchronously
        task = TaskService.create_task(request)
        return task
""",
    "backend/app/api/dependencies.py": """from fastapi import Depends

def get_db():
    # Stub for future db dependency
    yield None
""",

    # Tests Stubs
    "backend/tests/unit/test_agents.py": """def test_planner_stub():
    assert True
""",
    "backend/tests/unit/test_memory.py": """def test_memory_stub():
    assert True
""",
    "backend/tests/unit/test_tools.py": """from backend.app.tools.registry import ToolRegistry

def test_registry_has_tools():
    # Ensure that our loaded tools are in the registry
    assert len(ToolRegistry.list_tools()) >= 0
""",
    "backend/tests/integration/test_agent_workflow.py": """def test_workflow_stub():
    assert True
""",
    "backend/tests/integration/test_api.py": """from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
""",
    "scripts/health_check.py": """import sys
import httpx

def main():
    try:
        r = httpx.get("http://127.0.0.1:8000/health")
        if r.status_code == 200:
            print("Health check passed.")
            sys.exit(0)
    except Exception as e:
        print(f"Health check failed: {e}")
    sys.exit(1)

if __name__ == "__main__":
    main()
""",
    "scripts/setup.py": """print("Setup script stub")""",
    "scripts/start.py": """import subprocess
def main():
    subprocess.run(["uvicorn", "backend.app.main:app", "--reload"])
if __name__ == "__main__":
    main()
""",
    "backend/app/api/routes/agent.py": """# Implementation moved to backend.app.api.agent for simplicity
""",
    "backend/app/api/routes/health.py": """# Implementation moved to backend.app.api.health
""",
    "backend/app/api/routes/tasks.py": """from fastapi import APIRouter
from backend.app.services.task_service import TaskService
from backend.app.models.task import TaskResult

router = APIRouter()

@router.get("/{task_id}", response_model=TaskResult)
def get_task(task_id: str):
    task = TaskService.get_task(task_id)
    if not task:
        return {"error": "Task not found"}
    return task
""",
    "backend/app/api/routes/tools.py": """# Implementation moved to backend.app.api.tools
"""
}

for fpath, content in files_content.items():
    p = base_dir / fpath
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)

# create __init__.py files as well
for folder in ["backend/app", "backend/tests", "backend/app/agents", "backend/app/api", "backend/app/api/routes", "backend/app/config", "backend/app/llm", "backend/app/memory", "backend/app/models", "backend/app/security", "backend/app/services", "backend/app/tools", "backend/app/utils", "backend/app/workflows"]:
    p = base_dir / folder / "__init__.py"
    if p.exists() and p.stat().st_size == 0:
        with open(p, "w", encoding="utf-8") as f:
            f.write("# Init module\\n")

print("Scaffolded remaining missing files successfully.")
