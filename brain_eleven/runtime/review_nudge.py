"""Content-free per-session counters for the IG04-B3 review nudge."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timedelta, timezone

from brain_eleven.projects.registry import ProjectRegistry

from .storage import RuntimeConfig, guard_runtime_path, read_json, runtime_file_lock, write_json


MIN_PROMPTS_FOR_NUDGE = 5
COUNTER_TTL = timedelta(days=7)
MARKER_TTL = timedelta(days=7)
MAX_NUDGES_PER_SESSION_START = 1

_SCHEMA_VERSION = 1
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_PROJECT_ID_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,256}$")
_LEDGER_NAME = "review-nudge.json"
_LOCK_NAME = "review-nudge-state"
_COUNTER_FIELDS = {
    "schema_version", "session_id_hash", "project_id", "prompt_count", "last_seen_at", "expires_at",
}
_MARKER_FIELDS = {
    "schema_version", "session_id_hash", "project_id", "prompt_count", "ended_at", "expires_at",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _session_id_hash(client, raw_session_id):
    if (client not in {"claude", "codex"} or not isinstance(raw_session_id, str)
            or _SESSION_ID_RE.fullmatch(raw_session_id) is None):
        return None
    material = b"brain-eleven:ig04b3:session:v1\0" + client.encode("ascii") + b"\0" + raw_session_id.encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _valid_row(value, fields):
    if (not isinstance(value, dict) or set(value) != fields
            or value.get("schema_version") != _SCHEMA_VERSION):
        return False
    if not isinstance(value.get("session_id_hash"), str) or _SHA256_RE.fullmatch(value["session_id_hash"]) is None:
        return False
    if not isinstance(value.get("project_id"), str) or _PROJECT_ID_RE.fullmatch(value["project_id"]) is None:
        return False
    count = value.get("prompt_count")
    minimum_count = 1 if fields == _COUNTER_FIELDS else MIN_PROMPTS_FOR_NUDGE
    if (isinstance(count, bool) or not isinstance(count, int)
            or count < minimum_count or count > 2**31 - 1):
        return False
    if fields == _COUNTER_FIELDS:
        seen = _timestamp(value.get("last_seen_at"))
        expiry = _timestamp(value.get("expires_at"))
        return (seen is not None and expiry is not None
                and seen < expiry <= seen + COUNTER_TTL)
    ended = _timestamp(value.get("ended_at"))
    expiry = _timestamp(value.get("expires_at"))
    return (ended is not None and expiry is not None
            and ended < expiry <= ended + MARKER_TTL)


def _empty_ledger():
    return {"schema_version": _SCHEMA_VERSION, "counters": [], "markers": []}


def _valid_ledger(value):
    if (not isinstance(value, dict) or set(value) != {"schema_version", "counters", "markers"}
            or value.get("schema_version") != _SCHEMA_VERSION
            or not isinstance(value.get("counters"), list)
            or not isinstance(value.get("markers"), list)):
        return False
    seen = set()
    for row in value["counters"]:
        if not _valid_row(row, _COUNTER_FIELDS):
            return False
        key = (row["session_id_hash"], row["project_id"])
        if key in seen:
            return False
        seen.add(key)
    seen.clear()
    for row in value["markers"]:
        if not _valid_row(row, _MARKER_FIELDS):
            return False
        key = (row["session_id_hash"], row["project_id"])
        if key in seen:
            return False
        seen.add(key)
    return True


def _eligible_project(config, registry, project_id):
    if project_id not in config.get("project_ids", []):
        return False
    project = registry.get(project_id)
    return bool(project and project.get("status") == "active" and project.get("proactive_capture") is True)


def _read_ledger(runtime_root, path):
    if not os.path.lexists(path):
        return _empty_ledger()
    guard_runtime_path(runtime_root, path, create=False)
    value = read_json(path)
    if not _valid_ledger(value):
        raise ValueError("Review nudge state is invalid")
    return value


def record_prompt(vault, client, raw_session_id, project_id) -> bool:
    """Best-effort increment for a valid, opted-in prompt event.

    The prompt payload is intentionally not accepted as an argument.
    """
    session_hash = _session_id_hash(client, raw_session_id)
    if session_hash is None or not isinstance(project_id, str) or _PROJECT_ID_RE.fullmatch(project_id) is None:
        return False
    try:
        runtime = RuntimeConfig(vault)
        config = runtime.load()
        if config["mode"] == "OFF":
            return False
        registry = ProjectRegistry(vault)
        if not _eligible_project(config, registry, project_id):
            return False

        state_path = runtime.root / _LEDGER_NAME
        with runtime_file_lock(runtime.root / _LOCK_NAME, timeout=0.5):
            current_config = runtime.load()
            if (current_config["mode"] == "OFF"
                    or project_id not in current_config.get("project_ids", [])):
                return False
            ledger = _read_ledger(runtime.root, state_path)
            current = _utc_now()
            counters = [
                row for row in ledger["counters"]
                if _timestamp(row["expires_at"]) > current
            ]
            row = next((item for item in counters
                        if item["session_id_hash"] == session_hash and item["project_id"] == project_id), None)
            if row is None:
                row = {
                    "schema_version": _SCHEMA_VERSION,
                    "session_id_hash": session_hash,
                    "project_id": project_id,
                    "prompt_count": 1,
                    "last_seen_at": _format_timestamp(current),
                    "expires_at": _format_timestamp(current + COUNTER_TTL),
                }
                counters.append(row)
            else:
                row["schema_version"] = _SCHEMA_VERSION
                row["prompt_count"] = min(row["prompt_count"] + 1, 2**31 - 1)
                row["last_seen_at"] = _format_timestamp(current)
                row["expires_at"] = _format_timestamp(current + COUNTER_TTL)
            ledger["counters"] = counters
            write_json(state_path, ledger)
        return True
    except Exception:
        # A convenience counter failure must never fail the prompt hook.
        return False


def finalize_session(vault, client, raw_session_id) -> bool:
    """Finalize all eligible project counters at the per-session SessionEnd."""
    session_hash = _session_id_hash(client, raw_session_id)
    if session_hash is None:
        return False
    try:
        runtime = RuntimeConfig(vault)
        if runtime.load()["mode"] == "OFF":
            return False
        state_path = runtime.root / _LEDGER_NAME
        with runtime_file_lock(runtime.root / _LOCK_NAME, timeout=0.5):
            config = runtime.load()
            if config["mode"] == "OFF":
                return False
            registry = ProjectRegistry(vault)
            ledger = _read_ledger(runtime.root, state_path)
            current = _utc_now()
            unexpired_counters = [
                row for row in ledger["counters"]
                if _timestamp(row["expires_at"]) > current
            ]
            markers = [
                row for row in ledger["markers"]
                if _timestamp(row["expires_at"]) > current
            ]
            changed = (len(unexpired_counters) != len(ledger["counters"])
                       or len(markers) != len(ledger["markers"]))
            session_counters = [
                row for row in unexpired_counters
                if row["session_id_hash"] == session_hash
            ]
            remaining = [
                row for row in unexpired_counters
                if row["session_id_hash"] != session_hash
            ]
            if len(remaining) != len(ledger["counters"]):
                changed = True
            for counter in session_counters:
                project_id = counter["project_id"]
                if (counter["prompt_count"] < MIN_PROMPTS_FOR_NUDGE
                        or not _eligible_project(config, registry, project_id)):
                    continue
                existing = next((marker for marker in markers
                                 if marker["session_id_hash"] == session_hash
                                 and marker["project_id"] == project_id), None)
                if existing is not None:
                    continue
                markers.append({
                    "schema_version": _SCHEMA_VERSION,
                    "session_id_hash": session_hash,
                    "project_id": project_id,
                    "prompt_count": counter["prompt_count"],
                    "ended_at": _format_timestamp(current),
                    "expires_at": _format_timestamp(current + MARKER_TTL),
                })
                changed = True
            if changed:
                ledger["counters"] = remaining
                ledger["markers"] = markers
                write_json(state_path, ledger)
        return True
    except Exception:
        # SessionEnd cleanup is independent best-effort work; it cannot affect
        # the B1 transcript/worker path or prevent the host from closing.
        return False


def project_markers(vault, project_id):
    """Return unexpired marker session hashes, or None when state is unknown."""
    if not isinstance(project_id, str) or _PROJECT_ID_RE.fullmatch(project_id) is None:
        return None
    try:
        runtime = RuntimeConfig(vault)
        config = runtime.load()
        if config["mode"] == "OFF":
            return None
        registry = ProjectRegistry(vault)
        if not _eligible_project(config, registry, project_id):
            return None
        state_path = runtime.root / _LEDGER_NAME
        with runtime_file_lock(runtime.root / _LOCK_NAME, timeout=0.5):
            current_config = runtime.load()
            if (current_config["mode"] == "OFF"
                    or not _eligible_project(current_config, registry, project_id)):
                return None
            ledger = _read_ledger(runtime.root, state_path)
            current = _utc_now()
            markers = [
                row for row in ledger["markers"]
                if _timestamp(row["expires_at"]) > current
            ]
            expired = len(markers) != len(ledger["markers"])
            if expired:
                ledger["markers"] = markers
                write_json(state_path, ledger)
            return [row["session_id_hash"] for row in markers
                    if row["project_id"] == project_id]
    except Exception:
        return None


def consume_project_markers(vault, project_id, expected_session_hashes) -> bool:
    """Atomically consume the observed project markers; false means do not emit."""
    if (not isinstance(project_id, str) or _PROJECT_ID_RE.fullmatch(project_id) is None
            or not isinstance(expected_session_hashes, (list, tuple, set))):
        return False
    expected = set(expected_session_hashes)
    if not expected or any(not isinstance(item, str) or _SHA256_RE.fullmatch(item) is None for item in expected):
        return False
    try:
        runtime = RuntimeConfig(vault)
        config = runtime.load()
        if config["mode"] == "OFF":
            return False
        registry = ProjectRegistry(vault)
        if not _eligible_project(config, registry, project_id):
            return False
        state_path = runtime.root / _LEDGER_NAME
        with runtime_file_lock(runtime.root / _LOCK_NAME, timeout=0.5):
            current_config = runtime.load()
            if (current_config["mode"] == "OFF"
                    or not _eligible_project(current_config, registry, project_id)):
                return False
            ledger = _read_ledger(runtime.root, state_path)
            current = _utc_now()
            unexpired = [
                row for row in ledger["markers"]
                if _timestamp(row["expires_at"]) > current
            ]
            current_project_hashes = {
                row["session_id_hash"] for row in unexpired
                if row["project_id"] == project_id
            }
            if not expected.issubset(current_project_hashes):
                return False
            remaining = [row for row in unexpired if row["project_id"] != project_id]
            ledger["markers"] = remaining
            write_json(state_path, ledger)
        return True
    except Exception:
        return False
