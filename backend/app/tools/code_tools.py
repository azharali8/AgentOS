"""
Code Intelligence Tool for AgentOS Phase 3.

Registers the 'code' tool with the ToolRegistry.  Dispatches structured
operations (scan, search, read, symbols) to the respective code modules.

Security boundary
-----------------
* Every file path argument is validated by WorkspaceService.validate_path()
  inside the individual modules.
* Sensitive-file protection is enforced by each module via the centralized
  sensitive_files policy and by SecurityManager.is_allowed(file_path=...).
* No arbitrary command execution; pure Python logic only.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from backend.app.code.language_detector import LanguageDetector
from backend.app.code.project_detector import ProjectDetector
from backend.app.code.reader import CodeReader
from backend.app.code.scanner import RepositoryScanner
from backend.app.code.search import CodeSearch
from backend.app.code.symbols import SymbolExtractor
from backend.app.models.tool import RiskLevel, ToolMetadata, ToolRequest, ToolResult
from backend.app.tools.base import BaseTool
from backend.app.tools.registry import ToolRegistry


def _dc_to_dict(obj: Any) -> Any:
    """Recursively convert dataclass instances to plain dicts."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _dc_to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_dc_to_dict(i) for i in obj]
    return obj


class CodeTool(BaseTool):
    """Code intelligence tool: scan, search, read, symbols."""

    _OPERATIONS = ("scan", "search", "read", "symbols")

    def __init__(self) -> None:
        super().__init__(ToolMetadata(
            name="code",
            description=(
                "Repository intelligence: scan directory structure, search for patterns, "
                "read file slices, and extract Python AST symbols."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": list(self._OPERATIONS),
                        "description": "Operation to perform.",
                    },
                    "path": {
                        "type": "string",
                        "description": (
                            "Target path relative to WORKSPACE_ROOT. "
                            "For 'scan': a directory. "
                            "For 'search': a directory or file. "
                            "For 'read'/'symbols': a file."
                        ),
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query string (only for 'search').",
                    },
                    "is_regex": {
                        "type": "boolean",
                        "description": "Treat query as regex (default false, only for 'search').",
                    },
                    "include_extensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Extension filter for 'search' (e.g. ['.py', '.ts']).",
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "description": "Case-sensitive search (default true).",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "First line to read, 1-indexed (only for 'read').",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Last line to read, inclusive, 1-indexed (only for 'read').",
                    },
                },
                "required": ["operation"],
            },
            risk_level=RiskLevel.LOW,
        ))
        self._scanner = RepositoryScanner()
        self._language_detector = LanguageDetector()
        self._project_detector = ProjectDetector()
        self._searcher = CodeSearch()
        self._reader = CodeReader()
        self._symbols = SymbolExtractor()

    # ------------------------------------------------------------------
    # BaseTool interface
    # ------------------------------------------------------------------

    def execute(self, request: ToolRequest) -> ToolResult:
        op = request.arguments.get("operation")
        if op not in self._OPERATIONS:
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error=f"Unknown code operation: '{op}'. Must be one of {self._OPERATIONS}.",
            )

        try:
            if op == "scan":
                return self._do_scan(request.arguments)
            elif op == "search":
                return self._do_search(request.arguments)
            elif op == "read":
                return self._do_read(request.arguments)
            elif op == "symbols":
                return self._do_symbols(request.arguments)
        except ValueError as exc:
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error=str(exc),
            )
        except Exception as exc:  # pragma: no cover
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error=f"Unexpected error in code.{op}: {exc}",
            )

    # ------------------------------------------------------------------
    # Operation implementations
    # ------------------------------------------------------------------

    def _do_scan(self, args: dict) -> ToolResult:
        path = args.get("path", ".")
        scan_result = self._scanner.scan(relative_path=path)
        lang_result = self._language_detector.detect(scan_result.files)
        project_result = self._project_detector.detect(scan_result.files)

        # Build a compact summary — do NOT put all raw source in result
        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            data={
                "root": scan_result.root,
                "total_files": scan_result.total_files,
                "total_dirs": scan_result.total_dirs,
                "total_bytes": scan_result.total_bytes,
                "truncated": scan_result.truncated,
                "truncation_reason": scan_result.truncation_reason,
                "errors": scan_result.errors,
                "languages": _dc_to_dict(lang_result.languages),
                "primary_language": lang_result.primary_language,
                "frameworks": project_result.frameworks,
                "has_docker": project_result.has_docker,
                "has_alembic": project_result.has_alembic,
                "has_pytest": project_result.has_pytest,
                "has_jest": project_result.has_jest,
                "detected_configs": project_result.detected_configs[:20],  # cap for safety
                # File listing: only metadata, not content
                "files": [
                    {
                        "path": f.relative_path,
                        "size_bytes": f.size_bytes,
                        "extension": f.extension,
                        "is_test": f.is_test_file,
                        "is_config": f.is_config_file,
                        "is_doc": f.is_doc_file,
                    }
                    for f in scan_result.files
                ],
            },
        )

    def _do_search(self, args: dict) -> ToolResult:
        query = args.get("query")
        if not query:
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error="'query' is required for code.search",
            )
        path = args.get("path", ".")
        search_result = self._searcher.search(
            query=query,
            relative_path=path,
            is_regex=bool(args.get("is_regex", False)),
            include_extensions=args.get("include_extensions"),
            case_sensitive=bool(args.get("case_sensitive", True)),
        )
        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            data={
                "query": search_result.query,
                "is_regex": search_result.is_regex,
                "files_searched": search_result.files_searched,
                "match_count": len(search_result.matches),
                "truncated": search_result.truncated,
                "truncation_reason": search_result.truncation_reason,
                "errors": search_result.errors,
                "matches": [
                    {
                        "path": m.relative_path,
                        "line": m.line_number,
                        "content": m.line_content,
                    }
                    for m in search_result.matches
                ],
            },
        )

    def _do_read(self, args: dict) -> ToolResult:
        path = args.get("path")
        if not path:
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error="'path' is required for code.read",
            )
        read_result = self._reader.read(
            relative_path=path,
            start_line=int(args.get("start_line", 1)),
            end_line=args.get("end_line"),
        )
        if read_result.error:
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error=read_result.error,
            )
        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            data={
                "path": read_result.relative_path,
                "start_line": read_result.start_line,
                "end_line": read_result.end_line,
                "total_lines": read_result.total_lines,
                "truncated": read_result.truncated,
                "truncation_reason": read_result.truncation_reason,
                # Numbered lines for LLM consumption
                "lines": [
                    {"line": read_result.start_line + i, "content": l}
                    for i, l in enumerate(read_result.lines)
                ],
            },
        )

    def _do_symbols(self, args: dict) -> ToolResult:
        path = args.get("path")
        if not path:
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error="'path' is required for code.symbols",
            )
        sym_result = self._symbols.extract(relative_path=path)
        if sym_result.error:
            return ToolResult(
                tool_name=self.metadata.name,
                success=False,
                error=sym_result.error,
            )
        return ToolResult(
            tool_name=self.metadata.name,
            success=True,
            data={
                "path": sym_result.relative_path,
                "total_lines": sym_result.total_lines,
                "symbol_count": len(sym_result.symbols),
                "symbols": [
                    {
                        "name": s.name,
                        "type": s.symbol_type,
                        "line": s.line,
                        "end_line": s.end_line,
                        "parent_class": s.parent_class,
                    }
                    for s in sym_result.symbols
                ],
            },
        )


# Register on import
ToolRegistry.register(CodeTool())
