"""
Bounded Code Search for AgentOS Phase 3.

Searches for literal strings or regex patterns inside files within the
workspace boundary.  All security constraints from Phase 0 are preserved:

* Paths are resolved and validated against WORKSPACE_ROOT before opening.
* Symlinks that escape the workspace are skipped.
* Sensitive files are never searched.
* Results are capped at MAX_SEARCH_RESULTS.
* Per-file reading is capped at MAX_SEARCH_FILE_SIZE.
* Total returned content is capped at MAX_OUTPUT_SIZE.
* Binary files are skipped.
* Ignored directories are skipped.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from backend.app.code.scanner import _DEFAULT_IGNORED_DIRS, _is_binary
from backend.app.config.settings import settings
from backend.app.security.sensitive_files import is_sensitive_path
from backend.app.services.workspace_service import WorkspaceService


@dataclass
class SearchMatch:
    relative_path: str   # POSIX relative path from workspace root
    line_number: int
    line_content: str    # stripped of trailing newline


@dataclass
class SearchResult:
    query: str
    is_regex: bool
    matches: list[SearchMatch] = field(default_factory=list)
    files_searched: int = 0
    truncated: bool = False
    truncation_reason: str = ""
    errors: list[str] = field(default_factory=list)


class CodeSearch:
    """Line-numbered, workspace-bounded text/regex search."""

    def __init__(self) -> None:
        self._root = Path(settings.WORKSPACE_ROOT).resolve()

    def _is_inside_workspace(self, p: Path) -> bool:
        try:
            p.relative_to(self._root)
            return True
        except ValueError:
            return False

    def search(
        self,
        query: str,
        *,
        relative_path: str = ".",
        is_regex: bool = False,
        include_extensions: Optional[Sequence[str]] = None,
        case_sensitive: bool = True,
    ) -> SearchResult:
        """Search for *query* inside the workspace subtree *relative_path*.

        Args:
            query: Literal string or regex pattern.
            relative_path: Subtree to search (relative to WORKSPACE_ROOT).
            is_regex: If True, treat *query* as a regex pattern.
            include_extensions: Optional allowlist of extensions (e.g. ['.py', '.ts']).
            case_sensitive: Case-sensitive matching.

        Returns:
            SearchResult with line-numbered matches.

        Raises:
            ValueError: If *relative_path* escapes the workspace.
            re.error: If *is_regex=True* and the pattern is invalid.
        """
        start = WorkspaceService.validate_path(relative_path)
        if not start.exists():
            raise ValueError(f"Search path does not exist: {relative_path}")

        # Compile the pattern
        flags = 0 if case_sensitive else re.IGNORECASE
        if is_regex:
            pattern = re.compile(query, flags)
        else:
            # Escape literal and compile for uniform match interface
            pattern = re.compile(re.escape(query), flags)

        result = SearchResult(query=query, is_regex=is_regex)
        total_content_bytes = 0

        # Collect files to search
        if start.is_file():
            files_to_search = [start]
        else:
            files_to_search = []
            for dir_path, dir_names, file_names in os.walk(start, followlinks=False):
                dp = Path(dir_path)
                if not self._is_inside_workspace(dp.resolve()):
                    dir_names[:] = []
                    continue
                dir_names[:] = [d for d in dir_names if d not in _DEFAULT_IGNORED_DIRS]
                for fname in file_names:
                    files_to_search.append(dp / fname)

        ext_filter = None
        if include_extensions:
            ext_filter = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in include_extensions}

        for fp in files_to_search:
            resolved = fp.resolve()
            if not self._is_inside_workspace(resolved):
                continue
            rel_str = str(fp.relative_to(self._root)).replace(os.sep, "/")

            # Sensitive-file skip
            if is_sensitive_path(rel_str):
                continue

            # Extension filter
            if ext_filter and fp.suffix.lower() not in ext_filter:
                continue

            # File-size limit
            try:
                size = fp.stat().st_size
            except OSError:
                continue
            if size > settings.MAX_SEARCH_FILE_SIZE:
                continue

            # Binary skip
            if _is_binary(fp):
                continue

            result.files_searched += 1

            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                result.errors.append(f"{rel_str}: {exc}")
                continue

            for lineno, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    result.matches.append(SearchMatch(
                        relative_path=rel_str,
                        line_number=lineno,
                        line_content=line.rstrip("\r\n"),
                    ))
                    total_content_bytes += len(line.encode("utf-8"))

                    # Result count cap
                    if len(result.matches) >= settings.MAX_SEARCH_RESULTS:
                        result.truncated = True
                        result.truncation_reason = (
                            f"MAX_SEARCH_RESULTS ({settings.MAX_SEARCH_RESULTS}) reached"
                        )
                        return result

                    # Output size cap
                    if total_content_bytes > settings.MAX_OUTPUT_SIZE:
                        result.truncated = True
                        result.truncation_reason = (
                            f"MAX_OUTPUT_SIZE ({settings.MAX_OUTPUT_SIZE} bytes) reached"
                        )
                        return result

        return result
