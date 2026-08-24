"""
AgentOS Phase 6 & 14 — Hardened Authentication & RBAC Service.

Implements:
- Session expiration and sliding window refresh
- Instant token blacklisting on logout
- Brute-force lockout (5 failed attempts -> 15 min lock)
- Constant-time verification
- Backend RBAC verification
"""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Set
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
    email: Optional[str] = None
    role: UserRole
    api_key_id: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    expires_at: float = Field(default_factory=lambda: time.time() + 3600)


class UserCredentials(BaseModel):
    user_id: str
    email: str
    username: str
    password_hash: str
    role: UserRole


class AuthService:
    """Manages secure sessions, lockout policies, and RBAC authorization."""

    _users_by_hash: Dict[str, AuthenticatedUser] = {}
    _credentials_by_email: Dict[str, UserCredentials] = {}
    _revoked_tokens: Set[str] = set()
    _failed_login_attempts: Dict[str, List[float]] = {}  # email -> list of attempt timestamps

    SESSION_TTL_SECONDS = 3600  # 1 hour
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_SECONDS = 900  # 15 min

    @classmethod
    def hash_password(cls, password: str) -> str:
        salt = settings.API_KEY_SALT.encode("utf-8")
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000).hex()

    @classmethod
    def verify_password(cls, password: str, hashed: str) -> bool:
        computed = cls.hash_password(password)
        return hmac.compare_digest(computed, hashed)

    @classmethod
    def hash_api_key(cls, raw_key: str) -> str:
        return hmac.new(
            settings.API_KEY_SALT.encode("utf-8"),
            raw_key.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @classmethod
    def is_locked_out(cls, email: str) -> bool:
        """Check if account is temporarily locked out due to brute force attempts."""
        attempts = cls._failed_login_attempts.get(email.lower(), [])
        now = time.time()
        recent = [t for t in attempts if now - t < cls.LOCKOUT_SECONDS]
        cls._failed_login_attempts[email.lower()] = recent
        return len(recent) >= cls.MAX_FAILED_ATTEMPTS

    @classmethod
    def record_failed_login(cls, email: str) -> None:
        if email.lower() not in cls._failed_login_attempts:
            cls._failed_login_attempts[email.lower()] = []
        cls._failed_login_attempts[email.lower()].append(time.time())

    @classmethod
    def clear_failed_logins(cls, email: str) -> None:
        cls._failed_login_attempts.pop(email.lower(), None)

    @classmethod
    def register_key(cls, raw_key: str, user: AuthenticatedUser) -> str:
        hashed = cls.hash_api_key(raw_key)
        cls._users_by_hash[hashed] = user
        return hashed

    @classmethod
    def register_user(cls, email: str, username: str, password: str, role: UserRole) -> UserCredentials:
        user_id = f"u-{hashlib.sha256(email.encode()).hexdigest()[:8]}"
        pwd_hash = cls.hash_password(password)
        creds = UserCredentials(
            user_id=user_id,
            email=email.lower(),
            username=username,
            password_hash=pwd_hash,
            role=role,
        )
        cls._credentials_by_email[email.lower()] = creds
        return creds

    @classmethod
    def authenticate_credentials(cls, email: str, password: str) -> Optional[tuple[AuthenticatedUser, str]]:
        if cls.is_locked_out(email):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Account temporarily locked out due to multiple failed login attempts. Try again later.",
            )

        creds = cls._credentials_by_email.get(email.lower())
        if not creds or not cls.verify_password(password, creds.password_hash):
            cls.record_failed_login(email)
            return None

        cls.clear_failed_logins(email)

        # Generate unique timestamped session token
        now = time.time()
        token = f"agentos-sess-{creds.user_id}-{hashlib.sha256((creds.email + str(now) + settings.API_KEY_SALT).encode()).hexdigest()[:24]}"
        auth_user = AuthenticatedUser(
            user_id=creds.user_id,
            username=creds.username,
            email=creds.email,
            role=creds.role,
            created_at=now,
            expires_at=now + cls.SESSION_TTL_SECONDS,
        )
        cls.register_key(token, auth_user)
        return auth_user, token

    @classmethod
    def authenticate_key(cls, raw_key: str) -> Optional[AuthenticatedUser]:
        if raw_key in cls._revoked_tokens:
            return None

        hashed = cls.hash_api_key(raw_key)
        user = cls._users_by_hash.get(hashed)
        if not user:
            return None

        # Check expiration
        now = time.time()
        if user.expires_at < now:
            cls._users_by_hash.pop(hashed, None)
            return None

        # Sliding window refresh
        user.expires_at = now + cls.SESSION_TTL_SECONDS
        return user

    @classmethod
    def revoke_token(cls, raw_key: str) -> bool:
        """Instantly revoke token on logout."""
        cls._revoked_tokens.add(raw_key)
        hashed = cls.hash_api_key(raw_key)
        cls._users_by_hash.pop(hashed, None)
        return True

    @classmethod
    def reset(cls) -> None:
        cls._users_by_hash.clear()
        cls._credentials_by_email.clear()
        cls._revoked_tokens.clear()
        cls._failed_login_attempts.clear()
        cls._setup_defaults()

    @classmethod
    def _setup_defaults(cls) -> None:
        # Default test API keys
        now = time.time()
        far_future = now + 86400 * 365
        cls.register_key("test-admin-key", AuthenticatedUser(user_id="u-admin", username="admin", email="admin@agentos.local", role=UserRole.ADMIN, expires_at=far_future))
        cls.register_key("test-dev-key", AuthenticatedUser(user_id="u-dev", username="developer", email="azhar@agentos.local", role=UserRole.DEVELOPER, expires_at=far_future))
        cls.register_key("test-user-key", AuthenticatedUser(user_id="u-user", username="user", email="user@agentos.local", role=UserRole.USER, expires_at=far_future))
        cls.register_key("test-viewer-key", AuthenticatedUser(user_id="u-viewer", username="viewer", email="viewer@agentos.local", role=UserRole.VIEWER, expires_at=far_future))

        # Default users for real login flow
        cls.register_user("admin@agentos.local", "Admin", "admin123", UserRole.ADMIN)
        cls.register_user("azhar@agentos.local", "Azhar Ali", "agentos123", UserRole.USER)
        cls.register_user("user@agentos.local", "Developer User", "user123", UserRole.USER)


AuthService.reset()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_current_user(
    api_key: Optional[str] = Security(api_key_header),
    authorization: Optional[str] = Header(default=None),
) -> AuthenticatedUser:
    """FastAPI dependency enforcing authentication."""
    if not settings.AUTH_ENABLED:
        return AuthenticatedUser(user_id="dev-default", username="dev_user", email="azhar@agentos.local", role=UserRole.DEVELOPER)

    token = api_key
    if not token and authorization:
        if authorization.startswith("Bearer "):
            token = authorization.split(" ", 1)[1]
        else:
            token = authorization

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required authentication token",
        )

    user = AuthService.authenticate_key(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token",
        )
    return user


def require_role(min_role: UserRole):
    """Dependency factory ensuring backend RBAC hierarchy."""
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
