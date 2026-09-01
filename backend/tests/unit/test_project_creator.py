"""
Unit tests for ProjectCreatorService.

Tests:
- Valid project creation and workspace root switching
- Project name format validation
- Location validation (not a directory, does not exist)
- Null byte injection rejection
- UNC path rejection
- Path traversal ('..') rejection
- Targeting inside AgentOS installation tree rejection
- Existing non-empty directory conflict rejection
- Empty existing directory is allowed (no conflict)
- Git initialization (mocked)
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.app.services.project_creator import (
    ProjectConflictError,
    ProjectCreationError,
    ProjectCreatorService,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_parent(tmp_path: Path, name: str = "projects") -> Path:
    """Create and return a parent directory for test projects."""
    parent = tmp_path / name
    parent.mkdir(parents=True, exist_ok=True)
    return parent


# ──────────────────────────────────────────────────────────────────────────────
# Name validation
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("valid_name", [
    "MyProject",
    "my-project",
    "my_project",
    "project.v2",
    "App123",
    "a",
])
def test_valid_project_names_pass(tmp_path, valid_name):
    parent = _make_parent(tmp_path)
    parent_path, target = ProjectCreatorService.validate_project_request(valid_name, str(parent))
    assert target == (parent / valid_name).resolve()


@pytest.mark.parametrize("bad_name", [
    "",
    " ",
    "project/bad",
    "proj ect",
    "proj@ect",
    "../../escape",
    "proj\\ect",
])
def test_invalid_project_names_rejected(tmp_path, bad_name):
    parent = _make_parent(tmp_path)
    with pytest.raises(ProjectCreationError):
        ProjectCreatorService.validate_project_request(bad_name, str(parent))


# ──────────────────────────────────────────────────────────────────────────────
# Location validation
# ──────────────────────────────────────────────────────────────────────────────

def test_nonexistent_location_rejected(tmp_path):
    missing = tmp_path / "does_not_exist"
    with pytest.raises(ProjectCreationError, match="does not exist"):
        ProjectCreatorService.validate_project_request("MyApp", str(missing))


def test_file_as_location_rejected(tmp_path):
    file_path = tmp_path / "afile.txt"
    file_path.write_text("x")
    with pytest.raises(ProjectCreationError, match="not a directory"):
        ProjectCreatorService.validate_project_request("MyApp", str(file_path))


def test_null_byte_in_location_rejected(tmp_path):
    with pytest.raises(ProjectCreationError, match="Null byte"):
        ProjectCreatorService.validate_project_request("MyApp", str(tmp_path) + "\0evil")


def test_null_byte_in_name_rejected(tmp_path):
    parent = _make_parent(tmp_path)
    with pytest.raises(ProjectCreationError):
        # Null byte in name is caught by regex check first (still a ProjectCreationError)
        ProjectCreatorService.validate_project_request("App\0Evil", str(parent))


# ──────────────────────────────────────────────────────────────────────────────
# Security
# ──────────────────────────────────────────────────────────────────────────────

def test_unc_path_rejected(tmp_path):
    with pytest.raises(ProjectCreationError, match="UNC"):
        ProjectCreatorService.validate_project_request("MyApp", r"\\server\share")


def test_agentos_self_targeting_rejected():
    from backend.app.config.settings import PROJECT_ROOT
    agentos_root = Path(PROJECT_ROOT).resolve()
    # The agentos_root itself is the parent — target would be agentos_root/MyApp which is inside agentos_root
    with pytest.raises(ProjectCreationError, match="AgentOS installation"):
        ProjectCreatorService.validate_project_request("MyApp", str(agentos_root))


# ──────────────────────────────────────────────────────────────────────────────
# Conflict detection
# ──────────────────────────────────────────────────────────────────────────────

def test_existing_nonempty_directory_rejected(tmp_path):
    parent = _make_parent(tmp_path)
    existing = parent / "existing_project"
    existing.mkdir()
    (existing / "main.py").write_text("# code")
    with pytest.raises(ProjectConflictError, match="not empty"):
        ProjectCreatorService.validate_project_request("existing_project", str(parent))


def test_existing_file_at_target_rejected(tmp_path):
    parent = _make_parent(tmp_path)
    (parent / "collision").write_text("file, not a dir")
    with pytest.raises(ProjectConflictError):
        ProjectCreatorService.validate_project_request("collision", str(parent))


def test_empty_existing_directory_allowed(tmp_path):
    parent = _make_parent(tmp_path)
    empty_dir = parent / "empty_project"
    empty_dir.mkdir()
    # Should not raise — empty target dir is allowed
    parent_path, target = ProjectCreatorService.validate_project_request("empty_project", str(parent))
    assert target.exists()


# ──────────────────────────────────────────────────────────────────────────────
# Project creation
# ──────────────────────────────────────────────────────────────────────────────

def test_create_project_makes_directory(tmp_path):
    parent = _make_parent(tmp_path)
    with patch("backend.app.services.project_creator.settings") as mock_settings, \
         patch("os.environ"):
        mock_settings.WORKSPACE_ROOT = ""

        from backend.app.config.settings import PROJECT_ROOT as real_root
        with patch("backend.app.services.project_creator.PROJECT_ROOT", str(real_root)):
            result = ProjectCreatorService.create_project(
                name="TestApp",
                location=str(parent),
                instruction="Build a FastAPI app",
                initialize_git=False,
            )

    target = parent / "TestApp"
    assert target.exists()
    assert result["project_name"] == "TestApp"
    assert result["path"] == str(target)


def test_create_project_writes_base_files(tmp_path):
    parent = _make_parent(tmp_path)
    with patch("backend.app.services.project_creator.settings") as mock_settings, \
         patch("os.environ"):
        mock_settings.WORKSPACE_ROOT = ""

        from backend.app.config.settings import PROJECT_ROOT as real_root
        with patch("backend.app.services.project_creator.PROJECT_ROOT", str(real_root)):
            ProjectCreatorService.create_project(
                name="FileTestApp",
                location=str(parent),
                instruction="A CLI tool",
                initialize_git=False,
            )

    target = parent / "FileTestApp"
    assert (target / "README.md").exists()
    assert (target / ".gitignore").exists()
    readme_content = (target / "README.md").read_text()
    assert "FileTestApp" in readme_content
    assert "A CLI tool" in readme_content


def test_create_project_updates_workspace_root(tmp_path):
    parent = _make_parent(tmp_path)  # real directory exists

    from backend.app.config.settings import PROJECT_ROOT as real_root

    with patch("backend.app.services.project_creator.PROJECT_ROOT", str(real_root)):
        import backend.app.services.project_creator as pc_module
        original_settings = pc_module.settings
        mock_settings = MagicMock()
        mock_settings.WORKSPACE_ROOT = ""
        pc_module.settings = mock_settings

        try:
            with patch("os.environ"):
                ProjectCreatorService.create_project(
                    name="RootSwitchApp",
                    location=str(parent),
                    initialize_git=False,
                )
            target = parent / "RootSwitchApp"
            assert mock_settings.WORKSPACE_ROOT == str(target)
        finally:
            pc_module.settings = original_settings


def test_create_project_skips_git_gracefully(tmp_path):
    parent = _make_parent(tmp_path)
    from backend.app.config.settings import PROJECT_ROOT as real_root

    with patch("backend.app.services.project_creator.PROJECT_ROOT", str(real_root)):
        with patch("backend.app.services.project_creator.settings") as mock_settings, \
             patch("os.environ"), \
             patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            mock_settings.WORKSPACE_ROOT = ""
            result = ProjectCreatorService.create_project(
                name="NoGitApp",
                location=str(parent),
                initialize_git=True,
            )

    assert result["git_initialized"] is False
    assert (parent / "NoGitApp").exists()


def test_duplicate_creation_raises_conflict(tmp_path):
    parent = _make_parent(tmp_path)
    existing = parent / "DuplicateApp"
    existing.mkdir()
    (existing / "existing_file.py").write_text("x = 1")

    with pytest.raises(ProjectConflictError):
        ProjectCreatorService.create_project(
            name="DuplicateApp",
            location=str(parent),
        )
