"""
Repository Scanner for AgentOS Phase 3.

Discovers the file/directory structure of a repository rooted at
WORKSPACE_ROOT.  All traversal is strictly bounded:

* Never follows symlinks that resolve outside WORKSPACE_ROOT.
* Skips a configurable set of ignored directories.
* Stops when MAX_REPOSITORY_FILES or MAX_TOTAL_SCAN_SIZE is reached.
* Skips files larger than MAX_FILE_SIZE.
* Skips binary files (heuristic: null-byte check in first 8 KB).
* Skips files matched by the sensitive-file policy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from backend.app.config.settings import settings
from backend.app.security.sensitive_files import is_sensitive_path

# Directories that are always excluded from traversal
_DEFAULT_IGNORED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        "coverage",
        ".idea",
        ".vscode",
        ".DS_Store",
    }
)

_BINARY_PROBE_BYTES = 8192


def _is_binary(path: Path) -> bool:
    """Heuristic: a file is binary if it contains a null byte in its first 8 KB."""
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(_BINARY_PROBE_BYTES)
        return b"\x00" in chunk
    except OSError:
        return True  # If we can't read it, treat it as binary/inaccessible


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------

@dataclass
class FileInfo:
    relative_path: str    # POSIX relative path from workspace root
    size_bytes: int
    extension: str        # lowercased, e.g. ".py"
    is_test_file: bool
    is_config_file: bool
    is_doc_file: bool


@dataclass
class ScanResult:
    root: str                          # Absolute workspace root scanned
    total_files: int = 0
    total_dirs: int = 0
    total_bytes: int = 0
    files: list[FileInfo] = field(default_factory=list)
    truncated: bool = False            # True if limits were hit
    truncation_reason: str = ""
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Heuristic classifiers
# ---------------------------------------------------------------------------

_TEST_PATTERNS: frozenset[str] = frozenset(
    {"test_", "_test", "tests/", "spec.", ".spec.", "__tests__/"}
)
_CONFIG_EXTENSIONS: frozenset[str] = frozenset(
    {".toml", ".cfg", ".ini", ".yaml", ".yml", ".json", ".env", ".conf", ".config"}
)
_CONFIG_BASENAMES: frozenset[str] = frozenset(
    {
        "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
        "package.json", "package-lock.json", "tsconfig.json", "webpack.config.js",
        "vite.config.js", "vite.config.ts", "next.config.js", "next.config.ts",
        "dockerfile", "docker-compose.yml", "docker-compose.yaml",
        ".flake8", ".pylintrc", ".mypy.ini", "mypy.ini",
        "jest.config.js", "jest.config.ts", "babel.config.js",
        ".gitignore", ".gitattributes", ".editorconfig",
        "alembic.ini", "manage.py",
    }
)
_DOC_EXTENSIONS: frozenset[str] = frozenset({".md", ".rst", ".txt", ".adoc"})
_DOC_BASENAMES: frozenset[str] = frozenset({"readme", "changelog", "license", "contributing"})


def _classify_file(rel: str, name: str, ext: str) -> tuple[bool, bool, bool]:
    """Return (is_test_file, is_config_file, is_doc_file)."""
    rel_lower = rel.lower()
    name_lower = name.lower()
    is_test = any(pat in rel_lower for pat in _TEST_PATTERNS)
    is_config = ext in _CONFIG_EXTENSIONS or name_lower in _CONFIG_BASENAMES
    is_doc = ext in _DOC_EXTENSIONS or any(
        name_lower.startswith(b) for b in _DOC_BASENAMES
    )
    return is_test, is_config, is_doc


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class RepositoryScanner:
    """Bounded, security-safe repository traversal."""

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        self._explicit_root = workspace_root

    @property
    def _root(self) -> Path:
        return (self._explicit_root or Path(settings.WORKSPACE_ROOT)).resolve()

    def _is_inside_workspace(self, resolved: Path) -> bool:
        try:
            resolved.relative_to(self._root)
            return True
        except ValueError:
            return False

    def scan(self, relative_path: str = ".") -> ScanResult:
        """Scan a directory tree rooted at *relative_path* inside the workspace.

        Args:
            relative_path: Path relative to WORKSPACE_ROOT to start scanning.
                           Defaults to the workspace root itself.

        Returns:
            ScanResult with discovered file metadata.

        Raises:
            ValueError: If *relative_path* escapes the workspace boundary.
        """
        start = (self._root / relative_path).resolve()
        if not self._is_inside_workspace(start):
            raise ValueError(f"Scan path escapes workspace: {relative_path}")
        if not start.is_dir():
            raise ValueError(f"Scan path is not a directory: {relative_path}")

        result = ScanResult(root=str(self._root))
        total_bytes = 0
        file_count = 0

        for dir_path, dir_names, file_names in os.walk(start, followlinks=False):
            dp = Path(dir_path)

            # Security: verify we haven't escaped workspace
            resolved_dp = dp.resolve()
            if not self._is_inside_workspace(resolved_dp):
                dir_names[:] = []
                result.errors.append(f"Symlink escape blocked at {dp}")
                continue

            # Prune ignored directories in-place so os.walk won't descend
            dir_names[:] = [
                d for d in dir_names
                if d not in _DEFAULT_IGNORED_DIRS
            ]

            result.total_dirs += 1

            for fname in file_names:
                fp = dp / fname
                resolved_fp = fp.resolve()

                # Symlink escape check
                if not self._is_inside_workspace(resolved_fp):
                    result.errors.append(f"Symlink escape blocked: {fp}")
                    continue

                # Sensitive-file skip
                rel_str = str(fp.relative_to(self._root)).replace(os.sep, "/")
                if is_sensitive_path(rel_str):
                    continue

                try:
                    size = fp.stat().st_size
                except OSError:
                    continue

                # File-size limit
                if size > settings.MAX_FILE_SIZE:
                    continue

                # Binary skip
                if _is_binary(fp):
                    continue

                ext = fp.suffix.lower()
                is_test, is_config, is_doc = _classify_file(rel_str, fname, ext)

                result.files.append(FileInfo(
                    relative_path=rel_str,
                    size_bytes=size,
                    extension=ext,
                    is_test_file=is_test,
                    is_config_file=is_config,
                    is_doc_file=is_doc,
                ))
                file_count += 1
                total_bytes += size

                # Cumulative size limit
                if total_bytes > settings.MAX_TOTAL_SCAN_SIZE:
                    result.truncated = True
                    result.truncation_reason = (
                        f"MAX_TOTAL_SCAN_SIZE ({settings.MAX_TOTAL_SCAN_SIZE} bytes) reached"
                    )
                    dir_names[:] = []
                    break

                # File count limit
                if file_count >= settings.MAX_REPOSITORY_FILES:
                    result.truncated = True
                    result.truncation_reason = (
                        f"MAX_REPOSITORY_FILES ({settings.MAX_REPOSITORY_FILES}) reached"
                    )
                    dir_names[:] = []
                    break

            if result.truncated:
                break

        result.total_files = len(result.files)
        result.total_bytes = sum(f.size_bytes for f in result.files)
        return result
