"""
Tests for backend/app/code/reader.py

Covers:
- Basic line-range reading
- 1-indexed line numbers
- start_line default (1)
- end_line clamped to file length
- MAX_LINES_PER_READ enforcement (truncation)
- Sensitive file denial (.env, .key, .pem, id_rsa, etc.)
- Binary file denial
- File-size guard
- File not found
- Path is not a file
- Workspace traversal rejection
- Windows drive escape rejection
- UNC path rejection
- Absolute path outside workspace rejection
- start_line beyond file length
"""

import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_reader(workspace: Path, monkeypatch):
    """Return a CodeReader with workspace root patched to *workspace*."""
    monkeypatch.setattr(
        "backend.app.code.reader.settings.WORKSPACE_ROOT", str(workspace)
    )
    import backend.app.services.workspace_service as ws

    def patched_validate(path_str):
        root = workspace.resolve()
        p = Path(path_str)
        if ".." in p.parts:
            raise ValueError("Path traversal ('..') detected")
        if path_str.startswith("\\\\") or path_str.startswith("//"):
            raise ValueError("UNC paths are not allowed")
        import os
        if os.path.isabs(path_str):
            target = p.resolve()
            if sys.platform == "win32" and target.drive.lower() != root.drive.lower():
                raise ValueError("Windows drive escape detected")
            if not str(target).startswith(str(root)):
                raise ValueError(f"Path outside workspace: {path_str}")
        else:
            target = (root / path_str).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            raise ValueError(f"Path outside workspace: {path_str}")
        return target

    monkeypatch.setattr(ws.WorkspaceService, "validate_path", staticmethod(patched_validate))
    from backend.app.code.reader import CodeReader
    reader = CodeReader()
    reader._root = workspace.resolve()
    return reader


# ---------------------------------------------------------------------------
# Basic reading
# ---------------------------------------------------------------------------

class TestCodeReaderBasic:
    def test_reads_all_lines_default(self, tmp_path, monkeypatch):
        content = "\n".join(f"line {i}" for i in range(1, 6)) + "\n"
        make_file(tmp_path / "file.py", content)
        reader = make_reader(tmp_path, monkeypatch)
        result = reader.read("file.py")
        assert result.error is None
        assert result.start_line == 1
        assert result.lines[0] == "line 1"

    def test_reads_specific_range(self, tmp_path, monkeypatch):
        content = "\n".join(f"L{i}" for i in range(1, 11)) + "\n"
        make_file(tmp_path / "file.py", content)
        reader = make_reader(tmp_path, monkeypatch)
        result = reader.read("file.py", start_line=3, end_line=5)
        assert result.error is None
        assert result.start_line == 3
        assert result.end_line == 5
        assert result.lines == ["L3", "L4", "L5"]

    def test_total_lines_reported(self, tmp_path, monkeypatch):
        content = "a\nb\nc\n"
        make_file(tmp_path / "file.py", content)
        reader = make_reader(tmp_path, monkeypatch)
        result = reader.read("file.py")
        assert result.total_lines == 3

    def test_end_line_clamped_to_file_end(self, tmp_path, monkeypatch):
        content = "a\nb\n"
        make_file(tmp_path / "file.py", content)
        reader = make_reader(tmp_path, monkeypatch)
        result = reader.read("file.py", start_line=1, end_line=999)
        assert result.end_line == 2


# ---------------------------------------------------------------------------
# MAX_LINES_PER_READ enforcement
# ---------------------------------------------------------------------------

class TestCodeReaderLineCap:
    def test_enforces_max_lines_per_read(self, tmp_path, monkeypatch):
        monkeypatch.setattr("backend.app.code.reader.settings.MAX_LINES_PER_READ", 5)
        content = "\n".join(f"L{i}" for i in range(1, 21)) + "\n"
        make_file(tmp_path / "big.py", content)
        reader = make_reader(tmp_path, monkeypatch)
        result = reader.read("big.py", start_line=1, end_line=20)
        assert len(result.lines) == 5
        assert result.truncated is True
        assert "MAX_LINES_PER_READ" in result.truncation_reason

    def test_no_truncation_within_limit(self, tmp_path, monkeypatch):
        monkeypatch.setattr("backend.app.code.reader.settings.MAX_LINES_PER_READ", 200)
        content = "\n".join(f"L{i}" for i in range(1, 11)) + "\n"
        make_file(tmp_path / "small.py", content)
        reader = make_reader(tmp_path, monkeypatch)
        result = reader.read("small.py", start_line=1, end_line=10)
        assert result.truncated is False
        assert len(result.lines) == 10


# ---------------------------------------------------------------------------
# Sensitive file denial
# ---------------------------------------------------------------------------

class TestCodeReaderSensitiveDenial:
    @pytest.mark.parametrize("sensitive_name", [
        ".env",
        ".env.local",
        "id_rsa",
        "private.key",
        "cert.pem",
        "credentials.json",
        "secrets.yaml",
    ])
    def test_denies_sensitive_file(self, tmp_path, monkeypatch, sensitive_name):
        make_file(tmp_path / sensitive_name, "SECRET=123\n")
        reader = make_reader(tmp_path, monkeypatch)
        result = reader.read(sensitive_name)
        assert result.error is not None
        assert "denied" in result.error.lower() or "sensitive" in result.error.lower() or "access" in result.error.lower()
        assert result.lines == []


# ---------------------------------------------------------------------------
# Binary file denial
# ---------------------------------------------------------------------------

class TestCodeReaderBinaryDenial:
    def test_denies_binary_file(self, tmp_path, monkeypatch):
        bin_file = tmp_path / "image.png"
        bin_file.write_bytes(b"\x00\x01\x02\x03")
        reader = make_reader(tmp_path, monkeypatch)
        result = reader.read("image.png")
        assert result.error is not None
        assert result.lines == []


# ---------------------------------------------------------------------------
# File-size guard
# ---------------------------------------------------------------------------

class TestCodeReaderSizeGuard:
    def test_denies_file_exceeding_max_size(self, tmp_path, monkeypatch):
        monkeypatch.setattr("backend.app.code.reader.settings.MAX_FILE_SIZE", 20)
        big_file = tmp_path / "huge.py"
        big_file.write_text("x" * 100, encoding="utf-8")
        reader = make_reader(tmp_path, monkeypatch)
        result = reader.read("huge.py")
        assert result.error is not None
        assert "large" in result.error.lower() or "MAX_FILE_SIZE" in result.error


# ---------------------------------------------------------------------------
# Non-existent file
# ---------------------------------------------------------------------------

class TestCodeReaderMissingFile:
    def test_error_on_missing_file(self, tmp_path, monkeypatch):
        reader = make_reader(tmp_path, monkeypatch)
        result = reader.read("doesnotexist.py")
        assert result.error is not None

    def test_error_on_directory(self, tmp_path, monkeypatch):
        (tmp_path / "subdir").mkdir()
        reader = make_reader(tmp_path, monkeypatch)
        result = reader.read("subdir")
        assert result.error is not None

    def test_error_start_line_beyond_file(self, tmp_path, monkeypatch):
        make_file(tmp_path / "short.py", "one\ntwo\n")
        reader = make_reader(tmp_path, monkeypatch)
        result = reader.read("short.py", start_line=100)
        assert result.error is not None


# ---------------------------------------------------------------------------
# Path security
# ---------------------------------------------------------------------------

class TestCodeReaderPathSecurity:
    def test_rejects_traversal(self, tmp_path, monkeypatch):
        reader = make_reader(tmp_path, monkeypatch)
        with pytest.raises(ValueError, match="traversal|outside|escape"):
            reader.read("../../etc/passwd")

    def test_rejects_unc_path(self, tmp_path, monkeypatch):
        reader = make_reader(tmp_path, monkeypatch)
        with pytest.raises(ValueError, match="UNC"):
            reader.read("\\\\server\\share\\secret.txt")

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific")
    def test_rejects_windows_drive_escape(self, tmp_path, monkeypatch):
        reader = make_reader(tmp_path, monkeypatch)
        with pytest.raises(ValueError, match="drive|escape"):
            reader.read("D:\\secret.txt")

    def test_rejects_absolute_outside_workspace(self, tmp_path, monkeypatch):
        reader = make_reader(tmp_path, monkeypatch)
        outside = str(tmp_path.parent / "outside.py")
        with pytest.raises(ValueError):
            reader.read(outside)
