from backend.app.models.agent import AgentState
from backend.app.tools.executor import ToolExecutor
from backend.app.models.tool import ToolRequest

class ExecutorAgent:
    def execute_step(self, state: AgentState, request: ToolRequest) -> dict:
        # Passes the formal ToolRequest directly to the central ToolExecutor
        # ToolExecutor handles Registry mapping + Security Risk Engine evaluation
        result = ToolExecutor.execute(request, task_id=state.task_id)
        
        return {
            "tool_name": result.tool_name,
            "success": result.success,
            "data": result.data,
            "error": result.error
        }
