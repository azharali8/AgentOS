from backend.app.tools.base import BaseTool
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
