"""
Tests for backend/app/tools/git.py — Structured Read-Only Git Tool

Covers:
- All five allowed operations are accepted (status, branch, log, diff, show)
- All mutation operations are rejected without execution
- Unknown operations are rejected
- git.log max_count cap (100)
- git.log invalid max_count rejected
- git.diff ref validation (alphanumeric, dots, dashes)
- git.diff injection via ref rejected (semicolons, pipes, $(), etc.)
- git.diff path traversal rejected (..)
- git.diff UNC path rejected
- git.diff absolute path rejected
- git.show requires ref
- git.show ref injection rejected
- shell=False confirmed (no shell expansion in args)
- Workspace cwd is respected
- Output truncated at MAX_OUTPUT_SIZE
- Timeout is respected
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.app.models.tool import ToolRequest
from backend.app.tools.git import GitTool, _validate_ref, _validate_relative_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_request(op: str, **kwargs) -> ToolRequest:
    return ToolRequest(tool_name="git", arguments={"operation": op, **kwargs})


def make_git() -> GitTool:
    return GitTool()


def mock_run_success(output: str = "ok\n"):
    """Return a mock for subprocess.run that simulates git success."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = output
    mock_result.stderr = ""
    return mock_result


def mock_run_failure(stderr: str = "fatal: not a git repo", code: int = 128):
    mock_result = MagicMock()
    mock_result.returncode = code
    mock_result.stdout = ""
    mock_result.stderr = stderr
    return mock_result


# ---------------------------------------------------------------------------
# Allowed operations — command construction (via mock)
# ---------------------------------------------------------------------------

class TestGitAllowedOperations:
    @patch("backend.app.tools.git.subprocess.run")
    def test_status_succeeds(self, mock_run):
        mock_run.return_value = mock_run_success("On branch main\n")
        git = make_git()
        result = git.execute(make_request("status"))
        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "git"
        assert cmd[1] == "status"
        assert result.success is True

    @patch("backend.app.tools.git.subprocess.run")
    def test_status_short_flag(self, mock_run):
        mock_run.return_value = mock_run_success("M  main.py\n")
        git = make_git()
        result = git.execute(make_request("status", short=True))
        cmd = mock_run.call_args[0][0]
        assert "--short" in cmd

    @patch("backend.app.tools.git.subprocess.run")
    def test_branch_succeeds(self, mock_run):
        mock_run.return_value = mock_run_success("* main\n")
        git = make_git()
        result = git.execute(make_request("branch"))
        cmd = mock_run.call_args[0][0]
        assert "branch" in cmd
        assert result.success is True

    @patch("backend.app.tools.git.subprocess.run")
    def test_branch_all_flag(self, mock_run):
        mock_run.return_value = mock_run_success("* main\n  remotes/origin/main\n")
        git = make_git()
        result = git.execute(make_request("branch", all_branches=True))
        cmd = mock_run.call_args[0][0]
        assert "--all" in cmd

    @patch("backend.app.tools.git.subprocess.run")
    def test_log_succeeds(self, mock_run):
        mock_run.return_value = mock_run_success("abc1234 Initial commit\n")
        git = make_git()
        result = git.execute(make_request("log"))
        cmd = mock_run.call_args[0][0]
        assert "log" in cmd
        assert result.success is True

    @patch("backend.app.tools.git.subprocess.run")
    def test_log_max_count_passed(self, mock_run):
        mock_run.return_value = mock_run_success()
        git = make_git()
        git.execute(make_request("log", max_count=10))
        cmd = mock_run.call_args[0][0]
        assert "--max-count=10" in cmd

    @patch("backend.app.tools.git.subprocess.run")
    def test_log_max_count_capped_at_100(self, mock_run):
        mock_run.return_value = mock_run_success()
        git = make_git()
        git.execute(make_request("log", max_count=9999))
        cmd = mock_run.call_args[0][0]
        assert "--max-count=100" in cmd

    @patch("backend.app.tools.git.subprocess.run")
    def test_log_oneline_flag(self, mock_run):
        mock_run.return_value = mock_run_success()
        git = make_git()
        git.execute(make_request("log", oneline=True))
        cmd = mock_run.call_args[0][0]
        assert "--oneline" in cmd

    @patch("backend.app.tools.git.subprocess.run")
    def test_diff_no_args(self, mock_run):
        mock_run.return_value = mock_run_success("diff output\n")
        git = make_git()
        result = git.execute(make_request("diff"))
        assert result.success is True

    @patch("backend.app.tools.git.subprocess.run")
    def test_diff_with_valid_ref(self, mock_run):
        mock_run.return_value = mock_run_success()
        git = make_git()
        git.execute(make_request("diff", ref="HEAD~1"))
        cmd = mock_run.call_args[0][0]
        assert "HEAD~1" in cmd

    @patch("backend.app.tools.git.subprocess.run")
    def test_diff_with_path(self, mock_run):
        mock_run.return_value = mock_run_success()
        git = make_git()
        git.execute(make_request("diff", path="src/main.py"))
        cmd = mock_run.call_args[0][0]
        assert "--" in cmd
        assert "src/main.py" in cmd

    @patch("backend.app.tools.git.subprocess.run")
    def test_show_with_ref(self, mock_run):
        mock_run.return_value = mock_run_success("commit abc...\n")
        git = make_git()
        result = git.execute(make_request("show", ref="abc1234"))
        assert result.success is True
        cmd = mock_run.call_args[0][0]
        assert "abc1234" in cmd

    @patch("backend.app.tools.git.subprocess.run")
    def test_shell_false_always(self, mock_run):
        """Verify shell=False is always passed to subprocess.run."""
        mock_run.return_value = mock_run_success()
        git = make_git()
        git.execute(make_request("status"))
        kwargs = mock_run.call_args[1]
        assert kwargs.get("shell") is False

    @patch("backend.app.tools.git.subprocess.run")
    def test_cwd_is_workspace_root(self, mock_run):
        """Verify cwd is always WORKSPACE_ROOT, never user-supplied."""
        mock_run.return_value = mock_run_success()
        git = make_git()
        git.execute(make_request("status"))
        kwargs = mock_run.call_args[1]
        assert kwargs.get("cwd") == str(git._workspace)


# ---------------------------------------------------------------------------
# Mutation operation rejection
# ---------------------------------------------------------------------------

class TestGitMutationRejection:
    @pytest.mark.parametrize("mutation_op", [
        "push", "pull", "merge", "rebase", "reset", "clean",
        "checkout", "switch", "commit", "tag", "stash",
        "cherry-pick", "fetch", "remote", "rm", "add",
        "restore", "revert",
    ])
    def test_mutation_rejected(self, mutation_op):
        git = make_git()
        result = git.execute(make_request(mutation_op))
        assert result.success is False
        assert "mutation" in result.error.lower() or "permitted" in result.error.lower() or "write" in result.error.lower()

    def test_unknown_operation_rejected(self):
        git = make_git()
        result = git.execute(make_request("arbitrary-command"))
        assert result.success is False


# ---------------------------------------------------------------------------
# git.log argument validation
# ---------------------------------------------------------------------------

class TestGitLogValidation:
    @patch("backend.app.tools.git.subprocess.run")
    def test_invalid_max_count_zero(self, mock_run):
        mock_run.return_value = mock_run_success()
        git = make_git()
        result = git.execute(make_request("log", max_count=0))
        assert result.success is False

    @patch("backend.app.tools.git.subprocess.run")
    def test_invalid_max_count_string(self, mock_run):
        mock_run.return_value = mock_run_success()
        git = make_git()
        result = git.execute(make_request("log", max_count="DROP TABLE"))
        assert result.success is False


# ---------------------------------------------------------------------------
# Ref validation (injection prevention)
# ---------------------------------------------------------------------------

class TestRefValidation:
    @pytest.mark.parametrize("safe_ref", [
        "HEAD", "HEAD~1", "main", "origin/main",
        "abc1234", "v1.0.0", "feature/my-branch",
        "refs/heads/main",
    ])
    def test_valid_refs_accepted(self, safe_ref):
        assert _validate_ref(safe_ref) is None

    @pytest.mark.parametrize("dangerous_ref", [
        "main; rm -rf /",
        "$(rm -rf /)",
        "`rm -rf /`",
        "main | cat /etc/passwd",
        "main && curl evil.com",
        "main\necho pwned",
        "../../../etc/passwd",
        "HEAD\x00injected",
        "main > /tmp/out",
        "main < /etc/passwd",
    ])
    def test_dangerous_refs_rejected(self, dangerous_ref):
        error = _validate_ref(dangerous_ref)
        assert error is not None, f"Expected ref '{dangerous_ref}' to be rejected"

    def test_traversal_in_ref_rejected(self):
        assert _validate_ref("../../etc/shadow") is not None

    def test_empty_ref_rejected(self):
        assert _validate_ref("") is not None

    def test_too_long_ref_rejected(self):
        assert _validate_ref("a" * 300) is not None


# ---------------------------------------------------------------------------
# Path validation for git diff
# ---------------------------------------------------------------------------

class TestGitDiffPathValidation:
    def test_valid_relative_path(self):
        assert _validate_relative_path("src/main.py") is None

    def test_valid_nested_path(self):
        assert _validate_relative_path("backend/app/tools/git.py") is None

    def test_traversal_rejected(self):
        assert _validate_relative_path("../../etc/passwd") is not None

    def test_absolute_path_rejected(self):
        if sys.platform == "win32":
            assert _validate_relative_path("C:\\Windows\\system32") is not None
        else:
            assert _validate_relative_path("/etc/passwd") is not None

    def test_unc_path_rejected(self):
        assert _validate_relative_path("\\\\server\\share\\file.py") is not None

    def test_double_slash_rejected(self):
        assert _validate_relative_path("//etc/passwd") is not None

    def test_empty_path_rejected(self):
        assert _validate_relative_path("") is not None


# ---------------------------------------------------------------------------
# git.show validation
# ---------------------------------------------------------------------------

class TestGitShow:
    def test_show_without_ref_fails(self):
        git = make_git()
        result = git.execute(make_request("show"))
        assert result.success is False
        assert "ref" in result.error.lower() or "required" in result.error.lower()

    @patch("backend.app.tools.git.subprocess.run")
    def test_show_injection_rejected(self, mock_run):
        git = make_git()
        result = git.execute(make_request("show", ref="HEAD; cat /etc/passwd"))
        assert result.success is False
        # subprocess.run should NOT have been called with injected command
        assert not mock_run.called


# ---------------------------------------------------------------------------
# Timeout and git not found
# ---------------------------------------------------------------------------

class TestGitEdgeCases:
    @patch("backend.app.tools.git.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=30))
    def test_timeout_handled(self, mock_run):
        git = make_git()
        result = git.execute(make_request("status"))
        assert result.success is False
        assert "timed out" in result.error.lower()

    @patch("backend.app.tools.git.subprocess.run", side_effect=FileNotFoundError)
    def test_git_not_found_handled(self, mock_run):
        git = make_git()
        result = git.execute(make_request("status"))
        assert result.success is False
        assert "not found" in result.error.lower() or "git" in result.error.lower()

    @patch("backend.app.tools.git.subprocess.run")
    def test_output_is_in_data(self, mock_run):
        mock_run.return_value = mock_run_success("On branch main\n")
        git = make_git()
        result = git.execute(make_request("status"))
        assert result.success is True
        assert result.data["output"] == "On branch main\n"
        assert result.data["operation"] == "status"

    @patch("backend.app.tools.git.subprocess.run")
    def test_nonzero_returncode_is_failure(self, mock_run):
        mock_run.return_value = mock_run_failure("fatal: not a git repository")
        git = make_git()
        result = git.execute(make_request("status"))
        assert result.success is False
        assert "128" in result.error or "fatal" in result.error
