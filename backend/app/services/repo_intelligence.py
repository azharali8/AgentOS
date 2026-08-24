"""
AgentOS Phase 12 — Repository Intelligence Service.

Provides secure, bounded repository analysis:
- Discovers project structure, manifests, and technologies.
- Identifies entry points and test directories.
- Resolves relevant source files and symbol maps for a given prompt/task.
- Tracks recently modified files in the workspace.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from backend.app.code.reader import CodeReader
from backend.app.code.scanner import RepositoryScanner
from backend.app.code.search import CodeSearch
from backend.app.code.symbols import SymbolExtractor
from backend.app.config.settings import settings
from backend.app.services.workspace_service import WorkspaceService


class RepoIntelligence:
    """Bounded, secure intelligence service for codebase exploration."""

    def __init__(self, workspace_root: Optional[str] = None) -> None:
        self.workspace_root = Path(workspace_root or settings.WORKSPACE_ROOT).resolve()
        self.scanner = RepositoryScanner()
        self.reader = CodeReader()
        self.searcher = CodeSearch()
        self.symbols = SymbolExtractor()

    def inspect_overview(self) -> Dict[str, Any]:
        """Inspect workspace structure, frameworks, dependencies, and entry points."""
        scan_res = self.scanner.scan()
        file_paths = [f.relative_path for f in scan_res.files]

        # Detect technologies / dependencies
        detected_frameworks = []
        if any(f in ("pyproject.toml", "setup.py", "requirements.txt") for f in file_paths):
            detected_frameworks.append("python")
        if any(f in ("package.json", "tsconfig.json") for f in file_paths):
            detected_frameworks.append("node_typescript")
        if any(f in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml") for f in file_paths):
            detected_frameworks.append("docker")
        if any(f.startswith(".github/workflows") for f in file_paths):
            detected_frameworks.append("github_actions")

        # Detect test directories / files
        test_files = [f for f in file_paths if "test" in f.lower() or f.startswith("tests/")]

        # Detect entry points
        entry_points = [f for f in file_paths if f in ("main.py", "app.py", "index.ts", "index.js", "src/main.py", "backend/app/main.py")]

        return {
            "total_files": scan_res.total_files,
            "total_directories": getattr(scan_res, "total_dirs", 0),
            "frameworks": detected_frameworks,
            "test_files": test_files[:20],
            "entry_points": entry_points,
            "root_files": [f for f in file_paths if "/" not in f and "\\" not in f][:30],
        }

    def find_relevant_files(self, instruction: str, max_files: int = 5) -> List[str]:
        """Identify candidate files relevant to a task instruction without overloading context."""
        scan_res = self.scanner.scan()
        all_files = [f.relative_path for f in scan_res.files]
        if not all_files:
            return []

        instruction_lower = instruction.lower()
        scored_files: List[tuple[int, str]] = []

        # Keywords extraction from instruction
        keywords = set(k.strip(".,;:\"'()[]{}") for k in instruction_lower.split() if len(k) > 3)

        for rel_path in all_files:
            path_lower = rel_path.lower()
            score = 0
            # Direct match in filename
            for kw in keywords:
                if kw in path_lower:
                    score += 3
            
            # Match in file content (top lines snippet)
            try:
                content_res = self.reader.read(rel_path, start_line=1, end_line=40)
                content_str = "\n".join(content_res.lines) if content_res.lines else ""
                if content_str:
                    c_lower = content_str.lower()
                    for kw in keywords:
                        if kw in c_lower:
                            score += 1
            except Exception:
                pass

            if score > 0:
                scored_files.append((score, rel_path))

        # Sort descending by relevance score
        scored_files.sort(key=lambda x: x[0], reverse=True)
        return [path for _, path in scored_files[:max_files]]

    def extract_file_symbols(self, relative_path: str) -> Dict[str, Any]:
        """Extract AST symbols and signature map for a given file."""
        if not relative_path.endswith(".py"):
            return {"symbols": [], "error": "AST extraction only supported for Python files"}
        
        sym_res = self.symbols.extract(relative_path)
        if not sym_res.symbols:
            return {"symbols": [], "error": sym_res.error}

        return {
            "file": relative_path,
            "symbols": [
                {
                    "name": s.name,
                    "type": s.symbol_type,
                    "line": s.line,
                    "end_line": s.end_line,
                    "parent_class": s.parent_class,
                }
                for s in sym_res.symbols
            ],
            "total_lines": sym_res.total_lines,
        }

    def get_bounded_context(self, instruction: str) -> Dict[str, Any]:
        """Assemble a bounded, security-validated context bundle for agents."""
        overview = self.inspect_overview()
        target_files = self.find_relevant_files(instruction, max_files=4)

        file_contexts: Dict[str, Any] = {}
        for fpath in target_files:
            try:
                read_res = self.reader.read(fpath, start_line=1, end_line=100)
                content_str = "\n".join(read_res.lines) if read_res.lines else ""
                symbols_info = self.extract_file_symbols(fpath) if fpath.endswith(".py") else {}
                file_contexts[fpath] = {
                    "content": content_str,
                    "symbols": symbols_info.get("symbols", []),
                }
            except Exception:
                pass

        return {
            "overview": overview,
            "relevant_files": target_files,
            "file_contexts": file_contexts,
        }
