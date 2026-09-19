"""Stable package surface for bounded native hook events.

The hook-facing implementation remains in ``scripts/capture_event.py`` during
the strangler migration because deployed hook bundles may still copy that
script directly.  Loading it through the shared legacy bridge gives runtime
callers one package boundary without creating a second event implementation.
"""

from __future__ import annotations

from brain_eleven._legacy import load_legacy_module


_legacy = load_legacy_module("capture_event", "capture_event.py")

CAPTURE_EVENT_SCHEMA_VERSION = _legacy.CAPTURE_EVENT_SCHEMA_VERSION
EVENT_SESSION_END = _legacy.EVENT_SESSION_END
EVENT_USER_PROMPT_SUBMIT = _legacy.EVENT_USER_PROMPT_SUBMIT
EVENT_TYPES = _legacy.EVENT_TYPES
PROJECT_RESOLUTION_STATUSES = _legacy.PROJECT_RESOLUTION_STATUSES
MAX_HOOK_EVENT_BYTES = _legacy.MAX_HOOK_EVENT_BYTES
MAX_SESSION_ID_CHARS = _legacy.MAX_SESSION_ID_CHARS
MAX_PROJECT_ROOT_CHARS = _legacy.MAX_PROJECT_ROOT_CHARS
MAX_TRANSCRIPT_PATH_CHARS = _legacy.MAX_TRANSCRIPT_PATH_CHARS
MAX_PROMPT_CHARS = _legacy.MAX_PROMPT_CHARS
CaptureEventError = _legacy.CaptureEventError
CaptureProjectResolutionError = _legacy.CaptureProjectResolutionError
HookEvent = _legacy.HookEvent
parse_hook_event = _legacy.parse_hook_event
parse_hook_event_json = _legacy.parse_hook_event_json
normalize_native_hook_event = _legacy.normalize_native_hook_event
parse_native_hook_event_json = _legacy.parse_native_hook_event_json
main = _legacy.main

__all__ = [
    "CAPTURE_EVENT_SCHEMA_VERSION",
    "EVENT_SESSION_END",
    "EVENT_USER_PROMPT_SUBMIT",
    "EVENT_TYPES",
    "PROJECT_RESOLUTION_STATUSES",
    "MAX_HOOK_EVENT_BYTES",
    "MAX_SESSION_ID_CHARS",
    "MAX_PROJECT_ROOT_CHARS",
    "MAX_TRANSCRIPT_PATH_CHARS",
    "MAX_PROMPT_CHARS",
    "CaptureEventError",
    "CaptureProjectResolutionError",
    "HookEvent",
    "parse_hook_event",
    "parse_hook_event_json",
    "normalize_native_hook_event",
    "parse_native_hook_event_json",
    "main",
]
