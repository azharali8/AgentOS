from backend.app.tools.base import BaseTool
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
