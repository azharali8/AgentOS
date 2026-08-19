"""
Pure AST-based Python Symbol Extractor for AgentOS Phase 3.

Parses Python source code using the standard-library `ast` module in
PURE STATIC MODE — no modules are imported or executed.

Extracts:
* Module-level functions (`function`)
* Async module-level functions (`async_function`)
* Classes (`class`)
* Methods inside classes (`method`, `async_method`)
* Module-level imports (`import`, `import_from`)

Each symbol carries: name, type, line, end_line (when available).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from backend.app.config.settings import settings
from backend.app.security.sensitive_files import is_sensitive_path, sensitive_file_reason
from backend.app.services.workspace_service import WorkspaceService


@dataclass
class Symbol:
    name: str
    symbol_type: str     # "function" | "async_function" | "class" | "method" |
                         # "async_method" | "import" | "import_from"
    line: int            # 1-indexed start line
    end_line: Optional[int] = None  # None for imports (no end_line from AST)
    parent_class: Optional[str] = None  # Set for methods


@dataclass
class SymbolsResult:
    relative_path: str
    symbols: list[Symbol] = field(default_factory=list)
    error: Optional[str] = None
    total_lines: int = 0


class SymbolExtractor:
    """Extract structural symbols from a Python source file via AST."""

    def __init__(self) -> None:
        self._root = Path(settings.WORKSPACE_ROOT).resolve()

    def extract(self, relative_path: str) -> SymbolsResult:
        """Parse *relative_path* and return all top-level symbols.

        Args:
            relative_path: Path relative to WORKSPACE_ROOT to a Python file.

        Returns:
            SymbolsResult with a flat list of Symbol objects.
        """
        target = WorkspaceService.validate_path(relative_path)
        rel_str = str(target.relative_to(self._root)).replace("\\", "/")
        result = SymbolsResult(relative_path=rel_str)

        # Sensitive-file gate
        if is_sensitive_path(rel_str):
            result.error = f"Access denied: {sensitive_file_reason(rel_str)}"
            return result

        if not target.exists():
            result.error = f"File not found: {relative_path}"
            return result

        if not target.is_file():
            result.error = f"Not a file: {relative_path}"
            return result

        # Only support Python files
        if target.suffix.lower() != ".py":
            result.error = f"Symbol extraction only supported for .py files (got {target.suffix})"
            return result

        # Size guard
        size = target.stat().st_size
        if size > settings.MAX_FILE_SIZE:
            result.error = (
                f"File too large ({size} bytes > MAX_FILE_SIZE {settings.MAX_FILE_SIZE})"
            )
            return result

        # Read source
        try:
            source = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            result.error = str(exc)
            return result

        result.total_lines = len(source.splitlines())

        # Parse — strict static analysis, no execution
        try:
            tree = ast.parse(source, filename=rel_str)
        except SyntaxError as exc:
            result.error = f"Syntax error: {exc}"
            return result

        symbols: list[Symbol] = []

        for node in ast.walk(tree):
            # ---- Module-level imports ----
            if isinstance(node, ast.Import) and _is_module_level(node, tree):
                for alias in node.names:
                    symbols.append(Symbol(
                        name=alias.name,
                        symbol_type="import",
                        line=node.lineno,
                    ))

            elif isinstance(node, ast.ImportFrom) and _is_module_level(node, tree):
                module = node.module or ""
                for alias in node.names:
                    symbols.append(Symbol(
                        name=f"{module}.{alias.name}" if module else alias.name,
                        symbol_type="import_from",
                        line=node.lineno,
                    ))

        # Walk top-level body for functions/classes (handles nested methods)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sym_type = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
                symbols.append(Symbol(
                    name=node.name,
                    symbol_type=sym_type,
                    line=node.lineno,
                    end_line=getattr(node, "end_lineno", None),
                ))

            elif isinstance(node, ast.ClassDef):
                symbols.append(Symbol(
                    name=node.name,
                    symbol_type="class",
                    line=node.lineno,
                    end_line=getattr(node, "end_lineno", None),
                ))
                # Collect methods
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        mtype = "async_method" if isinstance(item, ast.AsyncFunctionDef) else "method"
                        symbols.append(Symbol(
                            name=item.name,
                            symbol_type=mtype,
                            line=item.lineno,
                            end_line=getattr(item, "end_lineno", None),
                            parent_class=node.name,
                        ))

        # Sort by line number for consistent output
        result.symbols = sorted(symbols, key=lambda s: (s.line, s.name))
        return result


def _is_module_level(node: ast.AST, tree: ast.Module) -> bool:
    """Return True if *node* is a direct child of the module body."""
    return node in tree.body
