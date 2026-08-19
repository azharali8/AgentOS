import hashlib
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import uuid

from backend.app.models.approval import ApprovalRequest, ApprovalStatus
from backend.app.db.database import get_db_session
from backend.app.db.models import ApprovalModel
from backend.app.db.repositories.approval_repository import ApprovalRepository

class ApprovalManager:

    @staticmethod
    def _compute_hash(task_id: str, step_id: str, tool_name: str, operation: str, arguments: Dict[str, Any]) -> str:
        # Sort keys to ensure deterministic hashing
        args_str = json.dumps(arguments, sort_keys=True)
        raw = f"{task_id}:{step_id}:{tool_name}:{operation}:{args_str}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    @classmethod
    def request_approval(cls, request: ApprovalRequest) -> str:
        # compute deterministic hash for integrity verification
        arg_hash = cls._compute_hash(
            request.task_id, 
            request.step_id, 
            request.tool_name, 
            request.operation, 
            request.arguments_summary
        )
        
        with get_db_session() as session:
            repo = ApprovalRepository(session)
            # Idempotency: if an approval with this ID already exists (e.g., due to
            # LangGraph node replay on resume), skip the insert and return existing ID.
            existing = repo.get_by_id(request.approval_id)
            if existing is not None:
                return request.approval_id
            model = ApprovalModel(
                approval_id=request.approval_id,
                task_id=request.task_id,
                step_id=request.step_id,
                tool_name=request.tool_name,
                operation=request.operation,
                arguments_hash=arg_hash,
                arguments_summary=request.arguments_summary,
                risk_level=request.risk_level.value,
                status=ApprovalStatus.PENDING.value,
                resolution_reason=request.reason,
            )
            repo.create(model)
        
        return request.approval_id
        
    @classmethod
    def get_approval(cls, approval_id: str) -> Optional[ApprovalRequest]:
        with get_db_session() as session:
            repo = ApprovalRepository(session)
            model = repo.get_by_id(approval_id)
            if not model:
                return None
                
            from backend.app.models.tool import RiskLevel
            return ApprovalRequest(
                approval_id=model.approval_id,
                task_id=model.task_id,
                step_id=model.step_id,
                tool_name=model.tool_name,
                operation=model.operation,
                arguments_hash=model.arguments_hash,
                arguments_summary=model.arguments_summary,
                risk_level=RiskLevel(model.risk_level),
                reason=model.resolution_reason or "",
                status=ApprovalStatus(model.status),
                created_at=model.created_at.replace(tzinfo=timezone.utc),
                resolved_at=model.resolved_at.replace(tzinfo=timezone.utc) if model.resolved_at else None,
                resolved_by=model.resolved_by
            )

    @classmethod
    def resolve_approval(cls, approval_id: str, status: ApprovalStatus, reason: str = "", resolved_by: str = "system") -> bool:
        with get_db_session() as session:
            repo = ApprovalRepository(session)
            model = repo.get_by_id(approval_id)
            if model and model.status == ApprovalStatus.PENDING.value:
                model.status = status.value
                model.resolution_reason = reason
                model.resolved_at = datetime.now(timezone.utc)
                model.resolved_by = resolved_by
                repo.update(model)
                return True
        return False
        
    @classmethod
    def verify_request(cls, approval_id: str, task_id: str, step_id: str, tool_name: str, operation: str, arguments: Dict[str, Any]) -> bool:
        """Verify the resumed request matches the originally approved request."""
        model = cls.get_approval(approval_id)
        if not model:
            return False
            
        expected_hash = cls._compute_hash(task_id, step_id, tool_name, operation, arguments)
        
        return (
            model.task_id == task_id and
            model.step_id == step_id and
            model.arguments_hash == expected_hash
        )

    @classmethod
    def list_approvals(cls, limit: int = 20, offset: int = 0) -> List[ApprovalRequest]:
        with get_db_session() as session:
            repo = ApprovalRepository(session)
            models = repo.list_approvals(limit, offset)
            from backend.app.models.tool import RiskLevel
            
            res = []
            for model in models:
                res.append(ApprovalRequest(
                    approval_id=model.approval_id,
                    task_id=model.task_id,
                    step_id=model.step_id,
                    tool_name=model.tool_name,
                    operation=model.operation,
                    arguments_hash=model.arguments_hash,
                    arguments_summary=model.arguments_summary,
                    risk_level=RiskLevel(model.risk_level),
                    reason=model.resolution_reason or "",
                    status=ApprovalStatus(model.status),
                    created_at=model.created_at.replace(tzinfo=timezone.utc),
                    resolved_at=model.resolved_at.replace(tzinfo=timezone.utc) if model.resolved_at else None,
                    resolved_by=model.resolved_by
                ))
            return res
