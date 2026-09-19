"""Stable package surface for the deterministic capture safety policy."""

from __future__ import annotations

from brain_eleven._legacy import load_legacy_module


_legacy = load_legacy_module("capture_safety", "capture_safety.py")

POLICY_NAME = _legacy.POLICY_NAME
MAX_MEMORY_LENGTH = _legacy.MAX_MEMORY_LENGTH
MAX_MULTILINE_COUNT = _legacy.MAX_MULTILINE_COUNT
MAX_RAW_TRANSCRIPT_LIKENESS = _legacy.MAX_RAW_TRANSCRIPT_LIKENESS
CaptureSafetyResult = _legacy.CaptureSafetyResult
CaptureSafetyError = _legacy.CaptureSafetyError
CaptureSafetyPolicy = _legacy.CaptureSafetyPolicy
DEFAULT_CAPTURE_SAFETY_POLICY = _legacy.DEFAULT_CAPTURE_SAFETY_POLICY
evaluate_capture = _legacy.evaluate_capture
require_safe_capture = _legacy.require_safe_capture

__all__ = [
    "POLICY_NAME",
    "MAX_MEMORY_LENGTH",
    "MAX_MULTILINE_COUNT",
    "MAX_RAW_TRANSCRIPT_LIKENESS",
    "CaptureSafetyResult",
    "CaptureSafetyError",
    "CaptureSafetyPolicy",
    "DEFAULT_CAPTURE_SAFETY_POLICY",
    "evaluate_capture",
    "require_safe_capture",
]
