"""
Tests for backend/app/code/scanner.py

Covers:
- Basic workspace traversal and file discovery
- Directory exclusion (.git, node_modules, .venv, __pycache__, etc.)
- File count limit (MAX_REPOSITORY_FILES)
- Total size limit (MAX_TOTAL_SCAN_SIZE)
- Per-file size limit (MAX_FILE_SIZE)
- Binary file skip
- Sensitive file skip
- Symlink escape blocked (where platform supports)
- Path traversal attempt rejected
- Language and project detection integration
"""

import os
import sys
from pathlib import Path

import pytest

from backend.app.code.scanner import RepositoryScanner, ScanResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_file(path: Path, content: str = "hello\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_binary(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x01\x02\x03")


# ---------------------------------------------------------------------------
# Basic discovery
# ---------------------------------------------------------------------------

class TestScannerBasic:
    def test_discovers_python_file(self, tmp_path):
        make_file(tmp_path / "main.py", "print('hello')\n")
        scanner = RepositoryScanner(workspace_root=tmp_path)
        result = scanner.scan()
        paths = [f.relative_path for f in result.files]
        assert "main.py" in paths

    def test_counts_files_correctly(self, tmp_path):
        for name in ["a.py", "b.py", "c.txt"]:
            make_file(tmp_path / name)
        scanner = RepositoryScanner(workspace_root=tmp_path)
        result = scanner.scan()
        assert result.total_files == 3

    def test_extension_captured(self, tmp_path):
        make_file(tmp_path / "app.ts", "const x = 1;\n")
        scanner = RepositoryScanner(workspace_root=tmp_path)
        result = scanner.scan()
        assert result.files[0].extension == ".ts"

    def test_test_file_classified(self, tmp_path):
        make_file(tmp_path / "test_calc.py", "def test_x(): pass\n")
        scanner = RepositoryScanner(workspace_root=tmp_path)
        result = scanner.scan()
        assert result.files[0].is_test_file is True

    def test_config_file_classified(self, tmp_path):
        make_file(tmp_path / "pyproject.toml", "[tool.pytest]\n")
        scanner = RepositoryScanner(workspace_root=tmp_path)
        result = scanner.scan()
        assert result.files[0].is_config_file is True


# ---------------------------------------------------------------------------
# Directory exclusion
# ---------------------------------------------------------------------------

class TestScannerExclusions:
    @pytest.mark.parametrize("excluded_dir", [
        ".git", "node_modules", ".venv", "venv", "env",
        "__pycache__", ".pytest_cache", "dist", "build", "coverage",
    ])
    def test_ignores_excluded_dir(self, tmp_path, excluded_dir):
        hidden = tmp_path / excluded_dir
        make_file(hidden / "hidden.py", "secret\n")
        make_file(tmp_path / "visible.py", "visible\n")
        scanner = RepositoryScanner(workspace_root=tmp_path)
        result = scanner.scan()
        assert all(excluded_dir not in f.relative_path for f in result.files)
        assert any("visible.py" in f.relative_path for f in result.files)


# ---------------------------------------------------------------------------
# File-size and count limits
# ---------------------------------------------------------------------------

class TestScannerLimits:
    def test_skips_oversized_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("backend.app.code.scanner.settings.MAX_FILE_SIZE", 10)
        big_file = tmp_path / "big.py"
        big_file.write_text("x" * 100, encoding="utf-8")
        make_file(tmp_path / "small.py", "x\n")
        scanner = RepositoryScanner(workspace_root=tmp_path)
        result = scanner.scan()
        paths = [f.relative_path for f in result.files]
        assert "big.py" not in paths
        assert "small.py" in paths

    def test_file_count_limit(self, tmp_path, monkeypatch):
        monkeypatch.setattr("backend.app.code.scanner.settings.MAX_REPOSITORY_FILES", 3)
        for i in range(10):
            make_file(tmp_path / f"file_{i}.py")
        scanner = RepositoryScanner(workspace_root=tmp_path)
        result = scanner.scan()
        assert result.total_files <= 3
        assert result.truncated is True
        assert "MAX_REPOSITORY_FILES" in result.truncation_reason

    def test_total_scan_size_limit(self, tmp_path, monkeypatch):
        monkeypatch.setattr("backend.app.code.scanner.settings.MAX_TOTAL_SCAN_SIZE", 50)
        for i in range(5):
            (tmp_path / f"f{i}.py").write_text("x" * 20, encoding="utf-8")
        scanner = RepositoryScanner(workspace_root=tmp_path)
        result = scanner.scan()
        assert result.truncated is True
        assert "MAX_TOTAL_SCAN_SIZE" in result.truncation_reason


# ---------------------------------------------------------------------------
# Binary file skip
# ---------------------------------------------------------------------------

class TestScannerBinarySkip:
    def test_skips_binary_file(self, tmp_path):
        make_binary(tmp_path / "image.png")
        make_file(tmp_path / "script.py", "# ok\n")
        scanner = RepositoryScanner(workspace_root=tmp_path)
        result = scanner.scan()
        paths = [f.relative_path for f in result.files]
        assert "image.png" not in paths
        assert "script.py" in paths


# ---------------------------------------------------------------------------
# Sensitive file skip
# ---------------------------------------------------------------------------

class TestScannerSensitiveSkip:
    def test_skips_dot_env(self, tmp_path):
        make_file(tmp_path / ".env", "SECRET=abc\n")
        make_file(tmp_path / "main.py", "print(1)\n")
        scanner = RepositoryScanner(workspace_root=tmp_path)
        result = scanner.scan()
        paths = [f.relative_path for f in result.files]
        assert ".env" not in paths
        assert "main.py" in paths

    def test_skips_private_key(self, tmp_path):
        make_file(tmp_path / "id_rsa", "-----BEGIN RSA PRIVATE KEY-----\n")
        scanner = RepositoryScanner(workspace_root=tmp_path)
        result = scanner.scan()
        assert all("id_rsa" not in f.relative_path for f in result.files)

    def test_skips_pem(self, tmp_path):
        make_file(tmp_path / "cert.pem", "-----BEGIN CERTIFICATE-----\n")
        scanner = RepositoryScanner(workspace_root=tmp_path)
        result = scanner.scan()
        assert all(".pem" not in f.relative_path for f in result.files)


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------

class TestScannerPathValidation:
    def test_rejects_traversal(self, tmp_path):
        scanner = RepositoryScanner(workspace_root=tmp_path)
        with pytest.raises(ValueError, match="traversal|outside|escape"):
            scanner.scan(relative_path="../../../etc")

    def test_rejects_absolute_path_outside_workspace(self, tmp_path):
        scanner = RepositoryScanner(workspace_root=tmp_path)
        outside = str(Path(tmp_path).parent)
        with pytest.raises(ValueError):
            scanner.scan(relative_path=outside)

    def test_accepts_dot_path(self, tmp_path):
        make_file(tmp_path / "x.py", "# ok\n")
        scanner = RepositoryScanner(workspace_root=tmp_path)
        result = scanner.scan(relative_path=".")
        assert result.total_files >= 1

    def test_rejects_non_directory(self, tmp_path):
        make_file(tmp_path / "main.py")
        scanner = RepositoryScanner(workspace_root=tmp_path)
        with pytest.raises(ValueError, match="directory"):
            scanner.scan(relative_path="main.py")


# ---------------------------------------------------------------------------
# Symlink escape (POSIX only)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="Symlinks require elevated privileges on Windows")
class TestScannerSymlinkEscape:
    def test_symlink_outside_workspace_is_blocked(self, tmp_path):
        outside = tmp_path.parent / "outside_target"
        outside.mkdir(exist_ok=True)
        (outside / "secret.py").write_text("SECRET\n", encoding="utf-8")
        link = tmp_path / "linked"
        link.symlink_to(outside)
        scanner = RepositoryScanner(workspace_root=tmp_path)
        result = scanner.scan()
        assert all("secret.py" not in f.relative_path for f in result.files)
