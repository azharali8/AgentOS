"""
Patch System Models for AgentOS Phase 3.

All patch data flows through these strongly-typed Pydantic models.
No mutation of source files occurs until a Patch has been:
  1. Parsed into these models by PatchGenerator
  2. Validated by PatchValidator (path bounds, hash, diff sanity)
  3. Cryptographically approved by ApprovalManager
  4. Applied by PatchApplier with pre-patch snapshot saved first

The patch_hash is the canonical identifier — it is the SHA-256 of the
serialized unified diff content.  It is computed by PatchValidator and
must be re-verified by PatchApplier before any file is written.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class PatchStatus(str, Enum):
    PENDING = "PENDING"        # Generated, not yet validated
    VALIDATED = "VALIDATED"    # Passed validator checks
    APPROVED = "APPROVED"      # Human approved
    APPLIED = "APPLIED"        # Applied to disk
    ROLLED_BACK = "ROLLED_BACK"
    REJECTED = "REJECTED"      # Human rejected
    FAILED = "FAILED"          # Application failed


class PatchHunk(BaseModel):
    """A single contiguous change block within a file."""

    original_start: int         # 1-indexed original file start line
    original_count: int         # Number of lines from original
    new_start: int              # 1-indexed new file start line
    new_count: int              # Number of lines in new version
    lines: list[str]            # Raw hunk lines (prefixed with +, -, or space)

    @field_validator("lines")
    @classmethod
    def lines_must_have_prefix(cls, v: list[str]) -> list[str]:
        for line in v:
            if line and line[0] not in ("+", "-", " ", "\\"):
                raise ValueError(
                    f"Hunk line must start with +, -, space, or \\\\ (got {line!r})"
                )
        return v


class PatchFile(BaseModel):
    """Represents changes to a single file within a patch."""

    relative_path: str          # POSIX path relative to WORKSPACE_ROOT
    original_hash: Optional[str] = None  # SHA-256 of original file content (hex)
    hunks: list[PatchHunk] = Field(default_factory=list)
    is_new_file: bool = False   # True if the file is being created
    is_deleted_file: bool = False  # True if the file is being deleted

    @property
    def lines_added(self) -> int:
        return sum(
            1 for h in self.hunks for line in h.lines if line.startswith("+")
        )

    @property
    def lines_removed(self) -> int:
        return sum(
            1 for h in self.hunks for line in h.lines if line.startswith("-")
        )


class Patch(BaseModel):
    """Complete patch proposed by the LLM and passed through the approval pipeline."""

    patch_id: str                              # UUID set by PatchGenerator
    task_id: str
    description: str                           # Human-readable summary of change
    files: list[PatchFile] = Field(default_factory=list)
    patch_hash: Optional[str] = None          # SHA-256 of canonical diff content; set by PatchValidator
    status: PatchStatus = PatchStatus.PENDING
    approval_id: Optional[str] = None         # Set after ApprovalManager records it

    @property
    def total_lines_added(self) -> int:
        return sum(f.lines_added for f in self.files)

    @property
    def total_lines_removed(self) -> int:
        return sum(f.lines_removed for f in self.files)

    @property
    def changed_files(self) -> list[str]:
        return [f.relative_path for f in self.files]


class PatchValidationResult(BaseModel):
    """Result of PatchValidator.validate()."""

    valid: bool
    patch_hash: Optional[str] = None    # Only set if valid
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0
    files_changed: int = 0


class PatchRollbackRecord(BaseModel):
    """Persistent record of pre-patch file snapshots for rollback."""

    patch_id: str
    task_id: str
    patch_hash: str
    snapshots: dict[str, str]           # relative_path → original file content
    original_hashes: dict[str, str]     # relative_path → SHA-256 of original content
    post_patch_hashes: dict[str, str]   # relative_path → SHA-256 after patch applied
    created_at: str                     # ISO 8601 UTC


def compute_file_hash(content: str | bytes) -> str:
    """Compute SHA-256 hash of file content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def compute_patch_hash(patch: Patch) -> str:
    """Compute a stable SHA-256 hash of the patch's canonical diff content.

    The hash binds:
    - task_id
    - Each file's relative_path, original_hash, and hunk lines
    Sorted deterministically so hash is order-independent across serializations.
    """
    canonical: list[dict] = []
    for pf in sorted(patch.files, key=lambda f: f.relative_path):
        file_entry: dict = {
            "relative_path": pf.relative_path,
            "original_hash": pf.original_hash,
            "is_new_file": pf.is_new_file,
            "is_deleted_file": pf.is_deleted_file,
            "hunks": [
                {
                    "original_start": h.original_start,
                    "original_count": h.original_count,
                    "new_start": h.new_start,
                    "new_count": h.new_count,
                    "lines": h.lines,
                }
                for h in pf.hunks
            ],
        }
        canonical.append(file_entry)

    payload = json.dumps(
        {"task_id": patch.task_id, "files": canonical},
        sort_keys=True,
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
