from typing import Dict, Type
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
    def get(cls, name: str) -> 'BaseTool':
        return cls.get_tool(name)

    @classmethod
    def list_tools(cls) -> list[ToolMetadata]:
        return [tool.metadata for tool in cls._tools.values()]
