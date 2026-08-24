"""
AgentOS Phase 14 — Database Backup, Verify & Restore CLI.

Provides:
- Timestamped SQLite backup via the safe sqlite3.backup() API
- SHA-256 checksum stored alongside backup for tamper-detection
- PRAGMA integrity_check on both create and verify
- Functional restore: writes back to live DB path + verifies basic table queries
- CLI interface:  python -m backend.app.services.backup_service [create|verify|restore] [--path <backup>]

Phase 14 guarantees:
- A restore actually produces a functional AgentOS instance, not merely a file copy.
- Checksums detect file corruption or tampering before restore is performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.config.settings import settings

logger = logging.getLogger("agentos.backup")


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest for file at *path*."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class BackupService:
    """Manages secure timestamped backups and restores of the SQLite database."""

    @staticmethod
    def _db_path() -> Path:
        return Path(settings.DATABASE_URL.replace("sqlite:///", ""))

    @staticmethod
    def get_backup_dir() -> Path:
        db_path = Path(settings.DATABASE_URL.replace("sqlite:///", ""))
        base_dir = db_path.parent / "backups"
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    @classmethod
    def create_backup(cls) -> Dict[str, Any]:
        """Create a timestamped, checksummed copy of the active SQLite database."""
        db_path = cls._db_path()
        if not db_path.exists():
            return {"success": False, "error": "Active database file does not exist."}

        backup_dir = cls.get_backup_dir()
        ts = int(time.time())
        backup_file = backup_dir / f"agentos_backup_{ts}.db"
        checksum_file = backup_dir / f"agentos_backup_{ts}.sha256"

        try:
            # Safe online backup using sqlite3 backup API (works while DB is open)
            src_conn = sqlite3.connect(str(db_path))
            dst_conn = sqlite3.connect(str(backup_file))
            src_conn.backup(dst_conn)
            dst_conn.close()
            src_conn.close()

            # Verify structural integrity of backup
            verify_conn = sqlite3.connect(str(backup_file))
            result = verify_conn.execute("PRAGMA integrity_check").fetchone()
            verify_conn.close()

            if not result or result[0] != "ok":
                backup_file.unlink(missing_ok=True)
                return {"success": False, "error": "Backup integrity_check failed — backup discarded."}

            # Store SHA-256 checksum
            checksum = _sha256_file(backup_file)
            checksum_file.write_text(f"{checksum}  {backup_file.name}\n")

            size_bytes = backup_file.stat().st_size
            logger.info("Backup created: %s  checksum=%s  size=%d", backup_file, checksum, size_bytes)
            return {
                "success": True,
                "backup_path": str(backup_file),
                "checksum": checksum,
                "timestamp": ts,
                "size_bytes": size_bytes,
            }
        except Exception as exc:
            logger.error("Backup creation failed: %s", exc, exc_info=True)
            backup_file.unlink(missing_ok=True)
            checksum_file.unlink(missing_ok=True)
            return {"success": False, "error": str(exc)}

    @classmethod
    def verify_backup(cls, backup_path: str) -> Dict[str, Any]:
        """
        Verify backup integrity:
        1. SHA-256 checksum match against stored .sha256 file
        2. SQLite PRAGMA integrity_check
        """
        p = Path(backup_path)
        if not p.exists():
            return {"success": False, "error": "Backup file not found."}

        checksum_file = p.with_suffix(".sha256")
        if checksum_file.exists():
            stored_line = checksum_file.read_text().strip().split()[0]
            actual = _sha256_file(p)
            if actual != stored_line:
                return {
                    "success": False,
                    "error": "Checksum mismatch — backup may be corrupted or tampered.",
                    "expected": stored_line,
                    "actual": actual,
                }
        else:
            logger.warning("No .sha256 file found for backup %s — skipping checksum verification.", p.name)

        try:
            conn = sqlite3.connect(str(p))
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            if not result or result[0] != "ok":
                return {"success": False, "error": "PRAGMA integrity_check failed."}
            return {"success": True, "backup_path": str(p), "integrity": "ok"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @classmethod
    def restore_backup(cls, backup_path: str) -> Dict[str, Any]:
        """
        Restore database from backup:
        1. Verify checksum + integrity first
        2. Write to live DB path
        3. Run functional verification — confirm tables exist and are queryable
        """
        verify = cls.verify_backup(backup_path)
        if not verify["success"]:
            return {"success": False, "error": f"Pre-restore verification failed: {verify.get('error')}"}

        p = Path(backup_path)
        target = cls._db_path()

        # Preserve current DB as emergency snapshot before overwrite
        emergency = target.parent / f"pre_restore_emergency_{int(time.time())}.db"
        try:
            if target.exists():
                shutil.copy2(target, emergency)
        except Exception as exc:
            logger.warning("Could not create emergency snapshot: %s", exc)

        try:
            # Perform restore
            shutil.copy2(p, target)

            # Functional verification: confirm core tables are readable
            conn = sqlite3.connect(str(target))
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            conn.close()

            expected_tables = {"tasks", "events", "executions"}
            found = expected_tables.intersection(set(tables))
            missing = expected_tables - found


            if missing:
                # Rollback to emergency snapshot
                if emergency.exists():
                    shutil.copy2(emergency, target)
                return {
                    "success": False,
                    "error": f"Restore functional check failed — missing tables: {missing}. Original DB restored.",
                }

            logger.info("Restore from %s completed. Functional check passed. Tables: %s", p.name, tables)
            # Clean up emergency snapshot after successful restore
            emergency.unlink(missing_ok=True)
            return {
                "success": True,
                "restored_from": str(p),
                "tables_verified": list(found),
                "all_tables": tables,
            }
        except Exception as exc:
            # Attempt rollback
            try:
                if emergency.exists():
                    shutil.copy2(emergency, target)
            except Exception:
                pass
            logger.error("Restore failed: %s", exc, exc_info=True)
            return {"success": False, "error": str(exc)}

    @classmethod
    def list_backups(cls) -> List[str]:
        backup_dir = cls.get_backup_dir()
        return [str(p) for p in sorted(backup_dir.glob("*.db"), reverse=True)]


# ─────────────────────────────────────────────────────────────────────────────
# CLI Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """
    CLI interface for backup management.

    Usage:
        python -m backend.app.services.backup_service create
        python -m backend.app.services.backup_service verify  --path <backup.db>
        python -m backend.app.services.backup_service restore --path <backup.db>
        python -m backend.app.services.backup_service list
    """
    parser = argparse.ArgumentParser(
        description="AgentOS Backup Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", choices=["create", "verify", "restore", "list"],
                        help="Backup operation to perform")
    parser.add_argument("--path", help="Path to backup file (required for verify/restore)")
    args = parser.parse_args()

    result: Any = None

    if args.command == "create":
        result = BackupService.create_backup()
    elif args.command == "verify":
        if not args.path:
            print("[ERROR] --path is required for 'verify'", file=sys.stderr)
            sys.exit(1)
        result = BackupService.verify_backup(args.path)
    elif args.command == "restore":
        if not args.path:
            print("[ERROR] --path is required for 'restore'", file=sys.stderr)
            sys.exit(1)
        result = BackupService.restore_backup(args.path)
    elif args.command == "list":
        backups = BackupService.list_backups()
        if not backups:
            print("No backups found.")
        else:
            for b in backups:
                print(b)
        sys.exit(0)

    print(json.dumps(result, indent=2))
    if result and not result.get("success", True):
        sys.exit(1)


if __name__ == "__main__":
    main()
