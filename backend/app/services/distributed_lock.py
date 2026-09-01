"""
AgentOS Phase 16 — Distributed Lock Service.
Implements Redis-backed atomic distributed locking with owner verification and Lua release.
"""


from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from backend.app.services.redis_client import get_redis_client, is_redis_available

logger = logging.getLogger("agentos.distributed_lock")

# Lua script to release lock atomically only if token matches owner
RELEASE_LOCK_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

# Lua script to extend lock atomically only if token matches owner
EXTEND_LOCK_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("pexpire", KEYS[1], ARGV[2])
else
    return 0
end
"""


class DistributedLock:
    """Atomic distributed locking backed by Redis with zero simulated state."""

    @classmethod
    def acquire(
        cls,
        lock_name: str,
        owner_id: str,
        ttl_seconds: int = 15,
        token: Optional[str] = None,
    ) -> Optional[str]:
        """
        Attempt to acquire distributed lock atomically.
        Returns lock_token (string) on success, None on failure.
        """
        if not is_redis_available():
            logger.warning("Redis unavailable: cannot acquire distributed lock '%s'", lock_name)
            return None

        lock_token = token or f"{owner_id}:{uuid.uuid4().hex[:12]}"
        key = f"agentos:lock:{lock_name}"
        ttl_ms = int(ttl_seconds * 1000)

        try:
            client = get_redis_client()
            acquired = client.set(key, lock_token, nx=True, px=ttl_ms)
            if acquired:
                logger.debug("Acquired lock '%s' for owner '%s' (token=%s)", lock_name, owner_id, lock_token)
                return lock_token
            return None
        except Exception as exc:
            logger.error("Error acquiring distributed lock '%s': %s", lock_name, exc)
            return None

    @classmethod
    def release(cls, lock_name: str, lock_token: str) -> bool:
        """
        Atomically release lock using Lua compare-and-delete.
        Returns True if released, False if token did not match or lock expired.
        """
        if not is_redis_available():
            return False

        key = f"agentos:lock:{lock_name}"
        try:
            client = get_redis_client()
            res = client.eval(RELEASE_LOCK_LUA, 1, key, lock_token)
            return bool(res == 1)
        except Exception as exc:
            logger.error("Error releasing distributed lock '%s': %s", lock_name, exc)
            return False

    @classmethod
    def extend(cls, lock_name: str, lock_token: str, ttl_seconds: int = 15) -> bool:
        """
        Atomically extend lease on held lock using Lua script.
        """
        if not is_redis_available():
            return False

        key = f"agentos:lock:{lock_name}"
        ttl_ms = int(ttl_seconds * 1000)
        try:
            client = get_redis_client()
            res = client.eval(EXTEND_LOCK_LUA, 1, key, lock_token, str(ttl_ms))
            return bool(res == 1)
        except Exception as exc:
            logger.error("Error extending distributed lock '%s': %s", lock_name, exc)
            return False

    @classmethod
    def is_locked(cls, lock_name: str) -> bool:
        """Check if lock currently exists."""
        if not is_redis_available():
            return False
        try:
            client = get_redis_client()
            return bool(client.exists(f"agentos:lock:{lock_name}"))
        except Exception:
            return False

    @classmethod
    def get_holder_token(cls, lock_name: str) -> Optional[str]:
        """Get currently stored token for inspection/debugging."""
        if not is_redis_available():
            return None
        try:
            client = get_redis_client()
            return client.get(f"agentos:lock:{lock_name}")
        except Exception:
            return None
