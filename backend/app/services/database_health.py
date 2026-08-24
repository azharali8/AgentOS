"""
AgentOS Phase 14 — Database Hardening & Health Service.

Provides:
- SQLite busy-timeout retry handling with exponential backoff
- Startup integrity verification via PRAGMA integrity_check
- Database health, connection latency, and migration status probing
"""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar
from pydantic import BaseModel

from backend.app.config.settings import settings
from backend.app.db.database import engine, get_db_session

logger = logging.getLogger("agentos.db_health")

T = TypeVar("T")


class DatabaseHealthStatus(BaseModel):
    status: str  # HEALTHY, DEGRADED, UNHEALTHY
    latency_ms: float
    integrity: str  # ok, failed, unknown
    db_path: str
    total_tables: int
    error: Optional[str] = None


def with_db_retry(max_retries: int = 5, initial_delay: float = 0.05) -> Callable:
    """Decorator to retry SQLite transient lock errors (database is locked / busy)."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args: Any, **kwargs: Any) -> T:
            retries = 0
            delay = initial_delay
            while True:
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as exc:
                    if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                        retries += 1
                        if retries > max_retries:
                            logger.error("SQLite lock retry exceeded max attempts (%d): %s", max_retries, exc)
                            raise
                        logger.warning("SQLite busy/locked (attempt %d/%d), retrying in %.3fs...", retries, max_retries, delay)
                        time.sleep(delay)
                        delay *= 2.0
                    else:
                        raise
        return wrapper
    return decorator


class DatabaseHealthService:
    """Probes and verifies database integrity and responsiveness."""

    @classmethod
    def check_integrity(cls) -> Dict[str, Any]:
        """Execute SQLite PRAGMA integrity_check."""
        db_path_str = settings.DATABASE_URL.replace("sqlite:///", "")
        db_path = Path(db_path_str)

        if not db_path.exists():
            return {"integrity": "unknown", "error": "Database file not found."}

        try:
            conn = sqlite3.connect(str(db_path), timeout=5.0)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            res = cursor.fetchone()
            conn.close()

            status = "ok" if res and res[0] == "ok" else "corrupted"
            return {"integrity": status, "raw": res[0] if res else None}
        except Exception as exc:
            return {"integrity": "failed", "error": str(exc)}

    @classmethod
    def probe_health(cls) -> DatabaseHealthStatus:
        """Measure database connection latency and inspect schema table count."""
        start_t = time.perf_counter()
        db_path_str = settings.DATABASE_URL.replace("sqlite:///", "")

        try:
            conn = sqlite3.connect(db_path_str, timeout=2.0)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            latency = (time.perf_counter() - start_t) * 1000.0

            cursor.execute("PRAGMA integrity_check")
            check_res = cursor.fetchone()
            integrity = "ok" if check_res and check_res[0] == "ok" else "failed"

            cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table'")
            table_count = cursor.fetchone()[0]
            conn.close()

            status = "HEALTHY" if integrity == "ok" else "DEGRADED"

            return DatabaseHealthStatus(
                status=status,
                latency_ms=round(latency, 2),
                integrity=integrity,
                db_path=db_path_str,
                total_tables=table_count,
            )

        except Exception as exc:
            latency = (time.perf_counter() - start_t) * 1000.0
            return DatabaseHealthStatus(
                status="UNHEALTHY",
                latency_ms=round(latency, 2),
                integrity="failed",
                db_path=db_path_str,
                total_tables=0,
                error=str(exc),
            )
