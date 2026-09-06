from backend.app.tools.base import BaseTool
from backend.app.models.tool import ToolMetadata, RiskLevel, ToolRequest, ToolResult
from backend.app.services.workspace_service import WorkspaceService
from backend.app.config.settings import settings
import subprocess
import platform
import shlex
import os

class TerminalTool(BaseTool):
    def __init__(self):
        super().__init__(ToolMetadata(
            name="terminal",
            description="Execute basic terminal commands safely",
            input_schema={
                "type": "object", 
                "properties": {
                    "operation": {"type": "string", "enum": ["execute"]}, 
                    "command": {"type": "string"},
                    "cwd": {"type": "string"}
                }
            },
            risk_level=RiskLevel.MEDIUM
        ))
        
    def _is_shell_wrapper(self, cmd_base: str, args: list) -> bool:
        cmd_lower = cmd_base.lower()
        if cmd_lower in ["cmd", "cmd.exe"] and "/c" in [a.lower() for a in args]:
            return True
        if cmd_lower in ["powershell", "powershell.exe", "pwsh", "pwsh.exe"]:
            for arg in args:
                if arg.lower() in ["-command", "-c", "-encodedcommand", "-e"]:
                    return True
        if cmd_lower in ["bash", "sh", "zsh"] and "-c" in args:
            return True
        return False

    def execute(self, request: ToolRequest) -> ToolResult:
        command = request.arguments.get("command", "")
        if not command:
            return ToolResult(tool_name=self.metadata.name, success=False, error="Missing command")
            
        # 1. Reject shell constructs in raw string
        forbidden_constructs = ["|", "||", "&", "&&", ";", ">", ">>", "<", "<<", "`", "$(", "${", "2>", "2>>", "2>&1"]
        for construct in forbidden_constructs:
            if construct in command:
                return ToolResult(tool_name=self.metadata.name, success=False, error=f"Shell construct '{construct}' not allowed")

        # 2. Command parser
        try:
            parsed_command = shlex.split(command, posix=(platform.system() != "Windows"))
        except ValueError as e:
            return ToolResult(tool_name=self.metadata.name, success=False, error=f"Invalid command syntax: {e}")

        if not parsed_command:
            return ToolResult(tool_name=self.metadata.name, success=False, error="Empty command")
            
        cmd_base = parsed_command[0]
        args = parsed_command[1:]

        # 3. Reject shell wrappers
        if self._is_shell_wrapper(cmd_base, args):
            return ToolResult(tool_name=self.metadata.name, success=False, error="Shell wrappers are not allowed")

        # 4. Executable allowlist (Platform-aware)
        is_windows = platform.system() == "Windows"
        if is_windows:
            allowlist = ["echo", "dir", "where", "python", "git"]
        else:
            allowlist = ["echo", "ls", "pwd", "which", "python3", "python", "git"]
            
        if cmd_base.lower() not in allowlist and cmd_base not in allowlist:
            return ToolResult(tool_name=self.metadata.name, success=False, error=f"Command {cmd_base} not in allowlist")

        # 5. Argument validation
        if cmd_base.lower() in ["python", "python3"]:
            if "-c" in args or "-m" in args:
                return ToolResult(tool_name=self.metadata.name, success=False, error="python -c or -m arguments are not allowed in V0.1")

        # 6. Working directory validation
        cwd_req = request.arguments.get("cwd")
        if cwd_req:
            try:
                target_cwd = WorkspaceService.validate_path(cwd_req)
            except ValueError as e:
                return ToolResult(tool_name=self.metadata.name, success=False, error=str(e))
        else:
            target_cwd = WorkspaceService.get_workspace_root()

        # 7. Security/Risk Manager execution with limits
        try:
            # shell=False is strictly required
            process = subprocess.Popen(
                parsed_command,
                shell=False,
                cwd=str(target_cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            try:
                stdout, stderr = process.communicate(timeout=settings.TERMINAL_TIMEOUT)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                return ToolResult(tool_name=self.metadata.name, success=False, error="Command execution timed out")
                
            # Limit output size
            if len(stdout) > settings.MAX_OUTPUT_SIZE:
                stdout = stdout[:settings.MAX_OUTPUT_SIZE] + "\n...[OUTPUT TRUNCATED]..."
            if len(stderr) > settings.MAX_OUTPUT_SIZE:
                stderr = stderr[:settings.MAX_OUTPUT_SIZE] + "\n...[ERROR TRUNCATED]..."

            if process.returncode == 0:
                output = stdout if stdout else stderr
                return ToolResult(tool_name=self.metadata.name, success=True, data=output)
            else:
                return ToolResult(tool_name=self.metadata.name, success=False, error=stderr)
        except Exception as e:
            return ToolResult(tool_name=self.metadata.name, success=False, error=str(e))

    def validate_command(self, command: str) -> dict:
        """
        Dry-run security check for a command string.
        Returns {"allowed": True} if command passes all gates,
        or {"allowed": False, "reason": "<why>"} if rejected.
        Does NOT execute the command.
        """
        forbidden_constructs = ["|", "||", "&", "&&", ";", ">", ">>", "<", "<<", "`", "$(", "${", "2>", "2>>", "2>&1"]
        for construct in forbidden_constructs:
            if construct in command:
                return {"allowed": False, "reason": f"Shell construct '{construct}' not allowed"}

        try:
            parsed = shlex.split(command, posix=(platform.system() != "Windows"))
        except ValueError as exc:
            return {"allowed": False, "reason": f"Invalid command syntax: {exc}"}

        if not parsed:
            return {"allowed": False, "reason": "Empty command"}

        cmd_base = parsed[0]
        args = parsed[1:]

        if self._is_shell_wrapper(cmd_base, args):
            return {"allowed": False, "reason": "Shell wrappers are not allowed"}

        return {"allowed": True}


from backend.app.tools.registry import ToolRegistry
ToolRegistry.register(TerminalTool())
