import os
from pathlib import Path
from backend.app.config.settings import settings

class WorkspaceService:
    @staticmethod
    def get_workspace_root() -> Path:
        configured_root = Path(settings.WORKSPACE_ROOT).resolve()
        expected_root = Path(__file__).resolve().parents[3] / "workspace"
        
        # Add a validation that the final workspace root is the intended AgentOS workspace
        # We ensure that the configured workspace root matches our expected secure path.
        if configured_root != expected_root:
            raise ValueError(f"Security Policy Violation: WORKSPACE_ROOT must be {expected_root}")
            
        if not configured_root.exists():
            configured_root.mkdir(parents=True, exist_ok=True)
            
        return configured_root

    @staticmethod
    def validate_path(requested_path: str) -> Path:
        root = WorkspaceService.get_workspace_root()
        req_path = str(requested_path)
        
        # Reject UNC paths
        if req_path.startswith(r"\\") or req_path.startswith("//"):
            raise ValueError("UNC paths are not allowed")
            
        # Reject simple traversal early
        if ".." in Path(req_path).parts:
            raise ValueError("Path traversal ('..') detected")
            
        if os.path.isabs(req_path):
            target = Path(req_path).resolve()
            # Windows drive escape check
            if os.name == 'nt' and target.drive.lower() != root.drive.lower():
                raise ValueError("Windows drive escape detected")
        else:
            target = (root / req_path).resolve()
            
        # Ensure it stays within the workspace
        try:
            target.relative_to(root)
        except ValueError:
            raise ValueError(f"Path outside workspace: {requested_path}")
            
        return target
