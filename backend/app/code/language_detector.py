"""
Language Detector for AgentOS Phase 3.

Analyses a list of FileInfo objects (produced by RepositoryScanner) and
computes the language distribution of the repository.  Pure in-memory logic;
no disk I/O beyond what the scanner already performed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from backend.app.code.scanner import FileInfo


# Map file extension → canonical language name
_EXT_TO_LANGUAGE: dict[str, str] = {
    # Python
    ".py":    "Python",
    ".pyx":   "Python",
    ".pyi":   "Python",
    # JavaScript / TypeScript
    ".js":    "JavaScript",
    ".jsx":   "JavaScript",
    ".mjs":   "JavaScript",
    ".cjs":   "JavaScript",
    ".ts":    "TypeScript",
    ".tsx":   "TypeScript",
    ".mts":   "TypeScript",
    # Web
    ".html":  "HTML",
    ".htm":   "HTML",
    ".css":   "CSS",
    ".scss":  "SCSS",
    ".sass":  "SCSS",
    ".less":  "Less",
    # Data / Config
    ".json":  "JSON",
    ".yaml":  "YAML",
    ".yml":   "YAML",
    ".toml":  "TOML",
    ".ini":   "INI",
    ".cfg":   "INI",
    ".env":   "ENV",   # should be blocked by sensitive-file gate before this
    # Shell
    ".sh":    "Shell",
    ".bash":  "Shell",
    ".zsh":   "Shell",
    ".fish":  "Shell",
    ".bat":   "Batch",
    ".cmd":   "Batch",
    ".ps1":   "PowerShell",
    # JVM
    ".java":  "Java",
    ".kt":    "Kotlin",
    ".kts":   "Kotlin",
    ".scala": "Scala",
    ".groovy":"Groovy",
    # Systems
    ".c":     "C",
    ".h":     "C",
    ".cpp":   "C++",
    ".cc":    "C++",
    ".cxx":   "C++",
    ".hpp":   "C++",
    ".rs":    "Rust",
    ".go":    "Go",
    ".cs":    "C#",
    # Docs
    ".md":    "Markdown",
    ".rst":   "reStructuredText",
    ".txt":   "Text",
    # SQL
    ".sql":   "SQL",
    # Other
    ".r":     "R",
    ".rb":    "Ruby",
    ".php":   "PHP",
    ".lua":   "Lua",
    ".swift": "Swift",
    ".dart":  "Dart",
}


@dataclass
class LanguageStats:
    language: str
    file_count: int
    byte_count: int
    percentage: float    # share of total source bytes (0–100)


@dataclass
class LanguageDetectionResult:
    languages: list[LanguageStats]           # ordered by byte_count descending
    primary_language: str                    # most bytes
    total_source_files: int
    total_source_bytes: int
    unknown_extensions: list[str]            # extensions not in the map


class LanguageDetector:
    """Compute language breakdown from a list of scanned FileInfo objects."""

    def detect(self, files: Sequence[FileInfo]) -> LanguageDetectionResult:
        byte_by_lang: dict[str, int] = {}
        count_by_lang: dict[str, int] = {}
        unknown_exts: set[str] = set()
        total_bytes = 0

        for fi in files:
            ext = fi.extension
            lang = _EXT_TO_LANGUAGE.get(ext)
            if lang is None:
                if ext:
                    unknown_exts.add(ext)
                continue
            byte_by_lang[lang] = byte_by_lang.get(lang, 0) + fi.size_bytes
            count_by_lang[lang] = count_by_lang.get(lang, 0) + 1
            total_bytes += fi.size_bytes

        stats: list[LanguageStats] = []
        for lang, bcount in sorted(byte_by_lang.items(), key=lambda x: -x[1]):
            pct = (bcount / total_bytes * 100) if total_bytes > 0 else 0.0
            stats.append(LanguageStats(
                language=lang,
                file_count=count_by_lang[lang],
                byte_count=bcount,
                percentage=round(pct, 1),
            ))

        primary = stats[0].language if stats else "Unknown"
        return LanguageDetectionResult(
            languages=stats,
            primary_language=primary,
            total_source_files=sum(count_by_lang.values()),
            total_source_bytes=total_bytes,
            unknown_extensions=sorted(unknown_exts),
        )
