"""
AgentOS Phase 1 — Safe Administrative Workspace Recovery Script.

Operates with strict preconditions, native SQLite backup verification,
and atomic in-session domain transitions to release the workspace lock.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import sqlite3
import sys
import uuid
from pathlib import Path

from backend.app.db.database import get_db_session
from backend.app.db.models import ApprovalModel, AuditLogModel, EventModel, QueueEntryModel, TaskLeaseModel, TaskModel
from backend.app.models.approval import ApprovalStatus
from backend.app.models.task import TaskStatus

TARGET_TASKS = [
    "0341d09d-05de-43c2-a8b5-c27f4eb5cc89",
    "8fe34442-c89e-4de1-80dd-5dcce27c504f",
    "93c5440e-4148-412d-910f-ab272f2399ff",
    "d50d14c9-c702-4bab-b91c-43a2a42317b6",
    "ebe2fb34-4ed9-44af-9111-081e44c56921",
]

TARGET_APPROVALS = [
    "appr-0341d09d-05de-43c2-a8b5-c27f4eb5cc89-2-0",
    "appr-8fe34442-c89e-4de1-80dd-5dcce27c504f-recovery-1-fix-1",
    "appr-93c5440e-4148-412d-910f-ab272f2399ff-1-0",
    "appr-d50d14c9-c702-4bab-b91c-43a2a42317b6-1-0",
]


def blocking_workspace_task_ids_session(db) -> list[str]:
    """In-session version of blocking_workspace_task_ids to evaluate transaction view."""
    blocking_statuses = {
        TaskStatus.PLANNING.value,
        TaskStatus.EXECUTING.value,
        TaskStatus.REVIEWING.value,
        TaskStatus.CANCELLING.value,
        TaskStatus.WAITING_APPROVAL.value,
        TaskStatus.PAUSED.value,
        TaskStatus.RECOVERY_REQUIRED.value,
    }
    queue_blocking = {"QUEUED", "DISPATCHED", "RUNNING", "PAUSED", "CANCELLING", "RECOVERY_REQUIRED"}
    terminal_statuses = [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]
    now = datetime.datetime.now(datetime.timezone.utc)

    ids = {row[0] for row in db.query(TaskModel.task_id).filter(TaskModel.status.in_(blocking_statuses)).all()}
    ids.update(
        row[0]
        for row in db.query(QueueEntryModel.task_id)
        .join(TaskModel)
        .filter(QueueEntryModel.status.in_(queue_blocking), ~TaskModel.status.in_(terminal_statuses))
        .all()
    )
    for task_id, expiry in (
        db.query(TaskLeaseModel.task_id, TaskLeaseModel.lease_expires_at)
        .join(TaskModel)
        .filter(TaskLeaseModel.status == "ACTIVE", ~TaskModel.status.in_(terminal_statuses))
        .all()
    ):
        expiry_utc = expiry.replace(tzinfo=datetime.timezone.utc) if expiry and expiry.tzinfo is None else expiry
        if expiry_utc and expiry_utc > now:
            ids.add(task_id)

    ids.update(
        row[0]
        for row in db.query(ApprovalModel.task_id)
        .join(TaskModel)
        .filter(ApprovalModel.status == "PENDING", ~TaskModel.status.in_(terminal_statuses))
        .all()
    )
    return sorted(ids)


def perform_verified_backup(src_db: str = "data/agentos.db", backup_dir: str = "data/backups") -> dict:
    Path(backup_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = Path(backup_dir) / f"agentos_backup_{ts}.db"

    print(f"Creating native SQLite online backup to: {backup_file}...")
    src_conn = sqlite3.connect(src_db)
    dst_conn = sqlite3.connect(str(backup_file))
    try:
        with dst_conn:
            src_conn.backup(dst_conn, pages=250)
    finally:
        dst_conn.close()
        src_conn.close()

    print("Verifying backup integrity...")
    verify_conn = sqlite3.connect(str(backup_file))
    cur = verify_conn.cursor()

    cur.execute("PRAGMA integrity_check")
    integ = cur.fetchall()
    if integ != [("ok",)]:
        raise RuntimeError(f"Backup PRAGMA integrity_check failed: {integ}")

    # In SQLite, PRAGMA foreign_key_check checks the entire DB.
    # We verify that NONE of our target tasks or approvals have FK violations.
    cur.execute("PRAGMA foreign_key_check(approvals)")
    fk_approvals = cur.fetchall()
    target_fk_violations = [r for r in fk_approvals if r[1] in [a for a in TARGET_APPROVALS]]
    if target_fk_violations:
        raise RuntimeError(f"Target approvals FK check failed: {target_fk_violations}")

    # Check key table counts match live source
    src_verify = sqlite3.connect(src_db)
    src_cur = src_verify.cursor()
    counts = {}
    for tbl in ["tasks", "approvals", "events", "artifacts", "checkpoints", "writes", "task_queue"]:
        src_cur.execute(f"SELECT count(*) FROM {tbl}")
        s_cnt = src_cur.fetchone()[0]
        cur.execute(f"SELECT count(*) FROM {tbl}")
        b_cnt = cur.fetchone()[0]
        if s_cnt != b_cnt:
            raise RuntimeError(f"Table count mismatch for {tbl}: source={s_cnt}, backup={b_cnt}")
        counts[tbl] = s_cnt

    # Verify all target tasks & approvals exist in backup
    for tid in TARGET_TASKS:
        cur.execute("SELECT status FROM tasks WHERE task_id = ?", (tid,))
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"Task {tid} missing from backup!")

    for aid in TARGET_APPROVALS:
        cur.execute("SELECT status FROM approvals WHERE approval_id = ?", (aid,))
        row = cur.fetchone()
        if not row or row[0] != "PENDING":
            raise RuntimeError(f"Approval {aid} missing or not PENDING in backup!")

    src_verify.close()
    verify_conn.close()

    file_bytes = backup_file.read_bytes()
    file_sha256 = hashlib.sha256(file_bytes).hexdigest()
    file_size = len(file_bytes)

    print(f"Backup successfully verified! Size: {file_size} bytes, SHA256: {file_sha256}")
    return {
        "path": str(backup_file),
        "size": file_size,
        "sha256": file_sha256,
        "counts": counts,
    }


def execute_recovery(execute: bool = False):
    print("=" * 60)
    print(f"AgentOS Administrative Recovery — Mode: {'EXECUTE' if execute else 'DRY-RUN'}")
    print("=" * 60)

    # 1. Backup before any connection to db session
    backup_meta = perform_verified_backup()

    # 2. Open session for atomic transaction
    with get_db_session() as session:
        # Precondition 1: Check blocking tasks in session
        current_blockers = blocking_workspace_task_ids_session(session)
        print("Pre-recovery blocking tasks in DB:", current_blockers)
        if sorted(current_blockers) != sorted(TARGET_TASKS):
            raise RuntimeError(
                f"Precondition failed: Expected blockers {sorted(TARGET_TASKS)}, but found {sorted(current_blockers)}"
            )

        now_utc = datetime.datetime.now(datetime.timezone.utc)

        # Precondition 2: Verify each target task status and transition
        tasks_to_update = session.query(TaskModel).filter(TaskModel.task_id.in_(TARGET_TASKS)).all()
        if len(tasks_to_update) != len(TARGET_TASKS):
            raise RuntimeError(f"Expected {len(TARGET_TASKS)} tasks in DB, found {len(tasks_to_update)}")

        for task in tasks_to_update:
            if task.task_id == "ebe2fb34-4ed9-44af-9111-081e44c56921":
                if task.status != TaskStatus.PLANNING.value:
                    raise RuntimeError(f"Task {task.task_id} expected PLANNING, found {task.status}")
            else:
                if task.status != TaskStatus.WAITING_APPROVAL.value:
                    raise RuntimeError(f"Task {task.task_id} expected WAITING_APPROVAL, found {task.status}")

            print(f"Updating Task {task.task_id}: {task.status} -> CANCELLED")
            task.status = TaskStatus.CANCELLED.value
            task.completed_at = now_utc

            # Immutable audit event in same session
            event = EventModel(
                event_id=str(uuid.uuid4()),
                task_id=task.task_id,
                timestamp=now_utc,
                event_type="admin.task.cancelled",
                step_id="admin_recovery",
                payload={
                    "previous_status": "PLANNING" if task.task_id == "ebe2fb34-4ed9-44af-9111-081e44c56921" else "WAITING_APPROVAL",
                    "new_status": "CANCELLED",
                    "actor": "system.admin.recovery",
                    "reason": "Administrative workspace recovery: session abandoned in prior run",
                },
            )
            session.add(event)

            # Audit log record in same session
            audit = AuditLogModel(
                log_id=str(uuid.uuid4()),
                user_id="system.admin.recovery",
                user_role="ADMIN",
                action="ADMIN_WORKSPACE_RECOVERY",
                target_entity="task",
                target_id=task.task_id,
                client_ip="127.0.0.1",
                status="SUCCESS",
                details={"reason": "Administrative workspace recovery", "previous_status": event.payload["previous_status"]},
                created_at=now_utc,
            )
            session.add(audit)

        # Precondition 3: Verify approvals and transition to REJECTED
        approvals_to_update = session.query(ApprovalModel).filter(ApprovalModel.approval_id.in_(TARGET_APPROVALS)).all()
        if len(approvals_to_update) != len(TARGET_APPROVALS):
            raise RuntimeError(f"Expected {len(TARGET_APPROVALS)} approvals in DB, found {len(approvals_to_update)}")

        for appr in approvals_to_update:
            if appr.status != ApprovalStatus.PENDING.value:
                raise RuntimeError(f"Approval {appr.approval_id} expected PENDING, found {appr.status}")

            print(f"Updating Approval {appr.approval_id}: PENDING -> REJECTED")
            appr.status = ApprovalStatus.REJECTED.value
            appr.resolved_at = now_utc
            appr.resolved_by = "system.admin.recovery"
            appr.resolution_reason = "Administrative workspace recovery: stale unmanaged session cancelled to release workspace lock"

            # Immutable audit event in same session
            event = EventModel(
                event_id=str(uuid.uuid4()),
                task_id=appr.task_id,
                timestamp=now_utc,
                event_type="admin.approval.rejected",
                step_id="admin_recovery",
                payload={
                    "approval_id": appr.approval_id,
                    "decision": "REJECTED",
                    "approved": False,
                    "actor": "system.admin.recovery",
                    "administrative": True,
                    "reason": appr.resolution_reason,
                },
            )
            session.add(event)

        # Flush changes to the transaction buffer before querying blockers
        session.flush()

        # Post-condition check inside session before commit
        post_blockers = blocking_workspace_task_ids_session(session)
        print("In-session post-update blocking tasks:", post_blockers)
        if post_blockers != []:
            raise RuntimeError(f"Post-condition failed: blocking tasks remaining in session: {post_blockers}")

        if not execute:
            session.rollback()
            print("\nDRY-RUN SUCCESSFUL: All preconditions verified. Changes rolled back. No database records modified.")
        else:
            session.commit()
            print("\nTRANSACTION COMMITTED: State updated successfully.")

    return backup_meta


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AgentOS Phase 1 Recovery")
    parser.add_argument("--execute", action="store_true", help="Execute mutations (defaults to dry-run)")
    args = parser.parse_args()

    execute_recovery(execute=args.execute)
