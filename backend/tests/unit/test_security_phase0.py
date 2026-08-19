import pytest
import os
import platform
from pathlib import Path
from backend.app.config.settings import settings
from backend.app.services.workspace_service import WorkspaceService
from backend.app.tools.terminal import TerminalTool
from backend.app.models.tool import ToolRequest

def test_workspace_root_correctness():
    # Workspace root must match the specific AgentOS/workspace resolution
    expected_root = Path(__file__).resolve().parents[3] / "workspace"
    actual_root = WorkspaceService.get_workspace_root()
    assert actual_root == expected_root

def test_workspace_traversal():
    with pytest.raises(ValueError, match="Path traversal.*detected"):
        WorkspaceService.validate_path("../outside")

def test_absolute_path_escape():
    root = WorkspaceService.get_workspace_root()
    escape_path = str(root.parent / "outside")
    with pytest.raises(ValueError, match="Path outside workspace"):
        WorkspaceService.validate_path(escape_path)

def test_windows_path_escape():
    if os.name == 'nt':
        with pytest.raises(ValueError, match="Windows drive escape detected"):
            WorkspaceService.validate_path("Z:\\escaped")

def test_basic_allowed_command():
    tool = TerminalTool()
    req = ToolRequest(tool_name="terminal", arguments={"command": "python --version"})
    res = tool.execute(req)
    assert res.success is True
    assert "Python" in res.data or res.data == ""

def test_pipe_injection():
    tool = TerminalTool()
    req = ToolRequest(tool_name="terminal", arguments={"command": "echo hello | whoami"})
    res = tool.execute(req)
    assert res.success is False
    assert "Shell construct '|' not allowed" in res.error

def test_and_and_injection():
    tool = TerminalTool()
    req = ToolRequest(tool_name="terminal", arguments={"command": "echo hello && whoami"})
    res = tool.execute(req)
    assert res.success is False
    assert "Shell construct" in res.error

def test_semicolon_injection():
    tool = TerminalTool()
    req = ToolRequest(tool_name="terminal", arguments={"command": "echo hello; whoami"})
    res = tool.execute(req)
    assert res.success is False
    assert "Shell construct ';' not allowed" in res.error

def test_redirect_injection():
    tool = TerminalTool()
    req = ToolRequest(tool_name="terminal", arguments={"command": "echo hello > file.txt"})
    res = tool.execute(req)
    assert res.success is False
    assert "Shell construct '>' not allowed" in res.error

def test_command_substitution():
    tool = TerminalTool()
    req = ToolRequest(tool_name="terminal", arguments={"command": "echo $(whoami)"})
    res = tool.execute(req)
    assert res.success is False
    assert "Shell construct '$(' not allowed" in res.error

def test_backtick_substitution():
    tool = TerminalTool()
    req = ToolRequest(tool_name="terminal", arguments={"command": "echo `whoami`"})
    res = tool.execute(req)
    assert res.success is False
    assert "Shell construct '`' not allowed" in res.error

def test_shell_wrapper():
    tool = TerminalTool()
    req = ToolRequest(tool_name="terminal", arguments={"command": "cmd /c whoami"})
    res = tool.execute(req)
    assert res.success is False
    
    req = ToolRequest(tool_name="terminal", arguments={"command": "powershell -Command whoami"})
    res = tool.execute(req)
    assert res.success is False

def test_python_unsafe_arguments():
    tool = TerminalTool()
    cmd = "python -c \"print('test')\""
    req = ToolRequest(tool_name="terminal", arguments={"command": cmd})
    res = tool.execute(req)
    assert res.success is False
    assert "-c or -m arguments are not allowed" in res.error

def test_working_directory_escape():
    tool = TerminalTool()
    req = ToolRequest(tool_name="terminal", arguments={"command": "echo hello", "cwd": "../outside"})
    res = tool.execute(req)
    assert res.success is False
    assert "Path traversal" in res.error
