"""
Standardized error codes and exceptions for AgentOS Phase 2.
"""

from enum import Enum
from typing import Optional, Any, Dict


class ErrorCategory(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    SECURITY_ERROR = "SECURITY_ERROR"
    APPROVAL_ERROR = "APPROVAL_ERROR"
    TOOL_ERROR = "TOOL_ERROR"
    LLM_ERROR = "LLM_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    CANCELLATION_ERROR = "CANCELLATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AgentOSError(Exception):
    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.INTERNAL_ERROR,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.message,
            "category": self.category.value,
            "details": self.details,
        }
