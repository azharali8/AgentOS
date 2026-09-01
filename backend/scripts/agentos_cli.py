"""
AgentOS Phase 16 — CLI Operations & Diagnostic Suite.
Provides 'doctor', 'workers', 'queue', 'scheduler', and 'health' commands.
"""


from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config.settings import settings
from backend.app.db.database import get_db_dialect, get_db_session
from backend.app.services.database_health import DatabaseHealthService
from backend.app.services.distributed_lock import DistributedLock
from backend.app.services.observability import ObservabilityService
from backend.app.services.redis_client import is_redis_available
from backend.app.services.task_queue import TaskQueue
from backend.app.services.worker_manager import WorkerManager


def doctor() -> int:
    """Run comprehensive production diagnostics against real platform components."""
    print("\n========================================================")
    print("  AgentOS Doctor — Phase 16 Infrastructure Verification")
    print("========================================================\n")

    checks = []

    # 1. Database Connectivity & Dialect
    dialect = get_db_dialect()
    db_health = DatabaseHealthService.probe_health()
    db_ok = db_health.status == "HEALTHY"
    print(f"[{'PASS' if db_ok else 'FAIL'}] Database: {dialect.upper()} ({db_health.status}, {db_health.latency_ms:.2f}ms)")
    checks.append(db_ok)

    # 2. Redis Connectivity
    redis_ok = is_redis_available()
    print(f"[{'PASS' if redis_ok else 'WARN'}] Redis Cache & Streams: {'REACHABLE' if redis_ok else 'UNAVAILABLE (falling back to SQLite)'}")
    # Redis is optional in dev, required in prod
    if settings.APP_ENV == "production":
        checks.append(redis_ok)

    # 3. Workspace Root
    ws_path = Path(settings.WORKSPACE_ROOT)
    ws_ok = ws_path.exists() and ws_path.is_dir()
    print(f"[{'PASS' if ws_ok else 'FAIL'}] Workspace Directory: {ws_path}")
    checks.append(ws_ok)

    # 4. Queue Backend
    q_backend = getattr(settings, "QUEUE_BACKEND", "sqlite")
    q_stats = TaskQueue.get_stats()
    print(f"[PASS] Task Queue Backend: {q_backend.upper()} (Active Tasks: {q_stats.get('total_active', q_stats.get('total_tasks', 0))})")
    checks.append(True)

    # 5. Distributed Scheduler Lock
    lock_held = DistributedLock.is_locked("agentos:scheduler:dispatch")
    print(f"[PASS] Distributed Scheduler Lock: {'HELD' if lock_held else 'FREE'}")
    checks.append(True)

    # 6. Worker Fleet
    workers = WorkerManager.list_workers()
    healthy = sum(1 for w in workers if w.get("status") in ("READY", "BUSY"))
    print(f"[PASS] Registered Workers: {len(workers)} total ({healthy} healthy)")
    checks.append(True)

    all_passed = all(checks)
    print("\n--------------------------------------------------------")
    print(f"  Doctor Result: {'ALL CHECKS PASSED' if all_passed else 'DEGRADED OR FAILED CHECKS'}")
    print("--------------------------------------------------------\n")
    return 0 if all_passed else 1


def workers() -> None:
    """List registered workers in the cluster."""
    w_list = WorkerManager.list_workers()
    print(json.dumps(w_list, indent=2))


def queue() -> None:
    """Print queue metrics and status distribution."""
    stats = TaskQueue.get_stats()
    print(json.dumps(stats, indent=2))


def health() -> None:
    """Return consolidated JSON health snapshot."""
    snap = ObservabilityService.get_full_snapshot()
    print(json.dumps(snap, indent=2))


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m backend.scripts.agentos_cli [doctor|workers|queue|scheduler|health]")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "doctor":
        sys.exit(doctor())
    elif cmd == "workers":
        workers()
    elif cmd == "queue":
        queue()
    elif cmd == "health":
        health()
    elif cmd == "scheduler":
        lock_held = DistributedLock.is_locked("agentos:scheduler:dispatch")
        holder = DistributedLock.get_holder_token("agentos:scheduler:dispatch")
        print(json.dumps({"lock_name": "agentos:scheduler:dispatch", "is_locked": lock_held, "holder": holder}, indent=2))
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
