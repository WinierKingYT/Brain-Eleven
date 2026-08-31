#!/usr/bin/env python3
"""Deterministic safety gate for content entering canonical memory."""

import re
from dataclasses import dataclass
from typing import Dict


POLICY_NAME = "capture_safety_v1"
MAX_MEMORY_LENGTH = 6000
MAX_MULTILINE_COUNT = 80
MAX_RAW_TRANSCRIPT_LIKENESS = 4


@dataclass(frozen=True)
class CaptureSafetyResult:
    """The stable, content-free result returned by the capture safety gate."""

    accepted: bool
    reason: str = ""
    policy: str = POLICY_NAME

    def to_dict(self) -> Dict[str, object]:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "policy": self.policy,
        }


class CaptureSafetyError(ValueError):
    """Raised when unsafe content attempts to enter a canonical write path."""

    def __init__(self, result: CaptureSafetyResult):
        self.result = result
        super().__init__(result.reason)


_PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")
_BEARER_TOKEN = re.compile(
    r"(?:authorization\s*:\s*)?bearer\s+[A-Za-z0-9._~+/=-]{16,}",
    re.IGNORECASE,
)
_API_KEY = re.compile(
    r"(?:"
    r"gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}|"
    r"sk_(?:live|test)_[A-Za-z0-9]{16,}|"
    r"AKIA[0-9A-Z]{16}"
    r")"
)
_NAMED_SECRET = re.compile(
    r"\b(?:api[_-]?key|secret[_-]?key|client[_-]?secret|"
    r"access[_-]?token|refresh[_-]?token|bearer[_-]?token)\s*[:=]\s*(?:"
    r"['\"][^'\"\r\n]{12,}['\"]|[A-Za-z0-9._~+/=-]{16,})",
    re.IGNORECASE,
)
_PASSWORD_ASSIGNMENT = re.compile(
    r"(?:^|[^A-Za-z0-9])(?:password|passwd|pwd)\s*[:=]\s*(?:"
    r"['\"][^'\"\r\n]{4,}['\"]|[^\s;,\r\n]{8,})",
    re.IGNORECASE,
)
_AUTHORIZATION_VALUE = re.compile(
    r"\bauthorization\s*:\s*(?:basic\s+[A-Za-z0-9+/=]{8,}|"
    r"[A-Za-z][A-Za-z0-9_-]*\s+[A-Za-z0-9._~+/=-]{16,})",
    re.IGNORECASE,
)
_SESSION_SECRET = re.compile(
    r"(?:\b(?:session(?:_id)?|sid|access_token|auth(?:_token)?)\s*[:=]\s*"
    r"[^\s;,\r\n]{12,}|\bcookie\s*:\s*[^\r\n]*\b"
    r"(?:session|sid|access_token|auth(?:_token)?)=[^\s;,\r\n]{12,})",
    re.IGNORECASE,
)
_CONNECTION_SECRET = re.compile(
    r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://"
    r"[^\s:@/]+:[^\s@/]{4,}@",
    re.IGNORECASE,
)
_TRANSCRIPT_ROLE = re.compile(r"^\s*(?:user|assistant|system|human|claude|chatgpt)\s*:", re.IGNORECASE)


class CaptureSafetyPolicy:
    """Single deterministic policy for every memory-capture write path."""

    name = POLICY_NAME

    def evaluate(self, content: str) -> CaptureSafetyResult:
        return _evaluate_capture(content)


DEFAULT_CAPTURE_SAFETY_POLICY = CaptureSafetyPolicy()


def evaluate_capture(content: str) -> CaptureSafetyResult:
    """Evaluate content against the default canonical capture policy."""
    return DEFAULT_CAPTURE_SAFETY_POLICY.evaluate(content)


def _evaluate_capture(content: str) -> CaptureSafetyResult:
    """Accept atomic memories and reject structural credential/transcript evidence."""
    value = str(content or "")
    if _PRIVATE_KEY.search(value):
        return CaptureSafetyResult(False, "potential_secret")
    if any(pattern.search(value) for pattern in (
        _BEARER_TOKEN,
        _API_KEY,
        _NAMED_SECRET,
        _PASSWORD_ASSIGNMENT,
        _AUTHORIZATION_VALUE,
        _SESSION_SECRET,
        _CONNECTION_SECRET,
    )):
        return CaptureSafetyResult(False, "potential_secret")
    if len(value) > MAX_MEMORY_LENGTH:
        return CaptureSafetyResult(False, "payload_too_large")

    lines = value.splitlines()
    if len(lines) > MAX_MULTILINE_COUNT:
        return CaptureSafetyResult(False, "too_many_lines")
    role_lines = sum(1 for line in lines if _TRANSCRIPT_ROLE.match(line))
    if role_lines >= MAX_RAW_TRANSCRIPT_LIKENESS and len(value) >= 350:
        return CaptureSafetyResult(False, "transcript_like")
    return CaptureSafetyResult(True)


def require_safe_capture(content: str) -> CaptureSafetyResult:
    """Return an accepted result or raise before any canonical write occurs."""
    result = evaluate_capture(content)
    if not result.accepted:
        raise CaptureSafetyError(result)
    return result
