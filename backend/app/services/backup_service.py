"""
AgentOS Phase 6 — Database & Event Backup and Recovery Service.

Supports:
- Timestamped SQLite database backup
- Integrity verification using SQLite pragma
- Backup validation and restore
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

from backend.app.config.settings import settings

logger = logging.getLogger("agentos.backup")


class BackupService:
    """Manages secure timestamped backups and restores of the database."""

    @staticmethod
    def get_backup_dir() -> Path:
        db_path = settings.DATABASE_URL.replace("sqlite:///", "")
        base_dir = Path(db_path).parent / "backups"
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    @classmethod
    def create_backup(cls) -> Dict[str, Any]:
        """Create a timestamped copy of the active SQLite database."""
        db_path_str = settings.DATABASE_URL.replace("sqlite:///", "")
        db_path = Path(db_path_str)

        if not db_path.exists():
            return {"success": False, "error": "Active database file does not exist."}

        backup_dir = cls.get_backup_dir()
        ts = int(time.time())
        backup_file = backup_dir / f"agentos_backup_{ts}.db"

        # Safe copy using sqlite backup API
        try:
            src_conn = sqlite3.connect(str(db_path))
            dst_conn = sqlite3.connect(str(backup_file))
            src_conn.backup(dst_conn)
            dst_conn.close()
            src_conn.close()

            # Verify integrity
            verify_conn = sqlite3.connect(str(backup_file))
            cursor = verify_conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            check_res = cursor.fetchone()
            verify_conn.close()

            if not check_res or check_res[0] != "ok":
                backup_file.unlink(missing_ok=True)
                return {"success": False, "error": "Backup integrity verification failed."}

            return {
                "success": True,
                "backup_path": str(backup_file),
                "timestamp": ts,
                "size_bytes": backup_file.stat().st_size,
            }
        except Exception as exc:
            logger.error("Backup creation failed: %s", exc, exc_info=True)
            return {"success": False, "error": str(exc)}

    @classmethod
    def list_backups(cls) -> List[str]:
        backup_dir = cls.get_backup_dir()
        return [str(p) for p in sorted(backup_dir.glob("*.db"), reverse=True)]

    @classmethod
    def restore_backup(cls, backup_path: str) -> Dict[str, Any]:
        """Restore database from backup after verifying integrity."""
        p = Path(backup_path)
        if not p.exists():
            return {"success": False, "error": "Backup file not found."}

        try:
            # Check integrity of backup before copying
            conn = sqlite3.connect(str(p))
            res = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            if not res or res[0] != "ok":
                return {"success": False, "error": "Backup corrupted, restore aborted."}

            db_path_str = settings.DATABASE_URL.replace("sqlite:///", "")
            target = Path(db_path_str)
            shutil.copy2(p, target)
            return {"success": True, "restored_from": str(p)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
