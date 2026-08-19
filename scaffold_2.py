import os
from pathlib import Path

base_dir = Path(r"c:\Users\evo\AgentOS")

files_content = {
    "backend/app/llm/base.py": """from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseLLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        pass
        
    @abstractmethod
    def generate_chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        pass
""",
    "backend/app/llm/factory.py": """from backend.app.config.settings import settings
from backend.app.llm.base import BaseLLMProvider

def get_llm_provider() -> BaseLLMProvider:
    provider_name = settings.LLM_PROVIDER.lower()
    if provider_name == "ollama":
        from backend.app.llm.ollama import OllamaProvider
        return OllamaProvider()
    elif provider_name == "openai":
        from backend.app.llm.openai_compatible import OpenAICompatibleProvider
        return OpenAICompatibleProvider()
    elif provider_name == "colab":
        from backend.app.llm.colab import ColabProvider
        return ColabProvider()
    else:
        raise ValueError(f"Unknown LLM provider: {provider_name}")
""",
    "backend/app/llm/ollama.py": """from backend.app.llm.base import BaseLLMProvider
from backend.app.config.settings import settings
from typing import List, Dict
import httpx

class OllamaProvider(BaseLLMProvider):
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL
        
    def generate(self, prompt: str, **kwargs) -> str:
        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False}
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except httpx.RequestError as e:
            return f"Error connecting to Ollama: {str(e)}"
            
    def generate_chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        # Simplistic implementation for chat
        prompt = "\\n".join([f"{m['role']}: {m['content']}" for m in messages])
        return self.generate(prompt)
""",
    "backend/app/llm/openai_compatible.py": """from backend.app.llm.base import BaseLLMProvider
from typing import List, Dict

class OpenAICompatibleProvider(BaseLLMProvider):
    def generate(self, prompt: str, **kwargs) -> str:
        return "OpenAI Provider Stub - Generate"
        
    def generate_chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        return "OpenAI Provider Stub - Chat"
""",
    "backend/app/llm/colab.py": """from backend.app.llm.base import BaseLLMProvider
from typing import List, Dict

class ColabProvider(BaseLLMProvider):
    def generate(self, prompt: str, **kwargs) -> str:
        return "Colab Provider Stub - Generate"
        
    def generate_chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        return "Colab Provider Stub - Chat"
""",
    "backend/app/memory/short_term.py": """from typing import Dict, Any

class ShortTermMemory:
    def __init__(self):
        self.state: Dict[str, Any] = {}
        
    def get(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)
        
    def set(self, key: str, value: Any):
        self.state[key] = value
        
    def clear(self):
        self.state.clear()
""",
    "backend/app/memory/conversation.py": """from typing import List, Dict

class ConversationMemory:
    def __init__(self):
        self.messages: List[Dict[str, str]] = []
        
    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        
    def get_messages(self) -> List[Dict[str, str]]:
        return self.messages
""",
    "backend/app/agents/planner.py": """from backend.app.models.agent import AgentState
from typing import Dict, Any
import json

class Planner:
    def __init__(self, llm):
        self.llm = llm
        
    def plan(self, state: AgentState) -> Dict[str, Any]:
        # Simple mock planning for the foundation
        # A real implementation would ask the LLM to return a JSON plan based on tools
        mock_plan = {
            "goal": state.instruction,
            "steps": [
                {"id": 1, "description": "Identify initial files", "tool": "filesystem", "operation": "list"}
            ]
        }
        return mock_plan
""",
    "backend/app/agents/executor.py": """from backend.app.models.agent import AgentState
from backend.app.tools.executor import ToolExecutor
from backend.app.models.tool import ToolRequest

class ExecutorAgent:
    def execute_step(self, state: AgentState, step_details: dict) -> dict:
        # Mock mapping step details to tool request
        tool_name = step_details.get("tool")
        operation = step_details.get("operation")
        
        req = ToolRequest(
            tool_name=tool_name,
            arguments={"operation": operation, "path": "."}
        )
        
        result = ToolExecutor.execute(req, task_id=state.task_id)
        
        return {
            "tool_name": result.tool_name,
            "success": result.success,
            "data": result.data,
            "error": result.error
        }
""",
    "backend/app/agents/reviewer.py": """class ReviewerAgent:
    def review(self, execution_result: dict) -> str:
        if execution_result.get("success"):
            return "SUCCESS"
        else:
            return "RETRYABLE_ERROR" if "Requires approval" not in execution_result.get("error", "") else "FATAL_ERROR"
""",
    "backend/app/workflows/task_graph.py": """# Minimal stub for task graph setup
from backend.app.models.agent import AgentState

def create_task_graph():
    # In a real LangGraph setup, we define edges and nodes here
    pass
""",
    "backend/app/services/task_service.py": """from backend.app.models.task import TaskRequest, TaskResult, TaskStatus
import uuid
from typing import Dict

class TaskService:
    _tasks: Dict[str, TaskResult] = {}
    
    @classmethod
    def create_task(cls, request: TaskRequest) -> TaskResult:
        task_id = str(uuid.uuid4())
        task = TaskResult(task_id=task_id, status=TaskStatus.PENDING)
        cls._tasks[task_id] = task
        return task
        
    @classmethod
    def get_task(cls, task_id: str) -> TaskResult:
        return cls._tasks.get(task_id)
        
    @classmethod
    def update_task_status(cls, task_id: str, status: TaskStatus):
        if task_id in cls._tasks:
            cls._tasks[task_id].status = status
""",
    "backend/app/api/agent.py": """from fastapi import APIRouter
from backend.app.models.task import TaskRequest, TaskResult, TaskStatus
from backend.app.services.task_service import TaskService
from backend.app.models.agent import AgentState
from backend.app.agents.planner import Planner
from backend.app.llm.factory import get_llm_provider
from backend.app.agents.executor import ExecutorAgent

router = APIRouter()

@router.post("/agent/run", response_model=TaskResult)
def run_agent(request: TaskRequest):
    # Synchronous mock run for foundation
    task = TaskService.create_task(request)
    TaskService.update_task_status(task.task_id, TaskStatus.PLANNING)
    
    llm = get_llm_provider()
    planner = Planner(llm)
    executor = ExecutorAgent()
    
    state = AgentState(task_id=task.task_id, instruction=request.instruction)
    plan = planner.plan(state)
    state.plan = plan
    
    TaskService.update_task_status(task.task_id, TaskStatus.EXECUTING)
    
    # Execute first step only for foundational mock
    if plan["steps"]:
        res = executor.execute_step(state, plan["steps"][0])
        if res["success"]:
            TaskService.update_task_status(task.task_id, TaskStatus.COMPLETED)
            task.final_response = str(res["data"])
        else:
            TaskService.update_task_status(task.task_id, TaskStatus.FAILED)
            task.error = res["error"]
            
    return task
"""
}

for fpath, content in files_content.items():
    p = base_dir / fpath
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)

print("Scaffolded LLM, Memory, Agents, Services successfully.")
