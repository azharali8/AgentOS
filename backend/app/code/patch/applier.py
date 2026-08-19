"""
Python-Native Patch Applier for AgentOS Phase 3.

PatchApplier applies a validated, approved Patch to disk using pure Python
hunk-application logic.  No external `patch` command is used; shell=False
is not even relevant here because no subprocess is invoked.

Safety guarantees
-----------------
* Re-validates patch_hash before writing any file.
* Re-reads and verifies original file hashes immediately before writing.
* Saves a PatchRollbackRecord with pre-patch snapshots to allow rollback.
* Rollback verifies post-patch hashes match expected before restoring.
* If rollback file hashes don't match (out-of-band modifications), rollback
  fails safely rather than silently overwriting unrelated changes.
* All paths go through WorkspaceService.validate_path() again at apply time.
* Sensitive files are re-checked at apply time (defence in depth).
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.app.code.patch.models import (
    Patch,
    PatchFile,
    PatchHunk,
    PatchRollbackRecord,
    PatchStatus,
    compute_file_hash,
    compute_patch_hash,
)
from backend.app.config.settings import settings
from backend.app.security.sensitive_files import is_sensitive_path
from backend.app.services.workspace_service import WorkspaceService


@dataclass
class ApplyResult:
    success: bool
    error: Optional[str] = None
    rollback_record: Optional[PatchRollbackRecord] = None
    files_written: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.files_written is None:
            self.files_written = []


@dataclass
class RollbackResult:
    success: bool
    error: Optional[str] = None
    files_restored: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.files_restored is None:
            self.files_restored = []


class PatchApplier:
    """Python-native patch applier with rollback support."""

    def __init__(self) -> None:
        self._root = Path(settings.WORKSPACE_ROOT).resolve()

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def apply(self, patch: Patch, expected_patch_hash: str) -> ApplyResult:
        """Apply *patch* to the workspace.

        Args:
            patch: The approved Patch object.
            expected_patch_hash: The hash that was approved.  Must match the
                                 computed hash of *patch* right now.

        Returns:
            ApplyResult indicating success/failure and rollback information.
        """
        # ---- 1. Re-verify patch hash (cannot have changed since approval) ----
        current_hash = compute_patch_hash(patch)
        if current_hash != expected_patch_hash:
            return ApplyResult(
                success=False,
                error=(
                    f"Patch hash mismatch: approved hash was {expected_patch_hash[:16]}…, "
                    f"current hash is {current_hash[:16]}…. "
                    "The patch may have been modified. Approval is invalid."
                ),
            )

        # ---- 2. Validate all paths and collect pre-patch snapshots ----
        snapshots: dict[str, str] = {}
        original_hashes: dict[str, str] = {}

        for pf in patch.files:
            # Re-check sensitive file gate
            if is_sensitive_path(pf.relative_path):
                return ApplyResult(
                    success=False,
                    error=f"Apply blocked: sensitive file {pf.relative_path}",
                )

            try:
                resolved = WorkspaceService.validate_path(pf.relative_path)
            except ValueError as exc:
                return ApplyResult(
                    success=False,
                    error=f"Path validation failed for {pf.relative_path}: {exc}",
                )

            if not pf.is_new_file:
                if not resolved.exists():
                    return ApplyResult(
                        success=False,
                        error=f"File no longer exists: {pf.relative_path}",
                    )
                try:
                    original_bytes = resolved.read_bytes()
                except OSError as exc:
                    return ApplyResult(
                        success=False,
                        error=f"Cannot read {pf.relative_path}: {exc}",
                    )

                current_file_hash = compute_file_hash(original_bytes)

                # Verify hash matches what was validated at approval time
                if pf.original_hash is not None and current_file_hash != pf.original_hash:
                    return ApplyResult(
                        success=False,
                        error=(
                            f"File {pf.relative_path} has been modified since approval. "
                            "Re-generate and re-approve the patch."
                        ),
                    )

                # Normalize to str with \n line endings for hunk application
                snapshots[pf.relative_path] = original_bytes.decode("utf-8", errors="replace").replace("\r\n", "\n")
                original_hashes[pf.relative_path] = current_file_hash

        # ---- 3. Apply each file's hunks ----
        applied_files: list[tuple[Path, str, str]] = []  # (resolved_path, rel, new_content)
        for pf in patch.files:
            resolved = WorkspaceService.validate_path(pf.relative_path)

            if pf.is_deleted_file:
                # Record for rollback; actual delete happens below
                applied_files.append((resolved, pf.relative_path, ""))
                continue

            if pf.is_new_file:
                # Construct new content from hunk additions
                new_content = _build_new_file_content(pf)
            else:
                original_text = snapshots[pf.relative_path].replace("\r\n", "\n")
                original_lines = original_text.splitlines(keepends=True)
                result, err = _apply_hunks(original_lines, pf.hunks)
                if err:
                    return ApplyResult(
                        success=False,
                        error=f"Hunk application failed for {pf.relative_path}: {err}",
                    )
                new_content = result

            applied_files.append((resolved, pf.relative_path, new_content))

        # ---- 4. Write to disk (after all validations pass) ----
        post_patch_hashes: dict[str, str] = {}
        files_written: list[str] = []

        for resolved, rel, new_content in applied_files:
            try:
                if new_content == "" and any(
                    pf.relative_path == rel and pf.is_deleted_file for pf in patch.files
                ):
                    resolved.unlink(missing_ok=True)
                    post_patch_hashes[rel] = ""
                else:
                    resolved.parent.mkdir(parents=True, exist_ok=True)
                    # Write with explicit \n (binary mode) to avoid platform CRLF issues
                    encoded = new_content.encode("utf-8")
                    resolved.write_bytes(encoded)
                    post_patch_hashes[rel] = compute_file_hash(encoded)
                files_written.append(rel)
            except OSError as exc:
                return ApplyResult(
                    success=False,
                    error=f"Failed to write {rel}: {exc}",
                )

        # ---- 5. Build rollback record ----
        rollback = PatchRollbackRecord(
            patch_id=patch.patch_id,
            task_id=patch.task_id,
            patch_hash=expected_patch_hash,
            snapshots=snapshots,
            original_hashes=original_hashes,
            post_patch_hashes=post_patch_hashes,
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

        return ApplyResult(
            success=True,
            rollback_record=rollback,
            files_written=files_written,
        )

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------

    def rollback(self, record: PatchRollbackRecord, task_id: str) -> RollbackResult:
        """Restore files to their pre-patch state using *record*.

        Args:
            record: The PatchRollbackRecord produced by apply().
            task_id: Must match record.task_id to prevent cross-task rollback.

        Returns:
            RollbackResult indicating success/failure.
        """
        # ---- 1. Ownership check ----
        if record.task_id != task_id:
            return RollbackResult(
                success=False,
                error=f"Task ID mismatch: record belongs to {record.task_id}, not {task_id}",
            )

        # ---- 2. Validate each path and verify current state matches post-patch ----
        for rel, expected_post_hash in record.post_patch_hashes.items():
            # Re-check sensitive file gate
            if is_sensitive_path(rel):
                return RollbackResult(
                    success=False,
                    error=f"Rollback blocked: sensitive file {rel}",
                )

            try:
                resolved = WorkspaceService.validate_path(rel)
            except ValueError as exc:
                return RollbackResult(
                    success=False,
                    error=f"Path validation failed for {rel}: {exc}",
                )

            if expected_post_hash == "":
                # File was deleted by patch — it should not exist now
                # (OK to proceed even if already absent)
                continue

            if resolved.exists():
                try:
                    current_bytes = resolved.read_bytes()
                    current_hash = compute_file_hash(current_bytes)
                except OSError as exc:
                    return RollbackResult(
                        success=False,
                        error=f"Cannot read {rel} for verification: {exc}",
                    )

                if current_hash != expected_post_hash:
                    return RollbackResult(
                        success=False,
                        error=(
                            f"File {rel} has been modified after the patch was applied. "
                            "Rollback aborted to prevent overwriting unrelated changes."
                        ),
                    )

        # ---- 3. Restore files ----
        restored: list[str] = []
        for rel, original_content in record.snapshots.items():
            try:
                resolved = WorkspaceService.validate_path(rel)
            except ValueError as exc:
                return RollbackResult(
                    success=False,
                    error=f"Path validation failed during restore of {rel}: {exc}",
                )

            try:
                resolved.parent.mkdir(parents=True, exist_ok=True)
                # Write as bytes to match the binary mode used during apply
                resolved.write_bytes(original_content.encode("utf-8"))
                restored.append(rel)
            except OSError as exc:
                return RollbackResult(
                    success=False,
                    error=f"Failed to restore {rel}: {exc}",
                )

        # Handle files that were newly created by the patch — delete them
        for rel, post_hash in record.post_patch_hashes.items():
            if rel not in record.snapshots and post_hash != "":
                # File was created by the patch — delete it
                try:
                    resolved = WorkspaceService.validate_path(rel)
                    resolved.unlink(missing_ok=True)
                    restored.append(rel)
                except (ValueError, OSError) as exc:
                    return RollbackResult(
                        success=False,
                        error=f"Failed to delete newly created file {rel}: {exc}",
                    )

        return RollbackResult(success=True, files_restored=restored)


# ---------------------------------------------------------------------------
# Hunk application logic
# ---------------------------------------------------------------------------

def _apply_hunks(
    original_lines: list[str],
    hunks: list[PatchHunk],
) -> tuple[str, Optional[str]]:
    """Apply unified diff hunks to *original_lines*.

    Returns:
        (new_content, None) on success.
        ("", error_message) on failure.
    """
    result_lines = list(original_lines)
    offset = 0  # Line offset accumulated from previous hunks

    for hunk in hunks:
        # Adjust for 0-indexed
        start = hunk.original_start - 1 + offset

        if start < 0 or start > len(result_lines):
            return "", (
                f"Hunk start line {hunk.original_start} (adjusted to {start}) "
                f"is out of range (file has {len(result_lines)} lines after previous hunks)"
            )

        # Separate the hunk into context/removed lines and added lines
        removed: list[str] = []
        added: list[str] = []

        for line in hunk.lines:
            if line.startswith(" "):
                removed.append(line[1:])
                added.append(line[1:])
            elif line.startswith("-"):
                removed.append(line[1:])
            elif line.startswith("+"):
                added.append(line[1:])
            # Ignore "\ No newline at end of file" lines

        # Verify that the lines we expect to remove are actually there
        expected_region = result_lines[start : start + len(removed)]
        if len(expected_region) != len(removed):
            return "", (
                f"Hunk context mismatch at line {hunk.original_start}: "
                f"expected {len(removed)} lines, found {len(expected_region)}"
            )
        for i, (expected, actual) in enumerate(zip(removed, expected_region)):
            # Strip line endings for comparison
            if expected.rstrip("\r\n") != actual.rstrip("\r\n"):
                return "", (
                    f"Hunk context mismatch at line {hunk.original_start + i}: "
                    f"expected {expected!r}, found {actual!r}"
                )

        # Replace the region
        # Ensure added lines end with \n
        normalized_added = [
            (line if line.endswith("\n") else line + "\n") for line in added
        ]
        result_lines[start : start + len(removed)] = normalized_added
        offset += len(added) - len(removed)

    return "".join(result_lines), None


def _build_new_file_content(pf: PatchFile) -> str:
    """Build new file content from a patch that creates a new file."""
    lines: list[str] = []
    for hunk in pf.hunks:
        for line in hunk.lines:
            if line.startswith("+"):
                content = line[1:]
                if not content.endswith("\n"):
                    content += "\n"
                lines.append(content)
    return "".join(lines)
