#!/usr/bin/env python3
"""Bounded, content-safe contracts for future Brain-Eleven hook capture.

PRE-01 deliberately stops at parsing, identity and project resolution.  It
does not enqueue work, read transcripts, retain prompt content, or write any
canonical MemoryStore/StateStore data.  PRE-02 owns durable queue delivery and
the hook integration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from brain_eleven.projects.registry import ProjectRegistry, ProjectRegistryError


CAPTURE_EVENT_SCHEMA_VERSION = 1
EVENT_SESSION_END = "SESSION_END"
EVENT_USER_PROMPT_SUBMIT = "USER_PROMPT_SUBMIT"
EVENT_TYPES = frozenset({EVENT_SESSION_END, EVENT_USER_PROMPT_SUBMIT})
PROJECT_RESOLUTION_STATUSES = frozenset({"resolved", "archived", "unresolved"})
MAX_HOOK_EVENT_BYTES = 16 * 1024
MAX_SESSION_ID_CHARS = 256
MAX_PROJECT_ROOT_CHARS = 4 * 1024
MAX_TRANSCRIPT_PATH_CHARS = 8 * 1024
MAX_PROMPT_CHARS = 12 * 1024
_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class CaptureEventError(ValueError):
    """Raised for malformed or unsafe hook-event input."""

    code = "CAPTURE_EVENT_INVALID"


class CaptureProjectResolutionError(CaptureEventError):
    """Raised when the registry cannot safely resolve an event project."""

    code = "PROJECT_REGISTRY_UNAVAILABLE"


@dataclass(frozen=True)
class HookEvent:
    """A content-safe, deterministic hook event with no canonical side effects."""

    event_id: str
    idempotency_key: str
    event_type: str
    session_id: str
    project_root: str
    project_id: Optional[str]
    project_status: str
    event_at: str
    transcript_path: Optional[str] = None
    prompt_sha256: Optional[str] = None
    prompt_length: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Return the queue-ready event envelope without raw prompt content."""
        payload: dict[str, Any] = {
            "schema_version": CAPTURE_EVENT_SCHEMA_VERSION,
            "event_id": self.event_id,
            "idempotency_key": self.idempotency_key,
            "event_type": self.event_type,
            "session_id": self.session_id,
            "project_root": self.project_root,
            "project": {
                "project_id": self.project_id,
                "status": self.project_status,
                "source": "project_registry",
            },
            "event_at": self.event_at,
        }
        if self.transcript_path is not None:
            payload["transcript_path"] = self.transcript_path
        if self.prompt_sha256 is not None:
            payload["prompt"] = {
                "sha256": self.prompt_sha256,
                "length": self.prompt_length,
            }
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"


def _error(message: str) -> CaptureEventError:
    return CaptureEventError(message)


def _require_string(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(f"{field} must be a non-empty string")
    if len(value) > maximum:
        raise _error(f"{field} exceeds {maximum} characters")
    if "\x00" in value:
        raise _error(f"{field} must not contain a NUL character")
    return value


def _event_at(value: Any) -> str:
    raw = _require_string(value, "event_at", 64)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _error("event_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise _error("event_at must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _payload_size(payload: Mapping[str, Any]) -> None:
    try:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise _error("hook event must be JSON-serializable") from exc
    if len(encoded) > MAX_HOOK_EVENT_BYTES:
        raise _error(f"hook event exceeds {MAX_HOOK_EVENT_BYTES} bytes")


def _validated_session_id(value: Any) -> str:
    session_id = _require_string(value, "session_id", MAX_SESSION_ID_CHARS)
    if _SESSION_ID_PATTERN.fullmatch(session_id) is None:
        raise _error("session_id contains unsupported characters")
    return session_id


def _resolve_project(vault_path: str | Path, project_root: str) -> tuple[Optional[str], str]:
    """Resolve an existing project read-only; never create an identity here."""
    try:
        record = ProjectRegistry(vault_path).resolve(project_root)
    except ProjectRegistryError as exc:
        raise CaptureProjectResolutionError("Project registry is unavailable for capture") from exc
    if record is None:
        return None, "unresolved"
    return record["project_id"], "archived" if record["status"] == "archived" else "resolved"


def _prompt_metadata(payload: Mapping[str, Any]) -> tuple[str, int]:
    has_raw = "prompt" in payload
    has_metadata = "prompt_sha256" in payload or "prompt_length" in payload
    if has_raw and has_metadata:
        raise _error("prompt input must use raw prompt or prompt metadata, not both")
    if not has_raw and not has_metadata:
        raise _error("USER_PROMPT_SUBMIT requires prompt or prompt metadata")
    if has_raw:
        prompt = _require_string(payload.get("prompt"), "prompt", MAX_PROMPT_CHARS)
        digest = "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        return digest, len(prompt)

    digest = _require_string(payload.get("prompt_sha256"), "prompt_sha256", 71)
    if _SHA256_PATTERN.fullmatch(digest) is None:
        raise _error("prompt_sha256 must use the sha256:<hex> format")
    length = payload.get("prompt_length")
    if not isinstance(length, int) or isinstance(length, bool) or not 0 <= length <= MAX_PROMPT_CHARS:
        raise _error("prompt_length must be a bounded non-negative integer")
    return digest, length


def _event_identity(event_type: str, session_id: str, event_at: str, prompt_sha256: Optional[str]) -> tuple[str, str]:
    if event_type == EVENT_SESSION_END:
        key = f"session:{session_id}:end"
    else:
        if prompt_sha256 is None:
            raise _error("USER_PROMPT_SUBMIT requires prompt metadata")
        key = f"prompt:{session_id}:{event_at}:{prompt_sha256}"
    event_id = "evt_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:26]
    return event_id, key


def parse_hook_event(payload: Mapping[str, Any], *, vault_path: str | Path) -> HookEvent:
    """Validate one untrusted hook payload without writing any local state."""
    if not isinstance(payload, Mapping):
        raise _error("hook event must be a JSON object")
    _payload_size(payload)

    event_type = payload.get("event_type")
    if event_type not in EVENT_TYPES:
        raise _error("event_type is unsupported")

    base_fields = {"event_type", "session_id", "project_root", "event_at"}
    allowed_fields = set(base_fields)
    if event_type == EVENT_SESSION_END:
        allowed_fields.add("transcript_path")
    else:
        allowed_fields.update({"prompt", "prompt_sha256", "prompt_length"})
    unexpected = set(payload) - allowed_fields
    if unexpected:
        raise _error("hook event contains unsupported fields")

    missing = base_fields - set(payload)
    if missing:
        raise _error("hook event is missing required fields")
    session_id = _validated_session_id(payload["session_id"])
    project_root = _require_string(payload["project_root"], "project_root", MAX_PROJECT_ROOT_CHARS)
    event_at = _event_at(payload["event_at"])
    project_id, project_status = _resolve_project(vault_path, project_root)
    if project_status not in PROJECT_RESOLUTION_STATUSES:
        raise _error("project resolution status is unsupported")

    transcript_path: Optional[str] = None
    prompt_sha256: Optional[str] = None
    prompt_length: Optional[int] = None
    if event_type == EVENT_SESSION_END:
        if "transcript_path" not in payload:
            raise _error("SESSION_END requires transcript_path")
        transcript_path = _require_string(
            payload["transcript_path"], "transcript_path", MAX_TRANSCRIPT_PATH_CHARS
        )
    else:
        prompt_sha256, prompt_length = _prompt_metadata(payload)

    event_id, idempotency_key = _event_identity(event_type, session_id, event_at, prompt_sha256)
    return HookEvent(
        event_id=event_id,
        idempotency_key=idempotency_key,
        event_type=event_type,
        session_id=session_id,
        project_root=project_root,
        project_id=project_id,
        project_status=project_status,
        event_at=event_at,
        transcript_path=transcript_path,
        prompt_sha256=prompt_sha256,
        prompt_length=prompt_length,
    )


def parse_hook_event_json(payload: str | bytes, *, vault_path: str | Path) -> HookEvent:
    """Parse bounded hook stdin JSON and return a content-safe event contract."""
    if isinstance(payload, str):
        raw = payload.encode("utf-8")
    elif isinstance(payload, bytes):
        raw = payload
    else:
        raise _error("hook stdin must be text or bytes")
    if len(raw) > MAX_HOOK_EVENT_BYTES:
        raise _error(f"hook event exceeds {MAX_HOOK_EVENT_BYTES} bytes")
    try:
        decoded = raw.decode("utf-8")
        document = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("hook stdin must be UTF-8 JSON") from exc
    return parse_hook_event(document, vault_path=vault_path)


def normalize_native_hook_event(
    payload: Mapping[str, Any],
    *,
    event_type: str,
    vault_path: str | Path,
    default_project_root: str | Path,
    received_at: Optional[str] = None,
) -> HookEvent:
    """Normalize one Claude hook payload into the strict capture contract.

    ``event_type`` and the fallback project root are trusted command-line
    inputs supplied by the installed hook.  The stdin payload is untrusted:
    it may supply only the session locator, a project cwd, a transcript
    locator, prompt text and an event timestamp.  In particular, stdin can
    never choose the event type, project identity, scope, or retention policy.
    """
    if event_type not in EVENT_TYPES:
        raise _error("trusted hook event_type is unsupported")
    if not isinstance(payload, Mapping):
        raise _error("hook event must be a JSON object")
    _payload_size(payload)

    # Claude hook payloads can add informational fields over time.  Deliberately
    # ignore them instead of treating them as authority-bearing input.
    project_root = payload.get("cwd", default_project_root)
    event_at = payload.get("event_at", payload.get("timestamp", received_at))
    if event_at is None:
        event_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    normalized: dict[str, Any] = {
        "event_type": event_type,
        "session_id": payload.get("session_id"),
        "project_root": project_root,
        "event_at": event_at,
    }
    if event_type == EVENT_SESSION_END:
        normalized["transcript_path"] = payload.get("transcript_path")
    else:
        # Raw prompt text is accepted only long enough to derive its digest in
        # ``parse_hook_event``.  It is never returned by HookEvent or persisted
        # by the PRE-02 queue.
        if "prompt" in payload:
            normalized["prompt"] = payload.get("prompt")
        else:
            normalized["prompt_sha256"] = payload.get("prompt_sha256")
            normalized["prompt_length"] = payload.get("prompt_length")
    return parse_hook_event(normalized, vault_path=vault_path)


def parse_native_hook_event_json(
    payload: str | bytes,
    *,
    event_type: str,
    vault_path: str | Path,
    default_project_root: str | Path,
    received_at: Optional[str] = None,
) -> HookEvent:
    """Parse bounded native hook stdin without granting it policy authority."""
    if isinstance(payload, str):
        raw = payload.encode("utf-8")
    elif isinstance(payload, bytes):
        raw = payload
    else:
        raise _error("hook stdin must be text or bytes")
    if len(raw) > MAX_HOOK_EVENT_BYTES:
        raise _error(f"hook event exceeds {MAX_HOOK_EVENT_BYTES} bytes")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("hook stdin must be UTF-8 JSON") from exc
    return normalize_native_hook_event(
        document,
        event_type=event_type,
        vault_path=vault_path,
        default_project_root=default_project_root,
        received_at=received_at,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Expose a future-hook-compatible parser without changing hooks in PRE-01."""
    parser = argparse.ArgumentParser(description="Validate a Brain-Eleven hook event without side effects")
    parser.add_argument("--vault", default=".", help="Vault containing the project registry")
    arguments = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(MAX_HOOK_EVENT_BYTES + 1)
        event = parse_hook_event_json(raw, vault_path=arguments.vault)
    except CaptureEventError as exc:
        print(json.dumps({"error": {"code": exc.code, "message": str(exc)}}))
        return 2
    print(event.to_json(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
