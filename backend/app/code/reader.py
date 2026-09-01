"""
Bounded Code Reader for AgentOS Phase 3.

Reads a window of lines from a file within WORKSPACE_ROOT.  All security
constraints from Phase 0 are preserved:

* Target path is validated against WORKSPACE_ROOT before opening.
* Sensitive files are denied unconditionally.
* Per-read line count is capped at MAX_LINES_PER_READ.
* Binary files return an error (no content exposed).
* File-size guard prevents opening huge files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from backend.app.code.scanner import _is_binary
from backend.app.config.settings import settings
from backend.app.security.sensitive_files import is_sensitive_path, sensitive_file_reason
from backend.app.services.workspace_service import WorkspaceService


@dataclass
class ReadResult:
    relative_path: str
    start_line: int                  # 1-indexed, actual start returned
    end_line: int                    # 1-indexed, actual end returned
    total_lines: int                 # total lines in file
    lines: list[str] = field(default_factory=list)  # content without trailing newlines
    truncated: bool = False
    truncation_reason: str = ""
    error: Optional[str] = None


class CodeReader:
    """Line-windowed code reader with workspace and sensitive-file protection."""

    @property
    def _root(self) -> Path:
        return Path(settings.WORKSPACE_ROOT).resolve()

    def read(
        self,
        relative_path: str,
        start_line: int = 1,
        end_line: Optional[int] = None,
    ) -> ReadResult:
        """Read *start_line* to *end_line* (both inclusive, 1-indexed).

        Args:
            relative_path: Path relative to WORKSPACE_ROOT.
            start_line: First line to return (1-indexed).  Defaults to 1.
            end_line: Last line to return (inclusive).  If omitted, reads up
                      to MAX_LINES_PER_READ lines from start_line.

        Returns:
            ReadResult with line content and metadata.

        Raises:
            ValueError: For workspace-escape or invalid path.
        """
        # --- Path validation ---
        target = WorkspaceService.validate_path(relative_path)
        rel_str = str(target.relative_to(self._root)).replace("\\", "/")

        result = ReadResult(
            relative_path=rel_str,
            start_line=start_line,
            end_line=end_line or start_line,
            total_lines=0,
        )

        # --- Sensitive-file gate ---
        if is_sensitive_path(rel_str):
            result.error = f"Access denied: {sensitive_file_reason(rel_str)}"
            return result

        # --- Existence and type check ---
        if not target.exists():
            result.error = f"File not found: {relative_path}"
            return result
        if not target.is_file():
            result.error = f"Path is not a file: {relative_path}"
            return result

        # --- Size guard (fast path before reading) ---
        size = target.stat().st_size
        if size > settings.MAX_FILE_SIZE:
            result.error = (
                f"File too large ({size} bytes > MAX_FILE_SIZE {settings.MAX_FILE_SIZE})"
            )
            return result

        # --- Binary guard ---
        if _is_binary(target):
            result.error = "Binary file — content not exposed"
            return result

        # --- Read all lines ---
        try:
            all_lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            result.error = str(exc)
            return result

        result.total_lines = len(all_lines)

        # --- Clamp / validate line range ---
        if start_line < 1:
            start_line = 1
        if start_line > result.total_lines:
            result.error = (
                f"start_line ({start_line}) exceeds file length ({result.total_lines})"
            )
            return result

        # Determine effective end_line
        if end_line is None:
            effective_end = min(start_line + settings.MAX_LINES_PER_READ - 1, result.total_lines)
        else:
            effective_end = min(end_line, result.total_lines)

        # Enforce MAX_LINES_PER_READ cap
        max_end = start_line + settings.MAX_LINES_PER_READ - 1
        truncated = effective_end > max_end
        if truncated:
            effective_end = max_end
            result.truncated = True
            result.truncation_reason = (
                f"MAX_LINES_PER_READ ({settings.MAX_LINES_PER_READ}) enforced"
            )

        result.start_line = start_line
        result.end_line = effective_end
        # Slice (0-indexed internally)
        result.lines = all_lines[start_line - 1 : effective_end]
        return result
