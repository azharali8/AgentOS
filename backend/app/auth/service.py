"""
AgentOS Phase 6 — Authentication & Role-Based Access Control (RBAC).

Provides:
- User roles: VIEWER, USER, DEVELOPER, ADMIN
- Cryptographic API Key hashing with salt
- FastAPI security dependencies
- Safe test bypass when AUTH_ENABLED=False
"""

from __future__ import annotations

import hashlib
import hmac
from enum import Enum
from typing import Dict, List, Optional
from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from backend.app.config.settings import settings


class UserRole(str, Enum):
    VIEWER = "viewer"
    USER = "user"
    DEVELOPER = "developer"
    ADMIN = "admin"


class AuthenticatedUser(BaseModel):
    user_id: str
    username: str
    role: UserRole
    api_key_id: Optional[str] = None


class AuthService:
    """Manages API keys and verifies RBAC permissions."""

    # In-memory API key store: key_hash -> AuthenticatedUser
    _users_by_hash: Dict[str, AuthenticatedUser] = {}

    @classmethod
    def hash_api_key(cls, raw_key: str) -> str:
        """Deterministic SHA-256 HMAC of raw API key using salt."""
        return hmac.new(
            settings.API_KEY_SALT.encode("utf-8"),
            raw_key.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @classmethod
    def register_key(cls, raw_key: str, user: AuthenticatedUser) -> str:
        """Register a new API key."""
        hashed = cls.hash_api_key(raw_key)
        cls._users_by_hash[hashed] = user
        return hashed

    @classmethod
    def authenticate_key(cls, raw_key: str) -> Optional[AuthenticatedUser]:
        """Validate raw key against stored hashes."""
        hashed = cls.hash_api_key(raw_key)
        return cls._users_by_hash.get(hashed)

    @classmethod
    def reset(cls) -> None:
        cls._users_by_hash.clear()
        cls._setup_defaults()

    @classmethod
    def _setup_defaults(cls) -> None:
        # Default test API keys
        cls.register_key("test-admin-key", AuthenticatedUser(user_id="u-admin", username="admin", role=UserRole.ADMIN))
        cls.register_key("test-dev-key", AuthenticatedUser(user_id="u-dev", username="developer", role=UserRole.DEVELOPER))
        cls.register_key("test-user-key", AuthenticatedUser(user_id="u-user", username="user", role=UserRole.USER))
        cls.register_key("test-viewer-key", AuthenticatedUser(user_id="u-viewer", username="viewer", role=UserRole.VIEWER))


AuthService.reset()

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_current_user(api_key: Optional[str] = Security(api_key_header)) -> AuthenticatedUser:
    """
    FastAPI dependency to authenticate requests.
    If settings.AUTH_ENABLED is False, returns a default DEVELOPER user for testing.
    """
    if not settings.AUTH_ENABLED:
        return AuthenticatedUser(user_id="dev-default", username="dev_user", role=UserRole.DEVELOPER)

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required X-API-Key header",
        )

    user = AuthService.authenticate_key(api_key)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API Key",
        )
    return user


def require_role(min_role: UserRole):
    """Dependency factory ensuring current user meets minimum role hierarchy."""
    role_hierarchy = {
        UserRole.VIEWER: 1,
        UserRole.USER: 2,
        UserRole.DEVELOPER: 3,
        UserRole.ADMIN: 4,
    }

    def _role_checker(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if role_hierarchy.get(user.role, 0) < role_hierarchy.get(min_role, 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: requires {min_role.value} role or higher",
            )
        return user

    return _role_checker
