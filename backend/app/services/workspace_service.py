"""
AgentOS Phase 3 & 14 — Workspace Security & Sandbox Hardening.

Enforces:
- Workspace boundary containment (prevents UNC, path traversal, Windows drive escapes)
- Symlink resolution & escape prevention
- Sensitive file access rejection (.env, credentials, SSH keys, shadow)
"""

from __future__ import annotations

import os
from pathlib import Path

from backend.app.config.settings import settings
from backend.app.security.sensitive_files import is_sensitive_path, sensitive_file_reason


class WorkspaceSecurityError(ValueError):
    """Raised when workspace boundary or sensitive file policies are violated."""
    pass


class WorkspaceService:
    @staticmethod
    def get_workspace_root() -> Path:
        configured_root = Path(settings.WORKSPACE_ROOT).resolve()
        if not configured_root.exists():
            configured_root.mkdir(parents=True, exist_ok=True)
        return configured_root

    @staticmethod
    def validate_path(requested_path: str, allow_sensitive: bool = False) -> Path:
        """
        Validate that requested path is safely contained within WORKSPACE_ROOT
        and does not target sensitive files.
        """
        root = WorkspaceService.get_workspace_root()
        req_path_str = str(requested_path).strip()

        # Reject null bytes
        if "\0" in req_path_str:
            raise WorkspaceSecurityError("Null byte injection detected in path.")

        # Reject UNC paths
        if req_path_str.startswith(r"\\") or req_path_str.startswith("//"):
            raise WorkspaceSecurityError("UNC network paths are forbidden.")

        # Reject direct traversal markers
        if ".." in Path(req_path_str).parts or ".." in req_path_str.replace("\\", "/").split("/"):
            raise WorkspaceSecurityError("Path traversal ('..') detected.")

        if os.path.isabs(req_path_str):
            target = Path(req_path_str).resolve()
            if os.name == "nt" and target.drive.lower() != root.drive.lower():
                raise WorkspaceSecurityError("Windows drive escape detected.")
        else:
            target = (root / req_path_str).resolve()

        # Symlink escape verification: resolve canonical real path
        try:
            target_real = target.resolve(strict=False)
            target_real.relative_to(root.resolve())
        except ValueError:
            raise WorkspaceSecurityError(f"Path outside workspace boundary: {requested_path}")

        # Sensitive file protection
        rel_posix = target.relative_to(root).as_posix()
        if not allow_sensitive and is_sensitive_path(rel_posix):
            raise WorkspaceSecurityError(f"Access denied: {sensitive_file_reason(rel_posix)}")

        return target

    @staticmethod
    def is_path_safe(requested_path: str, workspace_root: str) -> bool:
        """
        Convenience predicate used by benchmarks and tests.
        Returns True if path is safely inside *workspace_root*, False otherwise.
        Unlike validate_path (which uses settings.WORKSPACE_ROOT), this accepts
        an explicit root string — useful in sandboxed test workspaces.
        """
        import urllib.parse
        req_path_str = urllib.parse.unquote(str(requested_path).strip())

        # Reject null bytes
        if "\0" in req_path_str:
            return False

        # Reject UNC paths
        if req_path_str.startswith(r"\\") or req_path_str.startswith("//"):
            return False

        # Reject path traversal
        norm_parts = req_path_str.replace("\\", "/").split("/")
        if ".." in norm_parts or any(p == ".." for p in Path(req_path_str).parts):
            return False

        # Reject Windows drive letters (C:\...) when they differ from root
        root = Path(workspace_root).resolve()
        if os.path.isabs(req_path_str):
            target = Path(req_path_str)
            if os.name == "nt" and target.drive.lower() != root.drive.lower():
                return False
            try:
                target.resolve(strict=False).relative_to(root)
                # Check sensitive
                rel_posix = target.resolve(strict=False).relative_to(root).as_posix()
                if is_sensitive_path(rel_posix):
                    return False
                return True
            except ValueError:
                return False

        # Resolve relative path — reject traversal
        candidate = (root / req_path_str).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return False

        # Sensitive file check
        try:
            rel_posix = candidate.relative_to(root).as_posix()
            if is_sensitive_path(rel_posix):
                return False
        except ValueError:
            return False

        return True


