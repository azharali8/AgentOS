"""
AgentOS Phase 9 — Python SDK Exception Hierarchy.
"""

from typing import Optional


class AgentOSError(Exception):
    """Base exception for all AgentOS SDK errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[dict] = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class AuthenticationError(AgentOSError):
    """Raised when API key or token authentication fails."""


class AuthorizationError(AgentOSError):
    """Raised when user permissions or roles are insufficient for the requested resource/agent."""


class ValidationError(AgentOSError):
    """Raised when request payload fails validation."""


class NotFoundError(AgentOSError):
    """Raised when the requested task, agent, or resource cannot be found."""


class RateLimitError(AgentOSError):
    """Raised when the client exceeds rate limits."""


class TaskExecutionError(AgentOSError):
    """Raised when task execution fails or encounters a terminal state."""


class ServerError(AgentOSError):
    """Raised when AgentOS backend returns an unexpected 5xx status code."""


class TimeoutError(AgentOSError):
    """Raised when a task or streaming operation times out."""
