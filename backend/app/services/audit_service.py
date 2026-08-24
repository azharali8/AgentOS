"""
AgentOS Phase 13 — Administrative & Security Audit Service.

Records immutable audit entries for:
- User Authentication (Login, Logout, Token Refresh, Auth Denials)
- Task Control (Creation, Pause, Resume, Two-Phase Cancellation)
- Human Approvals (Granted, Rejected, Overridden)
- Security Interceptions (Path traversal, Sensitive file access, Role violations)
- Configuration & Model Changes
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from backend.app.db.database import get_db_session
from backend.app.db.models import AuditLogModel
from backend.app.observability.redaction import redact_secrets

logger = logging.getLogger("agentos.audit_service")


class AuditEntry(BaseModel):
    log_id: str
    user_id: Optional[str]
    user_role: Optional[str]
    action: str
    target_entity: Optional[str]
    target_id: Optional[str]
    client_ip: Optional[str]
    status: str
    details: Dict[str, Any]
    created_at: datetime


class AuditService:
    """Central append-only administrative security audit service."""

    @classmethod
    def record(
        cls,
        action: str,
        status: str,
        user_id: Optional[str] = None,
        user_role: Optional[str] = None,
        target_entity: Optional[str] = None,
        target_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Write an immutable audit log record."""
        log_id = str(uuid.uuid4())
        safe_details = redact_secrets(details or {})
        now = datetime.now(timezone.utc)

        with get_db_session() as session:
            model = AuditLogModel(
                log_id=log_id,
                user_id=user_id,
                user_role=user_role,
                action=action,
                target_entity=target_entity,
                target_id=target_id,
                client_ip=client_ip,
                status=status,
                details=safe_details,
                created_at=now,
            )
            session.add(model)
            session.commit()

        logger.info(
            "AUDIT LOG: [%s] action='%s' user='%s' target='%s/%s' status='%s'",
            log_id[:8], action, user_id or "system", target_entity, target_id, status
        )
        return log_id

    @classmethod
    def list_logs(
        cls,
        limit: int = 50,
        offset: int = 0,
        action: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[AuditEntry]:
        """Fetch audit log records for administrative review."""
        with get_db_session() as session:
            q = session.query(AuditLogModel)
            if action:
                q = q.filter(AuditLogModel.action == action)
            if user_id:
                q = q.filter(AuditLogModel.user_id == user_id)
            models = q.order_by(AuditLogModel.created_at.desc()).offset(offset).limit(limit).all()

            return [
                AuditEntry(
                    log_id=m.log_id,
                    user_id=m.user_id,
                    user_role=m.user_role,
                    action=m.action,
                    target_entity=m.target_entity,
                    target_id=m.target_id,
                    client_ip=m.client_ip,
                    status=m.status,
                    details=m.details or {},
                    created_at=m.created_at,
                )
                for m in models
            ]
