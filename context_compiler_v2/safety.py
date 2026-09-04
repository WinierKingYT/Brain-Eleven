"""Prompt-boundary and secret-leakage protections for model-facing context."""

from __future__ import annotations

import re


_SECRET_PATTERNS = (
    re.compile(r"\b(?:sk|rk|pk)_[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(?:api[_ -]?key|secret|password|token)\s*[:=]\s*['\"]?[^\s'\"]{12,}"),
)
_RESERVED = (
    "[BRAIN-ELEVEN TASK CONTEXT V2]",
    "[END BRAIN-ELEVEN CONTEXT]",
)


def contains_secret(text: str) -> bool:
    return any(pattern.search(text) is not None for pattern in _SECRET_PATTERNS)


def escape_untrusted_text(text: str) -> str:
    """Keep source meaning visible while neutralising our reserved delimiters."""
    escaped = text
    for marker in _RESERVED:
        escaped = escaped.replace(marker, marker.replace("[", "[ESCAPED ", 1))
    return escaped.replace("\x00", "�")
