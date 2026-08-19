from pydantic import BaseModel, Field
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
