from backend.app.tools.base import BaseTool
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
