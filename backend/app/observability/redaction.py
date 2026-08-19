"""
AgentOS Phase 6 — Centralized Secret Redaction.

Single authoritative utility for sanitizing sensitive data (API keys, passwords,
tokens, authorization headers, private keys) from logs, metrics, events, and API traces.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set, Union

_SECRET_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token|auth|bearer)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{8,})['\"]?"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    re.compile(r"sk-[a-zA-Z0-9]{32,}"),
    re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{20,}"),
)

_SENSITIVE_KEY_NAMES: frozenset[str] = frozenset({
    "password", "passwd", "secret", "api_key", "apikey",
    "access_token", "jwt", "private_key", "authorization", "auth_token", "bearer",
})


def redact_secrets(data: Any) -> Any:
    """Recursively scrub secrets and sensitive patterns from any Python data structure."""
    if isinstance(data, str):
        cleaned = data
        for pattern in _SECRET_PATTERNS:
            cleaned = pattern.sub("[REDACTED_SECRET]", cleaned)
        return cleaned
    elif isinstance(data, dict):
        sanitized: Dict[str, Any] = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(term in k_lower for term in _SENSITIVE_KEY_NAMES):
                sanitized[k] = "[REDACTED_SECRET]"
            else:
                sanitized[k] = redact_secrets(v)
        return sanitized
    elif isinstance(data, list):
        return [redact_secrets(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(redact_secrets(item) for item in data)
    return data
