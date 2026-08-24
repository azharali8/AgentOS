"""
AgentOS Phase 13 — Immutable Artifact Service.

Provides cryptographically verifiable and immutable artifact management:
- Plan, Patch, Test Report, Review, Diagnosis, Security Findings, Trace, Summary.
- SHA-256 content hashing at write-time.
- Mandatory integrity verification on read-time (detects tampering/corruption).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.app.db.database import get_db_session
from backend.app.db.models import ArtifactModel

logger = logging.getLogger("agentos.artifact_service")


class ArtifactType(str, Enum):
    PLAN = "PLAN"
    PATCH = "PATCH"
    TEST_REPORT = "TEST_REPORT"
    REVIEW = "REVIEW"
    DIAGNOSIS = "DIAGNOSIS"
    SECURITY_FINDINGS = "SECURITY_FINDINGS"
    CONTEXT = "CONTEXT"
    EXECUTION_TRACE = "EXECUTION_TRACE"
    FINAL_SUMMARY = "FINAL_SUMMARY"
    DEVOPS_ANALYSIS = "DEVOPS_ANALYSIS"
    DATA_PROFILE = "DATA_PROFILE"


class ArtifactIntegrityError(Exception):
    """Raised when an artifact's content does not match its stored cryptographic SHA-256 hash."""
    pass


class Artifact(BaseModel):
    artifact_id: str
    task_id: str
    agent_id: str
    artifact_type: ArtifactType
    content_hash: str
    content: Dict[str, Any]
    provenance: Optional[Dict[str, Any]] = None
    created_at: datetime


def compute_content_hash(content: Dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash for JSON-serializable content dict."""
    canonical_json = json.dumps(content, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class ArtifactService:
    """Immutable, tamper-evident artifact repository."""

    @classmethod
    def save(
        cls,
        task_id: str,
        agent_id: str,
        artifact_type: ArtifactType,
        content: Dict[str, Any],
        provenance: Optional[Dict[str, Any]] = None,
        artifact_id: Optional[str] = None,
    ) -> Artifact:
        """Create and store an immutable artifact with SHA-256 content hash."""
        aid = artifact_id or str(uuid.uuid4())
        content_hash = compute_content_hash(content)
        now = datetime.now(timezone.utc)

        with get_db_session() as session:
            model = ArtifactModel(
                artifact_id=aid,
                task_id=task_id,
                agent_id=agent_id,
                artifact_type=artifact_type.value if hasattr(artifact_type, "value") else str(artifact_type),
                content_hash=content_hash,
                content_json=content,
                provenance=provenance or {},
                created_at=now,
            )
            session.add(model)
            session.commit()

        logger.info("Saved artifact %s [%s] for task %s (hash=%s)", aid, artifact_type, task_id, content_hash[:8])
        return Artifact(
            artifact_id=aid,
            task_id=task_id,
            agent_id=agent_id,
            artifact_type=ArtifactType(artifact_type) if isinstance(artifact_type, str) else artifact_type,
            content_hash=content_hash,
            content=content,
            provenance=provenance,
            created_at=now,
        )

    @classmethod
    def get(cls, artifact_id: str) -> Optional[Artifact]:
        """Fetch artifact and cryptographically verify content integrity."""
        with get_db_session() as session:
            model = session.query(ArtifactModel).filter(ArtifactModel.artifact_id == artifact_id).first()
            if not model:
                return None

            # Read-time cryptographic tamper verification
            computed_hash = compute_content_hash(model.content_json)
            if computed_hash != model.content_hash:
                err_msg = (
                    f"CRITICAL INTEGRITY FAILURE: Artifact {artifact_id} hash mismatch! "
                    f"Stored: {model.content_hash}, Computed: {computed_hash}. Artifact has been corrupted or tampered."
                )
                logger.critical(err_msg)
                raise ArtifactIntegrityError(err_msg)

            return Artifact(
                artifact_id=model.artifact_id,
                task_id=model.task_id,
                agent_id=model.agent_id,
                artifact_type=ArtifactType(model.artifact_type),
                content_hash=model.content_hash,
                content=model.content_json,
                provenance=model.provenance,
                created_at=model.created_at,
            )

    @classmethod
    def list_by_task(cls, task_id: str) -> List[Artifact]:
        """List all artifacts generated for a given task, verifying each on read."""
        with get_db_session() as session:
            models = session.query(ArtifactModel).filter(ArtifactModel.task_id == task_id).order_by(ArtifactModel.created_at.asc()).all()
            artifacts: List[Artifact] = []
            for m in models:
                computed_hash = compute_content_hash(m.content_json)
                if computed_hash != m.content_hash:
                    raise ArtifactIntegrityError(f"Artifact {m.artifact_id} failed integrity verification.")
                artifacts.append(
                    Artifact(
                        artifact_id=m.artifact_id,
                        task_id=m.task_id,
                        agent_id=m.agent_id,
                        artifact_type=ArtifactType(m.artifact_type),
                        content_hash=m.content_hash,
                        content=m.content_json,
                        provenance=m.provenance,
                        created_at=m.created_at,
                    )
                )
            return artifacts
