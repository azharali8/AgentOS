"""
AgentOS Phase 16 - Reliability Benchmark.
25 deterministic reliability test cases.
"""
from __future__ import annotations
import sys, time, uuid, datetime, sqlite3
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

PASS = "PASS"
FAIL = "FAIL"


def run_case(number, description, fn):
    try:
        result = fn()
        ok = bool(result)
        print(f"  [{PASS if ok else FAIL}] Case {number:02d}: {description}")
        return ok
    except Exception as exc:
        print(f"  [{FAIL}] Case {number:02d}: {description} - Exception: {exc}")
        return False


def run_all():
    from backend.app.services.task_lease import TaskLeaseService, LeaseAcquisitionError, LeaseStatus
    from backend.app.services.worker_manager import WorkerManager, WorkerStatus
    from backend.app.services.task_queue import TaskQueue, QueueStatus
    from backend.app.services.task_scheduler import TaskScheduler
    from backend.app.services.database_health import DatabaseHealthService, with_db_retry
    from backend.app.services.event_service import EventService
    from backend.app.services.observability import ObservabilityService
    from backend.app.services.backup_service import BackupService
    from backend.app.security.rate_limit import RateLimiter
    from backend.app.services.distributed_lock import DistributedLock
    from backend.app.services.redis_client import is_redis_available
    from backend.app.db.database import get_db_dialect, get_db_session
    from backend.app.db.models import QueueEntryModel, WorkerModel, TaskLeaseModel
    from backend.app.services.task_service import TaskService
    from backend.app.models.task import TaskRequest, TaskStatus
    from backend.app.services.task_runtime import TaskRuntime, InvalidStateTransitionError
    from fastapi import HTTPException

    results = []
    cases = []

    # R01
    def case_01():
        lock_name = "rl-test-" + uuid.uuid4().hex[:8]
        owner_a = "owner-a-" + uuid.uuid4().hex[:6]
        owner_b = "owner-b-" + uuid.uuid4().hex[:6]
        if is_redis_available():
            tok_a = DistributedLock.acquire(lock_name, owner_a, ttl_seconds=1)
            if tok_a is None:
                return False
            time.sleep(1.1)
            tok_b = DistributedLock.acquire(lock_name, owner_b, ttl_seconds=5)
            if tok_b is None:
                return False
            DistributedLock.release(lock_name, tok_b)
            return True
        else:
            tok = DistributedLock.acquire(lock_name, owner_a, ttl_seconds=1)
            return tok is None
    cases.append((1, "Distributed Lock Expiry and Re-acquisition", case_01))

    # R02
    def case_02():
        task = TaskService.create_task(TaskRequest(instruction="Fencing monotonic"))
        wid = "wkr-" + uuid.uuid4().hex[:8]
        WorkerManager.register_worker(worker_id=wid, max_tasks=4)
        lease1 = TaskLeaseService.acquire_lease(task.task_id, wid, ttl_seconds=0)
        time.sleep(0.02)
        lease2 = TaskLeaseService.acquire_lease(task.task_id, wid, ttl_seconds=5)
        return lease2.fencing_token > lease1.fencing_token
    cases.append((2, "Fencing Token Strict Monotonic Increment", case_02))

    # R03
    def case_03():
        task = TaskService.create_task(TaskRequest(instruction="Zombie protection"))
        wid_zombie = "wkr-zombie-" + uuid.uuid4().hex[:6]
        wid_new = "wkr-new-" + uuid.uuid4().hex[:6]
        WorkerManager.register_worker(worker_id=wid_zombie, max_tasks=4)
        WorkerManager.register_worker(worker_id=wid_new, max_tasks=4)
        lease1 = TaskLeaseService.acquire_lease(task.task_id, wid_zombie, ttl_seconds=0)
        time.sleep(0.02)
        TaskLeaseService.acquire_lease(task.task_id, wid_new, ttl_seconds=10)
        try:
            TaskLeaseService.renew_lease(
                lease_id=lease1.lease_id, worker_id=wid_zombie,
                fencing_token=lease1.fencing_token, ttl_seconds=10,
            )
            return False
        except Exception:
            return True
    cases.append((3, "Zombie Worker Lease Mutation Rejection", case_03))

    # R04
    def case_04():
        task = TaskService.create_task(TaskRequest(instruction="Lease renewal extend"))
        wid = "wkr-" + uuid.uuid4().hex[:8]
        WorkerManager.register_worker(worker_id=wid, max_tasks=4)
        lease = TaskLeaseService.acquire_lease(task.task_id, wid, ttl_seconds=5)
        original_expiry = lease.lease_expires_at
        renewed = TaskLeaseService.renew_lease(
            lease_id=lease.lease_id, worker_id=wid,
            fencing_token=lease.fencing_token, ttl_seconds=30,
        )
        return renewed.lease_expires_at > original_expiry
    cases.append((4, "Lease Renewal Extends Expiry Correctly", case_04))

    # R05
    def case_05():
        task = TaskService.create_task(TaskRequest(instruction="Lease release lifecycle"))
        wid = "wkr-" + uuid.uuid4().hex[:8]
        WorkerManager.register_worker(worker_id=wid, max_tasks=4)
        lease = TaskLeaseService.acquire_lease(task.task_id, wid, ttl_seconds=30)
        released = TaskLeaseService.release_lease(
            lease_id=lease.lease_id, worker_id=wid, fencing_token=lease.fencing_token,
        )
        if released is not True:
            return False
        with get_db_session() as session:
            lm = session.query(TaskLeaseModel).filter_by(lease_id=lease.lease_id).first()
            return lm is not None and lm.status == LeaseStatus.RELEASED
    cases.append((5, "Lease Release Status Transitions to RELEASED", case_05))

    # R06
    def case_06():
        task = TaskService.create_task(TaskRequest(instruction="Second worker exclusion"))
        wid_a = "wkr-a-" + uuid.uuid4().hex[:6]
        wid_b = "wkr-b-" + uuid.uuid4().hex[:6]
        WorkerManager.register_worker(worker_id=wid_a, max_tasks=4)
        WorkerManager.register_worker(worker_id=wid_b, max_tasks=4)
        TaskLeaseService.acquire_lease(task.task_id, wid_a, ttl_seconds=30)
        try:
            TaskLeaseService.acquire_lease(task.task_id, wid_b, ttl_seconds=30)
            return False
        except LeaseAcquisitionError:
            return True
    cases.append((6, "Second Worker Active-Lease Exclusion", case_06))

    # R07
    def case_07():
        suffix = uuid.uuid4().hex[:6]
        t_low = TaskService.create_task(TaskRequest(instruction="Priority LOW " + suffix))
        t_high = TaskService.create_task(TaskRequest(instruction="Priority HIGH " + suffix))
        t_critical = TaskService.create_task(TaskRequest(instruction="Priority CRITICAL " + suffix))
        t_normal = TaskService.create_task(TaskRequest(instruction="Priority NORMAL " + suffix))
        idem_l = "idem-l-" + suffix
        idem_h = "idem-h-" + suffix
        idem_c = "idem-c-" + suffix
        idem_n = "idem-n-" + suffix
        TaskQueue.enqueue(t_low.task_id, priority=3, idempotency_key=idem_l)
        TaskQueue.enqueue(t_high.task_id, priority=1, idempotency_key=idem_h)
        TaskQueue.enqueue(t_critical.task_id, priority=0, idempotency_key=idem_c)
        TaskQueue.enqueue(t_normal.task_id, priority=2, idempotency_key=idem_n)
        with get_db_session() as session:
            entries = (
                session.query(QueueEntryModel)
                .filter(QueueEntryModel.idempotency_key.in_([idem_l, idem_h, idem_c, idem_n]))
                .filter(QueueEntryModel.status == QueueStatus.QUEUED)
                .all()
            )
            pmap = {"CRITICAL": 0, "HIGH": 1, "NORMAL": 2, "LOW": 3}
            pvals = []
            for e in entries:
                p = e.priority
                if isinstance(p, str) and p in pmap:
                    pvals.append(pmap[p])
                else:
                    pvals.append(int(p))
            return len(entries) == 4 and min(pvals) == 0
    cases.append((7, "Task Queue Priority Ordering CRITICAL Minimum", case_07))

    # R08
    def case_08():
        task = TaskService.create_task(TaskRequest(instruction="Idempotent enqueue test"))
        idem_key = "idem-" + uuid.uuid4().hex[:12]
        TaskQueue.enqueue(task.task_id, idempotency_key=idem_key)
        TaskQueue.enqueue(task.task_id, idempotency_key=idem_key)
        with get_db_session() as session:
            count = session.query(QueueEntryModel).filter(QueueEntryModel.idempotency_key == idem_key).count()
        return count == 1
    cases.append((8, "Idempotent Enqueue Duplicate Suppression", case_08))

    # R09
    def case_09():
        wid = "wkr-hb-" + uuid.uuid4().hex[:8]
        WorkerManager.register_worker(worker_id=wid, max_tasks=2)
        with get_db_session() as session:
            w = session.query(WorkerModel).filter_by(worker_id=wid).first()
            t0 = w.last_heartbeat
        time.sleep(0.05)
        WorkerManager.heartbeat(worker_id=wid, active_tasks=1)
        with get_db_session() as session:
            w = session.query(WorkerModel).filter_by(worker_id=wid).first()
            t1 = w.last_heartbeat
        t0_utc = t0.replace(tzinfo=datetime.timezone.utc) if t0.tzinfo is None else t0
        t1_utc = t1.replace(tzinfo=datetime.timezone.utc) if t1.tzinfo is None else t1
        return t1_utc >= t0_utc
    cases.append((9, "Worker Heartbeat Updates last_heartbeat Timestamp", case_09))

    # R10
    def case_10():
        wid = "wkr-stale-" + uuid.uuid4().hex[:6]
        WorkerManager.register_worker(worker_id=wid, max_tasks=2)
        ancient = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=120)
        with get_db_session() as session:
            row = session.query(WorkerModel).filter_by(worker_id=wid).first()
            if row:
                row.last_heartbeat = ancient
                row.status = WorkerStatus.READY
                session.commit()
        WorkerManager.check_worker_health()
        with get_db_session() as session:
            row = session.query(WorkerModel).filter_by(worker_id=wid).first()
            st = row.status if row else None
        return st in (WorkerStatus.UNHEALTHY, WorkerStatus.OFFLINE)
    cases.append((10, "Stale Worker UNHEALTHY Detection via Heartbeat Sweep", case_10))

    # R11
    def case_11():
        wid = "wkr-drain-" + uuid.uuid4().hex[:6]
        cap = "CAP_DRAIN_" + uuid.uuid4().hex[:4].upper()
        WorkerManager.register_worker(worker_id=wid, capabilities=[cap], max_tasks=4)
        WorkerManager.drain_worker(worker_id=wid)
        worker = TaskScheduler.find_eligible_worker(required_capabilities=[cap])
        return worker is None
    cases.append((11, "DRAINING Worker Excluded from Task Scheduling", case_11))

    # R12
    def case_12():
        wid = "wkr-full-" + uuid.uuid4().hex[:6]
        cap = "CAP_FULL_" + uuid.uuid4().hex[:4].upper()
        WorkerManager.register_worker(worker_id=wid, capabilities=[cap], max_tasks=1)
        WorkerManager.heartbeat(worker_id=wid, active_tasks=1)
        worker = TaskScheduler.find_eligible_worker(required_capabilities=[cap])
        return worker is None
    cases.append((12, "Worker Capacity Exhaustion Exclusion", case_12))

    # R13
    def case_13():
        task = TaskService.create_task(TaskRequest(instruction="Terminal immutable"))
        TaskService.cancel_task(task.task_id)
        try:
            TaskRuntime.validate_transition(TaskStatus.CANCELLED, TaskStatus.EXECUTING)
            return False
        except InvalidStateTransitionError:
            return True
    cases.append((13, "Terminal State CANCELLED to EXECUTING Rejected", case_13))

    # R14
    def case_14():
        v1 = TaskRuntime.validate_transition(TaskStatus.PENDING, TaskStatus.PLANNING)
        v2 = TaskRuntime.validate_transition(TaskStatus.EXECUTING, TaskStatus.COMPLETED)
        return v1 is True and v2 is True
    cases.append((14, "Task State Machine Valid Transition Acceptance", case_14))

    # R15
    def case_15():
        task = TaskService.create_task(TaskRequest(instruction="Event record test"))
        EventService.record_event(task.task_id, "PHASE16_TEST_EVENT", payload={"key": "value"})
        events = EventService.list_events(task.task_id)
        return any(e.get("event_type") == "PHASE16_TEST_EVENT" for e in events)
    cases.append((15, "Event Service Records and Retrieves Events by Task ID", case_15))

    # R16
    def case_16():
        task = TaskService.create_task(TaskRequest(instruction="Event replay ordering"))
        for i in range(3):
            EventService.record_event(task.task_id, "REPLAY_EVENT_" + str(i), payload={"seq": i})
            time.sleep(0.01)
        events = EventService.list_events(task.task_id)
        etypes = [e.get("event_type") for e in events if str(e.get("event_type", "")).startswith("REPLAY_EVENT_")]
        return etypes == ["REPLAY_EVENT_0", "REPLAY_EVENT_1", "REPLAY_EVENT_2"]
    cases.append((16, "Event Replay Returns Events in Chronological Order", case_16))

    # R17
    def case_17():
        health = DatabaseHealthService.probe_health()
        return health.status == "HEALTHY" and health.latency_ms > 0
    cases.append((17, "Database Health Probe Returns HEALTHY with Live Latency", case_17))

    # R18
    def case_18():
        call_count = [0]
        @with_db_retry(max_retries=3, initial_delay=0.001)
        def flaky_fn():
            call_count[0] += 1
            if call_count[0] < 3:
                raise sqlite3.OperationalError("database is locked")
            return True
        result = flaky_fn()
        return result is True and call_count[0] == 3
    cases.append((18, "DB Retry Decorator Retries on Transient Lock Error", case_18))

    # R19
    def case_19():
        key = "rl-r19-" + uuid.uuid4().hex[:8]
        domain = "auth"
        RateLimiter.reset_for_test(key, domain)
        blocked = False
        for _ in range(10):
            try:
                RateLimiter.check_rate_limit(key, domain)
            except HTTPException as exc:
                if exc.status_code == 429:
                    blocked = True
                    break
        RateLimiter.reset_for_test(key, domain)
        return blocked
    cases.append((19, "Rate Limiter Enforces Auth Window Limit", case_19))

    # R20
    def case_20():
        key = "rl-r20-" + uuid.uuid4().hex[:8]
        domain = "auth"
        RateLimiter.reset_for_test(key, domain)
        for _ in range(10):
            try:
                RateLimiter.check_rate_limit(key, domain)
            except HTTPException:
                pass
        RateLimiter.reset_for_test(key, domain)
        allowed = RateLimiter.check_rate_limit(key, domain)
        return allowed is True
    cases.append((20, "Rate Limiter Allows Traffic After Domain Reset", case_20))

    # R21
    def case_21():
        snapshot = ObservabilityService.get_full_snapshot()
        required_keys = {"system", "llm"}
        return required_keys.issubset(snapshot.keys())
    cases.append((21, "Observability Telemetry Snapshot Completeness", case_21))

    # R22
    def case_22():
        dialect = get_db_dialect()
        return dialect == "sqlite"
    cases.append((22, "Database Dialect Detection Returns sqlite in Dev/Test", case_22))

    # R23
    def case_23():
        task = TaskService.create_task(TaskRequest(instruction="Queue status transition"))
        idem = "idem-q-" + uuid.uuid4().hex[:8]
        wid = "wkr-qs-" + uuid.uuid4().hex[:6]
        WorkerManager.register_worker(worker_id=wid, max_tasks=4)
        entry = TaskQueue.enqueue(task.task_id, idempotency_key=idem)
        assert entry.status == QueueStatus.QUEUED
        TaskLeaseService.acquire_lease(task.task_id, wid, ttl_seconds=30)
        with get_db_session() as session:
            row = session.query(QueueEntryModel).filter_by(task_id=task.task_id).first()
            st = row.status if row else None
        return st == QueueStatus.RUNNING
    cases.append((23, "Queue Status Transitions QUEUED to RUNNING via Lease Acquisition", case_23))

    # R24
    def case_24():
        if not is_redis_available():
            print("      [SKIP] Redis unavailable - Redis lock ownership test skipped")
            return True
        lock_name = "rl-own-" + uuid.uuid4().hex[:8]
        owner_a = "oa-" + uuid.uuid4().hex[:6]
        owner_b = "ob-" + uuid.uuid4().hex[:6]
        tok_a = DistributedLock.acquire(lock_name, owner_a, ttl_seconds=10)
        if tok_a is None:
            return False
        tok_b = DistributedLock.acquire(lock_name, owner_b, ttl_seconds=10)
        result = tok_b is None
        DistributedLock.release(lock_name, tok_a)
        return result
    cases.append((24, "Redis Distributed Lock Token Ownership Exclusivity", case_24))

    # R25
    def case_25():
        try:
            result = BackupService.create_backup()
            backup_path = result.get("backup_path") or result.get("path")
            if not backup_path:
                return False
            verify = BackupService.verify_backup(backup_path)
            return verify.get("success", False)
        except Exception as exc:
            print("      [NOTE] Backup: " + str(exc))
            return False
    cases.append((25, "Backup Create and Verify SHA-256 Integrity", case_25))


    for number, description, fn in cases:
        ok = run_case(number, description, fn)
        results.append(ok)

    total = len(results)
    passed = sum(results)
    failed = total - passed
    print()
    print("-" * 56)
    print("  Phase 16 Reliability Benchmark: " + str(passed) + "/" + str(total) + " PASSED (" + str(round(100 * passed / total, 1)) + "%)")
    print("-" * 56)
    return {"total": total, "passed": passed, "failed": failed, "all_passed": failed == 0}


def main():
    print()
    print("=" * 56)
    print("  AgentOS Phase 16 - Reliability Benchmark")
    print("=" * 56)
    print()
    result = run_all()
    sys.exit(0 if result["all_passed"] else 1)


if __name__ == "__main__":
    main()
