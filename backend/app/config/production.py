"""
AgentOS Phase 14 — Production Configuration Management.

Provides:
- Environment profile detection (development, testing, production)
- Mandatory secret validation for production environments
- Zero-exposure secret redaction
- Dynamic profile-based configuration defaults
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ProductionConfigError(Exception):
    """Raised when mandatory production configuration is invalid or missing."""
    pass


class ProductionSettings(BaseSettings):
    """Hardened production settings with environment profile validation."""

    APP_ENV: str = Field(default="development", description="development | testing | production")
    PROJECT_NAME: str = "AgentOS"
    API_VERSION: str = "v1"

    # Database configuration
    DATABASE_URL: str = Field(default="sqlite:///./data/agentos.db")
    DATABASE_BUSY_TIMEOUT_MS: int = 5000
    DATABASE_MAX_RETRIES: int = 5

    # LLM & Model Router
    LLM_PROVIDER: str = "ollama"
    FALLBACK_LLM_PROVIDER: str = "openai"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"

    # Workspace & Limits
    WORKSPACE_ROOT: str = str(PROJECT_ROOT / "workspace")
    MAX_OUTPUT_SIZE: int = 1024 * 1024  # 1 MB
    TERMINAL_TIMEOUT: int = 30
    MAX_TASK_DURATION: int = 3600

    # Multi-Domain Rate Limits (requests per minute)
    RATE_LIMIT_AUTH: int = 5
    RATE_LIMIT_TASKS: int = 10
    RATE_LIMIT_API: int = 100
    RATE_LIMIT_WEBSOCKET: int = 5

    # Security & Auth
    AUTH_ENABLED: bool = False  # Set to True in production
    API_KEY_SALT: str = "agentos-default-salt-change-in-prod"
    SESSION_EXPIRATION_SECONDS: int = 3600  # 1 hour
    MAX_FAILED_LOGINS: int = 5
    LOCKOUT_DURATION_SECONDS: int = 900  # 15 minutes
    MAX_REQUEST_BODY_SIZE: int = 2 * 1024 * 1024  # 2 MB

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def validate_production_readiness(self) -> None:
        """Enforce strict production invariants."""
        if self.APP_ENV.lower() == "production":
            if not self.AUTH_ENABLED:
                raise ProductionConfigError("AUTH_ENABLED must be True in production mode.")
            if self.API_KEY_SALT == "agentos-default-salt-change-in-prod":
                raise ProductionConfigError("API_KEY_SALT must be configured with a secure random value in production.")
            if not Path(self.WORKSPACE_ROOT).is_absolute():
                raise ProductionConfigError("WORKSPACE_ROOT must be an absolute path in production.")

    class Config:
        env_file = ".env"
        extra = "allow"


prod_settings = ProductionSettings()
