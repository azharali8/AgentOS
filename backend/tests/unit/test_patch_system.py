"""
Tests for the Patch System (models, validator, applier)

Covers:
- Patch hash is deterministic and stable
- PatchValidator: file count limit
- PatchValidator: line count limit
- PatchValidator: path traversal rejected
- PatchValidator: UNC path rejected
- PatchValidator: absolute path rejected
- PatchValidator: Windows drive escape rejected
- PatchValidator: sensitive file rejected
- PatchValidator: stale file hash detected
- PatchValidator: missing file detected
- PatchValidator: valid patch passes
- PatchApplier: basic apply works
- PatchApplier: hash mismatch blocks apply
- PatchApplier: original file hash mismatch blocks apply (file changed since approval)
- PatchApplier: rollback restores files
- PatchApplier: rollback fails if file modified after patch (out-of-band)
- PatchApplier: new file creation
- PatchApplier: cross-task rollback rejected
- compute_file_hash is stable
"""

import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.code.patch.applier import PatchApplier, _apply_hunks
from backend.app.code.patch.models import (
    Patch,
    PatchFile,
    PatchHunk,
    PatchRollbackRecord,
    compute_file_hash,
    compute_patch_hash,
)
from backend.app.code.patch.validator import PatchValidator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_file(path: Path, content: str) -> str:
    """Write content, return hash of the actual bytes stored on disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    # Hash the actual bytes on disk (handles Windows \r\n vs \n)
    return compute_file_hash(path.read_bytes())



def patch_workspace(monkeypatch, workspace: Path):
    """Monkeypatch WORKSPACE_ROOT and WorkspaceService to use *workspace*."""
    monkeypatch.setattr("backend.app.code.patch.validator.settings.WORKSPACE_ROOT", str(workspace))
    monkeypatch.setattr("backend.app.code.patch.applier.settings.WORKSPACE_ROOT", str(workspace))
    import backend.app.services.workspace_service as ws

    def patched_validate(path_str):
        root = workspace.resolve()
        p = Path(path_str)
        if ".." in p.parts:
            raise ValueError("Path traversal detected")
        if path_str.startswith("\\\\") or path_str.startswith("//"):
            raise ValueError("UNC paths are not allowed")
        if p.is_absolute():
            if sys.platform == "win32" and p.drive.lower() != root.drive.lower():
                raise ValueError("Windows drive escape detected")
            try:
                p.relative_to(root)
            except ValueError:
                raise ValueError(f"Path outside workspace: {path_str}")
            return p
        target = (root / path_str).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            raise ValueError(f"Path outside workspace: {path_str}")
        return target

    monkeypatch.setattr(ws.WorkspaceService, "validate_path", staticmethod(patched_validate))


def simple_hunk(original_lines: list[str], new_lines: list[str], start: int = 1) -> PatchHunk:
    lines = [f"-{l}" for l in original_lines] + [f"+{l}" for l in new_lines]
    return PatchHunk(
        original_start=start,
        original_count=len(original_lines),
        new_start=start,
        new_count=len(new_lines),
        lines=lines,
    )


def make_patch(task_id: str, files: list[PatchFile]) -> Patch:
    return Patch(
        patch_id=str(uuid.uuid4()),
        task_id=task_id,
        description="Test patch",
        files=files,
    )


# ---------------------------------------------------------------------------
# compute_file_hash
# ---------------------------------------------------------------------------

class TestComputeFileHash:
    def test_deterministic(self):
        h1 = compute_file_hash(b"hello")
        h2 = compute_file_hash(b"hello")
        assert h1 == h2

    def test_different_content_different_hash(self):
        assert compute_file_hash(b"a") != compute_file_hash(b"b")

    def test_str_and_bytes_same_hash(self):
        assert compute_file_hash("hello") == compute_file_hash(b"hello")

    def test_returns_64_char_hex(self):
        h = compute_file_hash(b"test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# compute_patch_hash
# ---------------------------------------------------------------------------

class TestComputePatchHash:
    def test_deterministic(self, tmp_path, monkeypatch):
        patch_workspace(monkeypatch, tmp_path)
        pf = PatchFile(
            relative_path="calc.py",
            hunks=[simple_hunk(["old\n"], ["new\n"])],
        )
        p = make_patch("task-1", [pf])
        h1 = compute_patch_hash(p)
        h2 = compute_patch_hash(p)
        assert h1 == h2

    def test_different_content_different_hash(self, tmp_path, monkeypatch):
        patch_workspace(monkeypatch, tmp_path)
        pf1 = PatchFile(
            relative_path="calc.py",
            hunks=[simple_hunk(["old\n"], ["new\n"])],
        )
        pf2 = PatchFile(
            relative_path="calc.py",
            hunks=[simple_hunk(["old\n"], ["different\n"])],
        )
        h1 = compute_patch_hash(make_patch("task-1", [pf1]))
        h2 = compute_patch_hash(make_patch("task-1", [pf2]))
        assert h1 != h2


# ---------------------------------------------------------------------------
# PatchValidator
# ---------------------------------------------------------------------------

class TestPatchValidatorLimits:
    def test_empty_files_rejected(self, tmp_path, monkeypatch):
        patch_workspace(monkeypatch, tmp_path)
        p = make_patch("t1", [])
        v = PatchValidator()
        v._root = tmp_path.resolve()
        result = v.validate(p)
        assert not result.valid
        assert any("no files" in e.lower() for e in result.errors)

    def test_exceeds_max_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr("backend.app.code.patch.validator.settings.MAX_PATCH_FILES", 2)
        patch_workspace(monkeypatch, tmp_path)
        files = [PatchFile(relative_path=f"f{i}.py", hunks=[simple_hunk(["x\n"], ["y\n"])]) for i in range(5)]
        p = make_patch("t1", files)
        v = PatchValidator()
        v._root = tmp_path.resolve()
        result = v.validate(p)
        assert not result.valid
        assert any("MAX_PATCH_FILES" in e for e in result.errors)

    def test_exceeds_max_lines(self, tmp_path, monkeypatch):
        monkeypatch.setattr("backend.app.code.patch.validator.settings.MAX_PATCH_LINES", 2)
        patch_workspace(monkeypatch, tmp_path)
        hunk = PatchHunk(
            original_start=1, original_count=3, new_start=1, new_count=3,
            lines=["-a\n", "-b\n", "-c\n", "+x\n", "+y\n", "+z\n"]
        )
        pf = PatchFile(relative_path="f.py", hunks=[hunk])
        p = make_patch("t1", [pf])
        v = PatchValidator()
        v._root = tmp_path.resolve()
        result = v.validate(p)
        assert not result.valid
        assert any("MAX_PATCH_LINES" in e for e in result.errors)


class TestPatchValidatorPathSecurity:
    def test_traversal_rejected(self, tmp_path, monkeypatch):
        patch_workspace(monkeypatch, tmp_path)
        pf = PatchFile(relative_path="../../etc/passwd", hunks=[simple_hunk(["x\n"], ["y\n"])])
        p = make_patch("t1", [pf])
        v = PatchValidator()
        v._root = tmp_path.resolve()
        result = v.validate(p)
        assert not result.valid
        assert any("traversal" in e.lower() or "path" in e.lower() for e in result.errors)

    def test_unc_path_rejected(self, tmp_path, monkeypatch):
        patch_workspace(monkeypatch, tmp_path)
        pf = PatchFile(relative_path="\\\\server\\share\\evil.py", hunks=[simple_hunk(["x\n"], ["y\n"])])
        p = make_patch("t1", [pf])
        v = PatchValidator()
        v._root = tmp_path.resolve()
        result = v.validate(p)
        assert not result.valid

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific")
    def test_windows_drive_escape_rejected(self, tmp_path, monkeypatch):
        patch_workspace(monkeypatch, tmp_path)
        pf = PatchFile(relative_path="D:\\evil.py", hunks=[simple_hunk(["x\n"], ["y\n"])])
        p = make_patch("t1", [pf])
        v = PatchValidator()
        v._root = tmp_path.resolve()
        result = v.validate(p)
        assert not result.valid

    def test_sensitive_file_rejected(self, tmp_path, monkeypatch):
        patch_workspace(monkeypatch, tmp_path)
        pf = PatchFile(relative_path=".env", hunks=[simple_hunk(["x\n"], ["y\n"])])
        p = make_patch("t1", [pf])
        v = PatchValidator()
        v._root = tmp_path.resolve()
        result = v.validate(p)
        assert not result.valid
        assert any("sensitive" in e.lower() for e in result.errors)


class TestPatchValidatorFileState:
    def test_stale_hash_detected(self, tmp_path, monkeypatch):
        patch_workspace(monkeypatch, tmp_path)
        make_file(tmp_path / "calc.py", "old content\n")
        pf = PatchFile(
            relative_path="calc.py",
            original_hash="0" * 64,  # Wrong hash
            hunks=[simple_hunk(["old content\n"], ["new content\n"])],
        )
        p = make_patch("t1", [pf])
        v = PatchValidator()
        v._root = tmp_path.resolve()
        result = v.validate(p)
        assert not result.valid
        assert any("modified" in e.lower() or "hash" in e.lower() for e in result.errors)

    def test_missing_file_detected(self, tmp_path, monkeypatch):
        patch_workspace(monkeypatch, tmp_path)
        pf = PatchFile(
            relative_path="nonexistent.py",
            hunks=[simple_hunk(["x\n"], ["y\n"])],
        )
        p = make_patch("t1", [pf])
        v = PatchValidator()
        v._root = tmp_path.resolve()
        result = v.validate(p)
        assert not result.valid

    def test_valid_patch_passes(self, tmp_path, monkeypatch):
        patch_workspace(monkeypatch, tmp_path)
        original = "def add(a, b):\n    return a - b  # bug\n"
        h = make_file(tmp_path / "calc.py", original)
        pf = PatchFile(
            relative_path="calc.py",
            original_hash=h,
            hunks=[simple_hunk(["    return a - b  # bug\n"], ["    return a + b\n"], start=2)],
        )
        p = make_patch("t1", [pf])
        v = PatchValidator()
        v._root = tmp_path.resolve()
        result = v.validate(p)
        assert result.valid
        assert result.patch_hash is not None
        assert len(result.patch_hash) == 64


# ---------------------------------------------------------------------------
# PatchApplier
# ---------------------------------------------------------------------------

class TestPatchApplierBasic:
    def test_apply_modifies_file(self, tmp_path, monkeypatch):
        patch_workspace(monkeypatch, tmp_path)
        original = "def add(a, b):\n    return a - b  # bug\n"
        h = make_file(tmp_path / "calc.py", original)
        pf = PatchFile(
            relative_path="calc.py",
            original_hash=h,
            hunks=[simple_hunk(["    return a - b  # bug\n"], ["    return a + b\n"], start=2)],
        )
        p = make_patch("task-1", [pf])
        patch_hash = compute_patch_hash(p)
        applier = PatchApplier()
        applier._root = tmp_path.resolve()
        result = applier.apply(p, patch_hash)
        assert result.success is True
        assert "calc.py" in result.files_written
        new_content = (tmp_path / "calc.py").read_text()
        assert "return a + b" in new_content
        assert "return a - b" not in new_content

    def test_apply_saves_rollback_record(self, tmp_path, monkeypatch):
        patch_workspace(monkeypatch, tmp_path)
        h = make_file(tmp_path / "calc.py", "original\n")
        pf = PatchFile(
            relative_path="calc.py",
            original_hash=h,
            hunks=[simple_hunk(["original\n"], ["modified\n"])],
        )
        p = make_patch("task-1", [pf])
        patch_hash = compute_patch_hash(p)
        applier = PatchApplier()
        applier._root = tmp_path.resolve()
        result = applier.apply(p, patch_hash)
        assert result.rollback_record is not None
        assert "calc.py" in result.rollback_record.snapshots
        assert result.rollback_record.snapshots["calc.py"] == "original\n"

    def test_hash_mismatch_blocks_apply(self, tmp_path, monkeypatch):
        patch_workspace(monkeypatch, tmp_path)
        make_file(tmp_path / "f.py", "x\n")
        pf = PatchFile(
            relative_path="f.py",
            hunks=[simple_hunk(["x\n"], ["y\n"])],
        )
        p = make_patch("task-1", [pf])
        applier = PatchApplier()
        applier._root = tmp_path.resolve()
        # Pass a wrong hash
        result = applier.apply(p, "0" * 64)
        assert result.success is False
        assert "hash mismatch" in result.error.lower()

    def test_stale_file_hash_blocks_apply(self, tmp_path, monkeypatch):
        patch_workspace(monkeypatch, tmp_path)
        make_file(tmp_path / "f.py", "original\n")
        pf = PatchFile(
            relative_path="f.py",
            original_hash="0" * 64,  # Wrong pre-apply hash
            hunks=[simple_hunk(["original\n"], ["modified\n"])],
        )
        p = make_patch("task-1", [pf])
        patch_hash = compute_patch_hash(p)
        applier = PatchApplier()
        applier._root = tmp_path.resolve()
        result = applier.apply(p, patch_hash)
        assert result.success is False
        assert "modified" in result.error.lower() or "hash" in result.error.lower()

    def test_new_file_creation(self, tmp_path, monkeypatch):
        patch_workspace(monkeypatch, tmp_path)
        new_content_lines = ["+def hello():\n", "+    return 'hi'\n"]
        hunk = PatchHunk(
            original_start=1, original_count=0, new_start=1, new_count=2,
            lines=new_content_lines,
        )
        pf = PatchFile(relative_path="hello.py", hunks=[hunk], is_new_file=True)
        p = make_patch("task-1", [pf])
        patch_hash = compute_patch_hash(p)
        applier = PatchApplier()
        applier._root = tmp_path.resolve()
        result = applier.apply(p, patch_hash)
        assert result.success is True
        assert (tmp_path / "hello.py").exists()

    def test_sensitive_file_blocked_at_apply(self, tmp_path, monkeypatch):
        patch_workspace(monkeypatch, tmp_path)
        pf = PatchFile(relative_path=".env", hunks=[simple_hunk(["x\n"], ["y\n"])], is_new_file=True)
        p = make_patch("task-1", [pf])
        patch_hash = compute_patch_hash(p)
        applier = PatchApplier()
        applier._root = tmp_path.resolve()
        result = applier.apply(p, patch_hash)
        assert result.success is False
        assert "sensitive" in result.error.lower()


class TestPatchApplierRollback:
    def test_rollback_restores_original(self, tmp_path, monkeypatch):
        patch_workspace(monkeypatch, tmp_path)
        h = make_file(tmp_path / "calc.py", "original\n")
        pf = PatchFile(
            relative_path="calc.py",
            original_hash=h,
            hunks=[simple_hunk(["original\n"], ["modified\n"])],
        )
        p = make_patch("task-1", [pf])
        patch_hash = compute_patch_hash(p)
        applier = PatchApplier()
        applier._root = tmp_path.resolve()

        apply_result = applier.apply(p, patch_hash)
        assert apply_result.success
        assert (tmp_path / "calc.py").read_text() == "modified\n"

        rb_result = applier.rollback(apply_result.rollback_record, "task-1")
        assert rb_result.success is True
        assert (tmp_path / "calc.py").read_text() == "original\n"

    def test_rollback_fails_on_out_of_band_modification(self, tmp_path, monkeypatch):
        patch_workspace(monkeypatch, tmp_path)
        h = make_file(tmp_path / "calc.py", "original\n")
        pf = PatchFile(
            relative_path="calc.py",
            original_hash=h,
            hunks=[simple_hunk(["original\n"], ["modified\n"])],
        )
        p = make_patch("task-1", [pf])
        patch_hash = compute_patch_hash(p)
        applier = PatchApplier()
        applier._root = tmp_path.resolve()

        apply_result = applier.apply(p, patch_hash)
        assert apply_result.success

        # Simulate out-of-band modification after patch applied
        (tmp_path / "calc.py").write_text("someone else changed this\n")

        rb_result = applier.rollback(apply_result.rollback_record, "task-1")
        assert rb_result.success is False
        assert "modified" in rb_result.error.lower() or "unrelated" in rb_result.error.lower()

    def test_rollback_cross_task_rejected(self, tmp_path, monkeypatch):
        patch_workspace(monkeypatch, tmp_path)
        record = PatchRollbackRecord(
            patch_id="p1",
            task_id="task-A",
            patch_hash="abc",
            snapshots={"f.py": "original\n"},
            original_hashes={"f.py": "aaa"},
            post_patch_hashes={"f.py": "bbb"},
            created_at="2026-01-01T00:00:00+00:00",
        )
        applier = PatchApplier()
        applier._root = tmp_path.resolve()
        result = applier.rollback(record, "task-B")  # Wrong task
        assert result.success is False
        assert "mismatch" in result.error.lower() or "task" in result.error.lower()


# ---------------------------------------------------------------------------
# _apply_hunks unit tests
# ---------------------------------------------------------------------------

class TestApplyHunks:
    def test_basic_replacement(self):
        original = ["line1\n", "old_line\n", "line3\n"]
        hunk = PatchHunk(
            original_start=2, original_count=1, new_start=2, new_count=1,
            lines=["-old_line\n", "+new_line\n"],
        )
        result, err = _apply_hunks(original, [hunk])
        assert err is None
        assert "new_line\n" in result
        assert "old_line" not in result

    def test_add_lines(self):
        original = ["line1\n", "line2\n"]
        hunk = PatchHunk(
            original_start=2, original_count=0, new_start=2, new_count=1,
            lines=["+inserted\n"],
        )
        result, err = _apply_hunks(original, [hunk])
        assert err is None
        assert "inserted\n" in result

    def test_remove_lines(self):
        original = ["keep\n", "remove_me\n", "also_keep\n"]
        hunk = PatchHunk(
            original_start=2, original_count=1, new_start=2, new_count=0,
            lines=["-remove_me\n"],
        )
        result, err = _apply_hunks(original, [hunk])
        assert err is None
        assert "remove_me" not in result
        assert "keep\n" in result
        assert "also_keep\n" in result

    def test_context_mismatch_returns_error(self):
        original = ["line1\n", "actual_content\n"]
        hunk = PatchHunk(
            original_start=2, original_count=1, new_start=2, new_count=1,
            lines=["-expected_different\n", "+new\n"],
        )
        result, err = _apply_hunks(original, [hunk])
        assert err is not None
        assert "mismatch" in err.lower()
