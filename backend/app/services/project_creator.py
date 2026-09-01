"""
AgentOS — Project Creator Service.

Provides safe, bounded initialization of new software projects from scratch:
- Validates project names and target parent directories
- Enforces security boundaries (prevents path traversal, UNC paths, and AgentOS self-targeting)
- Detects existing directory conflicts to prevent data loss
- Creates project directory and basic skeleton files (README.md, .gitignore)
- Initializes Git safely if requested
- Dynamically updates active WORKSPACE_ROOT and persists to .env
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from backend.app.config.settings import PROJECT_ROOT, settings

logger = logging.getLogger("agentos.project_creator")

_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


class ProjectCreationError(ValueError):
    """Raised when project creation validation or filesystem operation fails."""
    pass


class ProjectConflictError(FileExistsError):
    """Raised when the target project directory already exists."""
    pass


class ProjectCreatorService:
    """Service for safely creating and initializing new software project directories."""

    @staticmethod
    def validate_project_request(name: str, location: str) -> Tuple[Path, Path]:
        """
        Validate project name and parent directory.
        Returns (parent_dir, target_project_dir).
        """
        name_clean = str(name).strip()
        location_clean = str(location).strip()

        if not name_clean:
            raise ProjectCreationError("Project name cannot be empty.")

        if not _NAME_PATTERN.match(name_clean):
            raise ProjectCreationError(
                "Invalid project name. Only alphanumeric characters, dashes (-), underscores (_), and dots (.) are allowed."
            )

        if not location_clean:
            raise ProjectCreationError("Project location directory cannot be empty.")

        # Reject null bytes and UNC paths
        if "\0" in location_clean or "\0" in name_clean:
            raise ProjectCreationError("Null byte injection detected in project path.")

        if location_clean.startswith(r"\\") or location_clean.startswith("//"):
            raise ProjectCreationError("UNC network paths are forbidden.")

        if ".." in Path(location_clean).parts or ".." in Path(name_clean).parts:
            raise ProjectCreationError("Path traversal sequences ('..') are not allowed.")

        try:
            parent_dir = Path(location_clean).resolve(strict=False)
        except Exception as exc:
            raise ProjectCreationError(f"Invalid location path: {exc}")

        if not parent_dir.is_absolute():
            raise ProjectCreationError("Project location must be an absolute directory path.")

        if not parent_dir.exists():
            raise ProjectCreationError(f"Project location directory does not exist: {parent_dir}")

        if not parent_dir.is_dir():
            raise ProjectCreationError(f"Project location is not a directory: {parent_dir}")

        target_dir = (parent_dir / name_clean).resolve()

        # Prevent pointing into the AgentOS installation directory
        agentos_root = Path(PROJECT_ROOT).resolve()
        _inside_agentos = False
        try:
            target_dir.relative_to(agentos_root)
            _inside_agentos = True
        except ValueError:
            pass  # Target is correctly outside agentos_root

        if _inside_agentos:
            raise ProjectCreationError(
                "Cannot create a project inside the AgentOS installation directory. "
                "Please choose an external directory."
            )

        if target_dir.exists():
            # If it exists, verify whether it's an empty directory or conflict
            if target_dir.is_file():
                raise ProjectConflictError(f"A file with the name '{name_clean}' already exists at {parent_dir}.")
            try:
                contents = list(target_dir.iterdir())
                if len(contents) > 0:
                    raise ProjectConflictError(
                        f"Directory '{target_dir}' already exists and is not empty. "
                        "Please choose a different project name or location."
                    )
            except PermissionError:
                raise ProjectCreationError(f"Permission denied accessing directory: {target_dir}")

        return parent_dir, target_dir

    @classmethod
    def create_project(
        cls,
        name: str,
        location: str,
        instruction: Optional[str] = None,
        initialize_git: bool = True,
    ) -> Dict[str, Any]:
        """
        Creates the project directory on disk, initializes base files and Git,
        updates the active WORKSPACE_ROOT, and returns created project metadata.
        """
        parent_dir, target_dir = cls.validate_project_request(name, location)

        # 1. Create project directory
        target_dir.mkdir(parents=True, exist_ok=True)

        # 2. Write initial base files (README.md and .gitignore)
        readme_path = target_dir / "README.md"
        if not readme_path.exists():
            initial_desc = instruction.strip() if instruction else "Initial project created with AgentOS."
            readme_path.write_text(
                f"# {name}\n\n{initial_desc}\n\n---\n*Created with AgentOS.*\n",
                encoding="utf-8",
            )

        gitignore_path = target_dir / ".gitignore"
        if not gitignore_path.exists():
            gitignore_path.write_text(
                "# Byte-compiled / optimized / DLL files\n"
                "__pycache__/\n*.py[cod]\n*$py.class\n\n"
                "# Node / Frontend\n"
                "node_modules/\n.next/\ndist/\nbuild/\n\n"
                "# Environments\n"
                ".env\n.venv\nenv/\nvenv/\n\n"
                "# Logs and temporary files\n"
                "*.log\n.pytest_cache/\n.coverage\n",
                encoding="utf-8",
            )

        # 3. Initialize Git if requested and not already present
        git_initialized = False
        if initialize_git and not (target_dir / ".git").exists():
            try:
                import subprocess
                res = subprocess.run(
                    ["git", "init"],
                    cwd=str(target_dir),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if res.returncode == 0:
                    git_initialized = True
            except Exception as exc:
                logger.warning("Git initialization skipped or failed: %s", exc)

        # 4. Update active WORKSPACE_ROOT dynamically in running process and .env
        settings.WORKSPACE_ROOT = str(target_dir)
        os.environ["WORKSPACE_ROOT"] = str(target_dir)

        agentos_root = Path(PROJECT_ROOT).resolve()
        env_path = agentos_root / ".env"
        try:
            if env_path.exists():
                lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
                updated = False
                for i, line in enumerate(lines):
                    if line.startswith("WORKSPACE_ROOT="):
                        lines[i] = f"WORKSPACE_ROOT={target_dir}\n"
                        updated = True
                        break
                if not updated:
                    lines.append(f"WORKSPACE_ROOT={target_dir}\n")
                env_path.write_text("".join(lines), encoding="utf-8")
            else:
                env_path.write_text(f"WORKSPACE_ROOT={target_dir}\n", encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not persist WORKSPACE_ROOT to .env: %s", exc)

        return {
            "status": "ok",
            "project_name": name,
            "path": str(target_dir),
            "git_initialized": git_initialized,
            "created_files": ["README.md", ".gitignore"],
        }
