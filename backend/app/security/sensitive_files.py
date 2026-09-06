"""
Centralized Sensitive File Detection Policy for AgentOS.

This module is the single source of truth for detecting files that contain,
or may contain, credentials, secrets, or private keys.  No tool should
independently replicate this logic.

Rules
-----
* Any file matched here is denied by SecurityManager for read/search/patch.
* Matched files are never placed in LLM prompts, events, DB records, or API
  responses.
* Patterns are evaluated against both the basename and the full relative path
  (relative to WORKSPACE_ROOT) so that .env files inside sub-directories are
  also caught.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Sequence

# ---------------------------------------------------------------------------
# Sensitive file name / glob patterns
# ---------------------------------------------------------------------------
_SENSITIVE_BASENAME_PATTERNS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "credentials",
    "credentials.*",
    "secrets",
    "secrets.*",
    "id_rsa",
    "id_rsa.*",
    "id_ed25519",
    "id_ed25519.*",
    "id_ecdsa",
    "id_ecdsa.*",
    "id_dsa",
    "id_dsa.*",
    ".netrc",
    ".pgpass",
    "*.jks",        # Java KeyStore
    "*.keystore",
    "*.asc",        # ASCII-armored PGP keys
)

# Directory/path prefixes that mark a path as sensitive.
# Checked against the full relative POSIX path (forward-slash separated).
_SENSITIVE_PATH_PREFIXES: tuple[str, ...] = (
    ".ssh/",
    ".gnupg/",
    ".aws/",
    ".docker/",
    "secrets/",
    "credentials/",
)

# Exact relative paths that are sensitive.
_SENSITIVE_EXACT_PATHS: frozenset[str] = frozenset({
    ".aws/credentials",
    ".aws/config",
    ".docker/config.json",
    "google/credentials.json",
})

# Suffix patterns inside sensitive directories (via prefix check above)
_SENSITIVE_PATH_SUFFIXES: tuple[str, ...] = (
    "/.env",
    "/.env.local",
    "/.env.production",
    "/.env.staging",
    "/.env.development",
)

# ---------------------------------------------------------------------------
# In-content credential pattern detection (applied to first 4 KB of a file)
# ---------------------------------------------------------------------------
_SECRET_CONTENT_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"(?i)(secret|api[_\-]?key|access[_\-]?key|token|password|passwd|auth[_\-]?token)\s*[=:]\s*\S+"),
    re.compile(r"(?i)-----BEGIN (RSA|EC|DSA|OPENSSH|PGP) PRIVATE KEY-----"),
    re.compile(r"(?i)(AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY)\s*="),
    re.compile(r"(?i)GITHUB[_\-]TOKEN\s*[=:]"),
    re.compile(r"(?i)sk-[a-zA-Z0-9]{20,}"),          # OpenAI secret keys
    re.compile(r"(?i)Bearer [a-zA-Z0-9\-_\.]{16,}"),  # Bearer tokens
)

_CONTENT_SCAN_BYTES = 4096  # Only inspect first 4 KB


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_sensitive_path(path: str | Path) -> bool:
    """Return True if the path matches a sensitive file pattern.

    Only the path is inspected — no disk I/O is performed.

    Args:
        path: Absolute or relative file path.

    Returns:
        True when the file should be blocked from reading.
    """
    p = Path(path)
    name = p.name
    # Match against basename patterns
    for pattern in _SENSITIVE_BASENAME_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return True

    # Match against full relative path (use posix separators for consistency)
    rel = p.as_posix()

    # Check exact relative paths
    if rel in _SENSITIVE_EXACT_PATHS:
        return True

    # Check directory prefix patterns  (rel starts with one of the prefixes)
    for prefix in _SENSITIVE_PATH_PREFIXES:
        if rel.startswith(prefix) or f"/{prefix}" in rel:
            return True

    # Check .env in any subdirectory  (basename already covered above;
    # this catches "subdir/.env" which basename == ".env" so already caught)
    # Extra check for .env.* suffix patterns embedded in paths
    for suffix in _SENSITIVE_PATH_SUFFIXES:
        if rel.endswith(suffix) or rel == suffix.lstrip("/"):
            return True

    return False


def contains_secrets(content: str | bytes) -> bool:
    """Return True when the first 4 KB of content contains a credential pattern.

    Args:
        content: Raw file content (str or bytes).

    Returns:
        True when a secret-like pattern is detected.
    """
    if isinstance(content, bytes):
        try:
            snippet = content[:_CONTENT_SCAN_BYTES].decode("utf-8", errors="replace")
        except Exception:
            return False
    else:
        snippet = content[:_CONTENT_SCAN_BYTES]

    for pattern in _SECRET_CONTENT_PATTERNS:
        if pattern.search(snippet):
            return True

    return False


def sensitive_file_reason(path: str | Path) -> str:
    """Return a human-readable explanation of why a path is sensitive."""
    p = Path(path)
    name = p.name
    for pattern in _SENSITIVE_BASENAME_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return f"File '{name}' matches sensitive pattern '{pattern}'"
    rel = p.as_posix()
    for prefix in _SENSITIVE_PATH_PREFIXES:
        if rel.startswith(prefix) or f"/{prefix}" in rel:
            return f"Path matches sensitive directory prefix '{prefix}'"
    if rel in _SENSITIVE_EXACT_PATHS:
        return f"Path matches sensitive exact path '{rel}'"
    for suffix in _SENSITIVE_PATH_SUFFIXES:
        if rel.endswith(suffix) or rel == suffix.lstrip("/"):
            return f"Path matches sensitive suffix '{suffix}'"
    return "File contains credential-like content"
