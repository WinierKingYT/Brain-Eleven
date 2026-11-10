"""Secret-leakage protection for model-facing context."""

from __future__ import annotations

import re


_SECRET_PATTERNS = (
    re.compile(r"\b(?:sk|rk|pk)_[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(?:api[_ -]?key|secret|password|passwd|token|credential|aws[_ -]?secret[_ -]?access[_ -]?key)\s*[:=]\s*['\"]?[^\s'\"]{12,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def contains_secret(text: str) -> bool:
    return any(pattern.search(text) is not None for pattern in _SECRET_PATTERNS)

