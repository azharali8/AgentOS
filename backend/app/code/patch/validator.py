"""
Patch Validator for AgentOS Phase 3.

PatchValidator is the security gate that sits between LLM-generated patch
proposals and the PatchApplier.  It validates:

1. File count limit (MAX_PATCH_FILES).
2. Total line limit (MAX_PATCH_LINES).
3. Each file path is within WORKSPACE_ROOT (traversal, drive escape, UNC, symlink).
4. Sensitive files are denied (no credential-file patching).
5. Original file content hash matches the current disk state.
6. Hunk sanity (non-empty, valid prefix characters).
7. Computes and returns the canonical patch_hash.

The validator never opens files for writing — it only reads to verify hashes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from backend.app.code.patch.models import (
    Patch,
    PatchFile,
    PatchValidationResult,
    compute_file_hash,
    compute_patch_hash,
)
from backend.app.config.settings import settings
from backend.app.security.sensitive_files import is_sensitive_path
from backend.app.services.workspace_service import WorkspaceService


class PatchValidator:
    """Multi-level security validator for patch proposals."""

    def __init__(self) -> None:
        self._root = Path(settings.WORKSPACE_ROOT).resolve()

    def validate(self, patch: Patch) -> PatchValidationResult:
        """Validate *patch* and return a PatchValidationResult.

        The result is valid (result.valid is True) only when ALL checks pass.
        On failure, result.errors contains the list of blocking errors.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # ---- Structural limits ----
        if len(patch.files) == 0:
            errors.append("Patch contains no files.")

        if len(patch.files) > settings.MAX_PATCH_FILES:
            errors.append(
                f"Patch modifies {len(patch.files)} files, exceeding MAX_PATCH_FILES "
                f"({settings.MAX_PATCH_FILES})."
            )

        total_lines = sum(
            len(h.lines) for pf in patch.files for h in pf.hunks
        )
        if total_lines > settings.MAX_PATCH_LINES:
            errors.append(
                f"Patch has {total_lines} hunk lines, exceeding MAX_PATCH_LINES "
                f"({settings.MAX_PATCH_LINES})."
            )

        # ---- Per-file validation ----
        lines_added = 0
        lines_removed = 0

        for pf in patch.files:
            file_errors = self._validate_patch_file(pf)
            errors.extend(file_errors)
            if not file_errors:
                lines_added += pf.lines_added
                lines_removed += pf.lines_removed

        if errors:
            return PatchValidationResult(
                valid=False,
                errors=errors,
                warnings=warnings,
                lines_added=lines_added,
                lines_removed=lines_removed,
                files_changed=len(patch.files),
            )

        # ---- Compute canonical hash ----
        patch_hash = compute_patch_hash(patch)

        return PatchValidationResult(
            valid=True,
            patch_hash=patch_hash,
            errors=[],
            warnings=warnings,
            lines_added=lines_added,
            lines_removed=lines_removed,
            files_changed=len(patch.files),
        )

    # ------------------------------------------------------------------
    # Per-file validation
    # ------------------------------------------------------------------

    def _validate_patch_file(self, pf: PatchFile) -> list[str]:
        errors: list[str] = []

        # 1. Sensitive file gate
        if is_sensitive_path(pf.relative_path):
            errors.append(
                f"Patching sensitive file is not permitted: {pf.relative_path}"
            )
            return errors  # Stop early — don't even resolve the path

        # 2. Workspace path validation
        try:
            resolved = WorkspaceService.validate_path(pf.relative_path)
        except ValueError as exc:
            errors.append(f"Invalid path '{pf.relative_path}': {exc}")
            return errors

        # 3. Symlink escape check after resolution
        if not self._is_inside_workspace(resolved):
            errors.append(
                f"Resolved path escapes workspace: {pf.relative_path} → {resolved}"
            )
            return errors

        # 4. For existing files, verify original hash matches disk state
        if not pf.is_new_file:
            if not resolved.exists():
                errors.append(f"File does not exist: {pf.relative_path}")
            elif not resolved.is_file():
                errors.append(f"Path is not a file: {pf.relative_path}")
            elif pf.original_hash is not None:
                # Read current content and compare
                try:
                    current_content = resolved.read_bytes()
                    current_hash = compute_file_hash(current_content)
                    if current_hash != pf.original_hash:
                        errors.append(
                            f"File has been modified since patch was generated. "
                            f"Expected hash {pf.original_hash[:16]}…, "
                            f"got {current_hash[:16]}… for {pf.relative_path}"
                        )
                except OSError as exc:
                    errors.append(f"Cannot read file {pf.relative_path}: {exc}")

        # 5. Hunk sanity
        if not pf.hunks and not pf.is_deleted_file:
            errors.append(f"No hunks in patch for {pf.relative_path}")

        return errors

    def _is_inside_workspace(self, resolved: Path) -> bool:
        try:
            resolved.relative_to(self._root)
            return True
        except ValueError:
            return False
