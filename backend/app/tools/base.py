from abc import ABC, abstractmethod
from backend.app.models.tool import ToolRequest, ToolResult, ToolMetadata
from typing import Any

class BaseTool(ABC):
    def __init__(self, metadata: ToolMetadata):
        self.metadata = metadata

    @abstractmethod
    def execute(self, request: ToolRequest) -> ToolResult:
        pass
