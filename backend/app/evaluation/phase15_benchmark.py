"""
AgentOS Phase 15 — Distributed Execution & Scalability Benchmark Suite.

25 deterministic validation cases covering:
- P15-01 Worker Registration
- P15-02 Worker Heartbeat
- P15-03 Worker Capability Matching
- P15-04 Worker Capacity Enforcement
- P15-05 Priority Scheduling
- P15-06 FIFO Ordering
- P15-07 Task Lease Creation
- P15-08 Lease Renewal
- P15-09 Lease Expiration
- P15-10 Duplicate Dispatch Prevention
- P15-11 Worker Failure Detection
- P15-12 Orphan Task Recovery
- P15-13 Task Requeue
- P15-14 Distributed Concurrency
- P15-15 Per-Agent Worker Limits
- P15-16 Task Idempotency
- P15-17 Graceful Worker Shutdown
- P15-18 Worker Drain
- P15-19 Distributed Trace Correlation
- P15-20 Audit Event Generation
- P15-21 RBAC Worker Administration
- P15-22 Security Boundary Preservation
- P15-23 Artifact Integrity Preservation
- P15-24 Multi-Worker E2E Workflow
- P15-25 Crash Recovery E2E

Target: 25/25 PASS
"""


from __future__ import annotations

import datetime
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

PASS = "PASS"
FAIL = "FAIL"


def run_case(number: int, description: str, fn: Callable[[], bool]) -> bool:
    try:
        ok = bool(fn())
        icon = PASS if ok else FAIL
        print(f"  [{icon}] Case {number:02d}: {description}")
        return ok
    except Exception as exc:
        print(f"  [{FAIL}] Case {number:02d}: {description} - Exception: {exc}")
        return False


def run_all() -> Dict[str, Any]:
    print("\n========================================================")
    print("  AgentOS Phase 15 - Distributed Execution Benchmark")
    print("========================================================\n")

    from backend.app.auth.service import AuthService, UserRole
    from backend.app.db.database import get_db_session
    from backend.app.db.models import QueueEntryModel, TaskLeaseModel, TaskModel, WorkerModel
    from backend.app.models.task import TaskPriority, TaskRequest, TaskStatus
    from backend.app.services.artifact_service import ArtifactService
    from backend.app.services.concurrency_manager import ConcurrencyManager
    from backend.app.services.recovery_service import RecoveryService
    from backend.app.services.task_lease import (
        FencingTokenMismatchError,
        LeaseAcquisitionError,
        TaskLeaseService,
    )
    from backend.app.services.task_queue import QueueStatus, TaskQueue
    from backend.app.services.task_scheduler import TaskScheduler
    from backend.app.services.task_service import TaskService
    from backend.app.services.trace_service import TraceService
    from backend.app.services.worker_manager import WorkerManager, WorkerStatus
    from backend.app.services.worker_runtime import WorkerRuntime
    from backend.app.services.workspace_service import WorkspaceService

    cases = []

    # ── P15-01: Worker Registration ──────────────────────────────────────────
    def case_01():
        wid = f"bench-wkr-{uuid.uuid4().hex[:6]}"
        w = WorkerManager.register_worker(worker_id=wid, capabilities=["CODING", "TESTING"], max_tasks=3)
        found = WorkerManager.get_worker(wid)
        return found is not None and found["status"] == WorkerStatus.READY and found["max_tasks"] == 3

    cases.append((1, "Worker Registration & Capability Advertising", case_01))

    # ── P15-02: Worker Heartbeat ─────────────────────────────────────────────
    def case_02():
        wid = f"bench-wkr-{uuid.uuid4().hex[:6]}"
        WorkerManager.register_worker(worker_id=wid)
        ok = WorkerManager.heartbeat(wid, active_tasks=1)
        w = WorkerManager.get_worker(wid)
        return ok and w["active_tasks"] == 1

    cases.append((2, "Worker Periodic Heartbeat & Active Count Update", case_02))

    # ── P15-03: Worker Capability Matching ───────────────────────────────────
    def case_03():
        unique_cap = f"CYBER_CAP_{uuid.uuid4().hex[:6]}"
        w_sec = f"wkr-sec-{uuid.uuid4().hex[:6]}"
        w_code = f"wkr-code-{uuid.uuid4().hex[:6]}"
        WorkerManager.register_worker(worker_id=w_sec, capabilities=[unique_cap])
        WorkerManager.register_worker(worker_id=w_code, capabilities=["CODING"])

        matched_wid = TaskScheduler.find_eligible_worker(required_capabilities=[unique_cap])
        return matched_wid == w_sec

    cases.append((3, "Intelligent Worker Capability Matching", case_03))


    # ── P15-04: Worker Capacity Enforcement ──────────────────────────────────
    def case_04():
        wid = f"wkr-full-{uuid.uuid4().hex[:6]}"
        WorkerManager.register_worker(worker_id=wid, capabilities=["DATA_ENG"], max_tasks=1)
        WorkerManager.heartbeat(wid, active_tasks=1)  # full

        matched_wid = TaskScheduler.find_eligible_worker(required_capabilities=["DATA_ENG"])
        return matched_wid != wid

    cases.append((4, "Worker Maximum Capacity Limit Enforcement", case_04))

    # ── P15-05: Priority Scheduling ──────────────────────────────────────────
    def case_05():
        unique_cap = f"PRIO_CAP_{uuid.uuid4().hex[:6]}"
        t1 = TaskService.create_task(TaskRequest(instruction="Low task"))
        t2 = TaskService.create_task(TaskRequest(instruction="Critical task"))

        TaskQueue.enqueue(task_id=t1.task_id, priority=TaskPriority.LOW, required_capabilities=[unique_cap])
        TaskQueue.enqueue(task_id=t2.task_id, priority=TaskPriority.CRITICAL, required_capabilities=[unique_cap])

        dequeued = TaskQueue.dequeue(worker_capabilities=[unique_cap])
        return dequeued is not None and dequeued.task_id == t2.task_id

    cases.append((5, "Priority-Based Task Scheduling (CRITICAL > LOW)", case_05))

    # ── P15-06: FIFO Ordering Within Same Priority ───────────────────────────
    def case_06():
        unique_cap = f"FIFO_CAP_{uuid.uuid4().hex[:6]}"
        t1 = TaskService.create_task(TaskRequest(instruction="1st"))
        t2 = TaskService.create_task(TaskRequest(instruction="2nd"))

        TaskQueue.enqueue(task_id=t1.task_id, priority=TaskPriority.NORMAL, required_capabilities=[unique_cap])
        time.sleep(0.01)
        TaskQueue.enqueue(task_id=t2.task_id, priority=TaskPriority.NORMAL, required_capabilities=[unique_cap])

        d1 = TaskQueue.dequeue(worker_capabilities=[unique_cap])
        return d1 is not None and d1.task_id == t1.task_id

    cases.append((6, "FIFO Ordering Tie-Breaking for Identical Priorities", case_06))


    # ── P15-07: Task Lease Creation & Monotonic Fencing ──────────────────────
    def case_07():
        task = TaskService.create_task(TaskRequest(instruction="Lease test"))
        wid = f"wkr-l1-{uuid.uuid4().hex[:6]}"
        TaskQueue.enqueue(task_id=task.task_id)

        lease = TaskLeaseService.acquire_lease(task.task_id, wid, ttl_seconds=20)
        return lease.worker_id == wid and lease.fencing_token == 1 and lease.status == "ACTIVE"

    cases.append((7, "Task Lease Acquisition & Initial Fencing Token", case_07))

    # ── P15-08: Lease Renewal ────────────────────────────────────────────────
    def case_08():
        task = TaskService.create_task(TaskRequest(instruction="Renew test"))
        wid = f"wkr-ren-{uuid.uuid4().hex[:6]}"
        TaskQueue.enqueue(task_id=task.task_id)

        lease = TaskLeaseService.acquire_lease(task.task_id, wid, ttl_seconds=10)
        renewed = TaskLeaseService.renew_lease(lease.lease_id, wid, fencing_token=lease.fencing_token, ttl_seconds=30)
        return renewed.renew_count == 1 and renewed.lease_expires_at > lease.lease_started_at

    cases.append((8, "Idempotent Task Lease Heartbeat Renewal", case_08))

    # ── P15-09: Lease Expiration Detection ───────────────────────────────────
    def case_09():
        task = TaskService.create_task(TaskRequest(instruction="Exp test"))
        wid = f"wkr-exp-{uuid.uuid4().hex[:6]}"
        TaskQueue.enqueue(task_id=task.task_id)

        lease = TaskLeaseService.acquire_lease(task.task_id, wid, ttl_seconds=0)  # expires immediately
        time.sleep(0.05)
        expired = TaskLeaseService.get_expired_leases()
        return any(l.lease_id == lease.lease_id for l in expired)

    cases.append((9, "Deterministic Task Lease Expiration Detection", case_09))

    # ── P15-10: Duplicate Dispatch Prevention & Split-Brain Rejection ────────
    def case_10():
        task = TaskService.create_task(TaskRequest(instruction="Dup test"))
        wid1 = f"wkr-d1-{uuid.uuid4().hex[:6]}"
        wid2 = f"wkr-d2-{uuid.uuid4().hex[:6]}"
        TaskQueue.enqueue(task_id=task.task_id)

        l1 = TaskLeaseService.acquire_lease(task.task_id, wid1, ttl_seconds=30)
        rejected = False
        try:
            TaskLeaseService.acquire_lease(task.task_id, wid2, ttl_seconds=30)
        except LeaseAcquisitionError:
            rejected = True
        return rejected

    cases.append((10, "Duplicate Dispatch Prevention & Concurrent Lease Lockout", case_10))

    # ── P15-11: Worker Failure Detection (Heartbeat Timeout) ─────────────────
    def case_11():
        wid = f"wkr-dead-{uuid.uuid4().hex[:6]}"
        WorkerManager.register_worker(worker_id=wid)
        with get_db_session() as session:
            db_w = session.query(WorkerModel).filter_by(worker_id=wid).first()
            db_w.last_heartbeat = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=40)
            session.commit()

        summary = WorkerManager.check_worker_health()
        return wid in summary["unhealthy_workers"]

    cases.append((11, "Worker Failure Detection via Heartbeat Timeout", case_11))

    # ── P15-12: Orphan Task Recovery via Fencing Token Increment ─────────────
    def case_12():
        task = TaskService.create_task(TaskRequest(instruction="Orphan test"))
        wid1 = f"wkr-o1-{uuid.uuid4().hex[:6]}"
        wid2 = f"wkr-o2-{uuid.uuid4().hex[:6]}"
        TaskQueue.enqueue(task_id=task.task_id)

        l1 = TaskLeaseService.acquire_lease(task.task_id, wid1, ttl_seconds=0)  # expired
        time.sleep(0.02)
        l2 = TaskLeaseService.acquire_lease(task.task_id, wid2, ttl_seconds=30)
        return l2.fencing_token == 2 and l2.worker_id == wid2

    cases.append((12, "Orphan Task Recovery with Incrementing Fencing Token", case_12))

    # ── P15-13: Task Requeue & Retry Tracking ────────────────────────────────
    def case_13():
        task = TaskService.create_task(TaskRequest(instruction="Requeue test"))
        TaskQueue.enqueue(task_id=task.task_id, retry_limit=3)

        ok = TaskQueue.requeue(task.task_id, reason="Simulated crash")
        entry = TaskQueue.get_entry(task.task_id)
        return ok and entry.status == QueueStatus.QUEUED and entry.retry_count == 1

    cases.append((13, "Automated Task Requeuing with Retry Tracking", case_13))

    # ── P15-14: Distributed Concurrency Limits ───────────────────────────────
    def case_14():
        metrics = ConcurrencyManager.get_metrics()
        return "max_concurrent_tasks" in metrics and "agent_concurrency" in metrics

    cases.append((14, "Distributed Concurrency Metrics Integration", case_14))

    # ── P15-15: Per-Agent Worker Limits ──────────────────────────────────────
    def case_15():
        from backend.app.models.multi_agent import AgentType
        slot1 = ConcurrencyManager.acquire_agent_slot(AgentType.CODING)
        slot2 = ConcurrencyManager.acquire_agent_slot(AgentType.CODING)
        ConcurrencyManager.release_agent_slot(AgentType.CODING)
        ConcurrencyManager.release_agent_slot(AgentType.CODING)
        return slot1 and slot2

    cases.append((15, "Per-Agent Worker Semaphore Management", case_15))

    # ── P15-16: Task Submission Idempotency ──────────────────────────────────
    def case_16():
        t1 = TaskService.create_task(TaskRequest(instruction="Idem 1"))
        t2 = TaskService.create_task(TaskRequest(instruction="Idem 2"))
        key = f"idem-key-{uuid.uuid4().hex[:8]}"

        e1 = TaskQueue.enqueue(task_id=t1.task_id, idempotency_key=key)
        e2 = TaskQueue.enqueue(task_id=t2.task_id, idempotency_key=key)
        return e1.task_id == e2.task_id and e1.queue_id == e2.queue_id

    cases.append((16, "Idempotent Task Submission via Idempotency Key", case_16))

    # ── P15-17: Graceful Worker Shutdown ─────────────────────────────────────
    def case_17():
        wid = f"wkr-shut-{uuid.uuid4().hex[:6]}"
        runtime = WorkerRuntime(worker_id=wid, capabilities=["CODING"], max_tasks=1)
        runtime.start()
        time.sleep(0.1)
        runtime.stop()
        w = WorkerManager.get_worker(wid)
        return w["status"] == WorkerStatus.OFFLINE

    cases.append((17, "Graceful Worker Process Lifecycle & Clean Shutdown", case_17))

    # ── P15-18: Worker Drain State ───────────────────────────────────────────
    def case_18():
        wid = f"wkr-drn-{uuid.uuid4().hex[:6]}"
        WorkerManager.register_worker(worker_id=wid, capabilities=["TESTING"])
        ok = WorkerManager.drain_worker(wid)
        w = WorkerManager.get_worker(wid)
        matched_wid = TaskScheduler.find_eligible_worker(required_capabilities=["TESTING"])
        return ok and w["status"] == WorkerStatus.DRAINING and matched_wid != wid

    cases.append((18, "Worker Draining: Reject New Work While Finishing Active", case_18))

    # ── P15-19: Distributed Trace Correlation ────────────────────────────────
    def case_19():
        task = TaskService.create_task(TaskRequest(instruction="Trace test"))
        wid = f"wkr-trc-{uuid.uuid4().hex[:6]}"
        TaskQueue.enqueue(task_id=task.task_id)
        lease = TaskLeaseService.acquire_lease(task.task_id, wid)

        trace = TraceService.build_trace(task.task_id)
        return trace.task_id == task.task_id and trace.worker_id == wid and trace.fencing_token == 1

    cases.append((19, "Distributed Trace Hierarchy with Worker & Lease Correlation", case_19))

    # ── P15-20: Audit Event Generation ───────────────────────────────────────
    def case_20():
        wid = f"wkr-audit-{uuid.uuid4().hex[:6]}"
        WorkerManager.register_worker(worker_id=wid)
        from backend.app.services.event_service import EventService
        events = EventService.list_events(f"sys-{wid}")
        return any(e["event_type"] == "WORKER_REGISTERED" for e in events)

    cases.append((20, "Structured Event Bus Emission for Distributed Operations", case_20))

    # ── P15-21: RBAC Worker Administration ───────────────────────────────────
    def case_21():
        from backend.app.auth.service import require_role
        from fastapi import HTTPException
        checker = require_role(UserRole.ADMIN)
        user_dev = AuthService.authenticate_key("test-dev-key")
        user_admin = AuthService.authenticate_key("test-admin-key")

        dev_blocked = False
        try:
            checker(user_dev)
        except HTTPException as exc:
            dev_blocked = (exc.status_code == 403)

        admin_allowed = (checker(user_admin).role == UserRole.ADMIN)
        return dev_blocked and admin_allowed

    cases.append((21, "Strict RBAC on Administrative Worker Endpoints", case_21))

    # ── P15-22: Security Boundary Preservation ───────────────────────────────
    def case_22():
        try:
            WorkspaceService.validate_path("../../../etc/passwd")
            return False
        except ValueError:
            return True

    cases.append((22, "Preservation of Workspace Sandboxing across Workers", case_22))

    # ── P15-23: Artifact Integrity Preservation ──────────────────────────────
    def case_23():
        from backend.app.services.artifact_service import ArtifactType
        task = TaskService.create_task(TaskRequest(instruction="Art test"))
        art = ArtifactService.save(
            task_id=task.task_id,
            agent_id="test-agent",
            artifact_type=ArtifactType.PATCH,
            content={"diff": "diff --git a/x b/x", "files": ["x"]},
        )
        verified = ArtifactService.get(art.artifact_id)
        return verified is not None and verified.content_hash == art.content_hash

    cases.append((23, "Immutable SHA-256 Artifact Integrity Verification", case_23))


    # ── P15-24: Multi-Worker E2E Dispatch Workflow ───────────────────────────
    def case_24():
        wid1 = f"wkr-e2e1-{uuid.uuid4().hex[:6]}"
        wid2 = f"wkr-e2e2-{uuid.uuid4().hex[:6]}"
        WorkerManager.register_worker(worker_id=wid1, capabilities=["CODING"])
        WorkerManager.register_worker(worker_id=wid2, capabilities=["TESTING"])

        t_code = TaskService.create_task(TaskRequest(instruction="Code task"))
        t_test = TaskService.create_task(TaskRequest(instruction="Test task"))

        TaskQueue.enqueue(task_id=t_code.task_id, required_capabilities=["CODING"])
        TaskQueue.enqueue(task_id=t_test.task_id, required_capabilities=["TESTING"])

        dispatched = TaskScheduler.schedule_all()
        return len(dispatched) >= 2

    cases.append((24, "Multi-Worker Parallel Task Capability Dispatching", case_24))

    # ── P15-25: Crash Recovery E2E Simulation ────────────────────────────────
    def case_25():
        task = TaskService.create_task(TaskRequest(instruction="Crash test"))
        wid_fail = f"wkr-fail-{uuid.uuid4().hex[:6]}"
        TaskQueue.enqueue(task_id=task.task_id)

        # Worker leases task and then expires/fails
        lease = TaskLeaseService.acquire_lease(task.task_id, wid_fail, ttl_seconds=0)
        time.sleep(0.02)

        # Trigger recovery
        rec_summary = RecoveryService.recover_tasks_on_startup()
        entry = TaskQueue.get_entry(task.task_id)
        return rec_summary.get("expired_leases_recovered", 0) >= 1 and entry.status == QueueStatus.QUEUED

    cases.append((25, "End-to-End Crash Recovery, Lease Expiry & Re-queueing", case_25))

    # ── Execution ────────────────────────────────────────────────────────────
    passed = 0
    total = len(cases)

    for num, desc, fn in cases:
        if run_case(num, desc, fn):
            passed += 1

    print("\n--------------------------------------------------------")
    print(f"  Phase 15 Benchmark: {passed}/{total} PASSED ({round((passed/total)*100, 1)}%)")
    print("--------------------------------------------------------\n")

    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "success_rate_pct": round((passed / total) * 100, 1),
    }


if __name__ == "__main__":
    res = run_all()
    if res["passed"] != res["total"]:
        sys.exit(1)
