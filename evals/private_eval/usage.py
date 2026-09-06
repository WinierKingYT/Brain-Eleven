"""Non-authoritative, content-free usage telemetry for local evaluation."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from brain_eleven.infrastructure.locking import file_lock


USAGE_SCHEMA_VERSION = 1
USAGE_EVENTS = frozenset(
    {"retrieved", "selected", "rendered", "explicit_reference", "user_helpful", "user_unhelpful", "contradiction"}
)
_EVENT_FIELDS = {
    "retrieved": ("retrieved_count", "last_retrieved_at"),
    "selected": ("selected_count", "last_selected_at"),
    "rendered": ("rendered_count", "last_rendered_at"),
    "explicit_reference": ("explicit_reference_count", "last_explicit_reference_at"),
    "user_helpful": ("user_helpful_count", "last_user_helpful_at"),
    "user_unhelpful": ("user_unhelpful_count", "last_user_unhelpful_at"),
    "contradiction": ("contradiction_count", "last_contradiction_at"),
}


class UsageTelemetryError(ValueError):
    """Usage telemetry is malformed, unsupported, or outside its local boundary."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _identifier(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
        raise UsageTelemetryError("memory_id must be a non-empty single-line identifier")
    return value.strip()


def _atomic_write(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _empty_document() -> dict[str, Any]:
    return {"schema_version": USAGE_SCHEMA_VERSION, "updated_at": _utc_now(), "memory": {}}


def _validate_document(document: Any) -> dict[str, Any]:
    if not isinstance(document, Mapping) or set(document) != {"schema_version", "updated_at", "memory"}:
        raise UsageTelemetryError("usage telemetry has invalid fields")
    if document["schema_version"] != USAGE_SCHEMA_VERSION or not isinstance(document["updated_at"], str):
        raise UsageTelemetryError("usage telemetry schema is unsupported")
    records = document["memory"]
    if not isinstance(records, Mapping):
        raise UsageTelemetryError("usage telemetry memory field must be an object")
    normalized: dict[str, Any] = {}
    allowed_fields = {field for fields in _EVENT_FIELDS.values() for field in fields} | {"retrieved_count", "selected_count", "rendered_count", "explicit_reference_count", "user_helpful_count", "user_unhelpful_count", "contradiction_count"}
    for memory_id, record in records.items():
        key = _identifier(memory_id)
        if not isinstance(record, Mapping) or any(field not in allowed_fields for field in record):
            raise UsageTelemetryError("usage telemetry record has unsupported fields")
        clean: dict[str, Any] = {}
        for field, value in record.items():
            if field.endswith("_count"):
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise UsageTelemetryError("usage telemetry counts must be non-negative integers")
            elif not isinstance(value, str) or not value:
                raise UsageTelemetryError("usage telemetry timestamps must be non-empty strings")
            clean[field] = value
        normalized[key] = clean
    return {"schema_version": USAGE_SCHEMA_VERSION, "updated_at": document["updated_at"], "memory": normalized}


class UsageTelemetryStore:
    """Atomically records observable events without affecting canonical truth."""

    relative_path = Path(".claude") / "memory-usage.json"

    def __init__(self, vault_path: str | Path, *, path: str | Path | None = None):
        self.vault_path = Path(vault_path)
        self.path = Path(path) if path is not None else self.vault_path / self.relative_path

    def load(self) -> Mapping[str, Any]:
        if not self.path.exists():
            return _empty_document()
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UsageTelemetryError("usage telemetry is unreadable") from exc
        return _validate_document(document)

    def record(self, memory_id: str, event: str, *, occurred_at: Optional[str] = None) -> Mapping[str, Any]:
        memory_id = _identifier(memory_id)
        if event not in USAGE_EVENTS:
            raise UsageTelemetryError(f"unsupported usage event: {event}")
        timestamp = occurred_at or _utc_now()
        if not isinstance(timestamp, str) or not timestamp:
            raise UsageTelemetryError("occurred_at must be a non-empty timestamp")
        with file_lock(self.path):
            document = dict(self.load())
            records = dict(document["memory"])
            record = dict(records.get(memory_id, {}))
            count_field, time_field = _EVENT_FIELDS[event]
            record[count_field] = int(record.get(count_field, 0)) + 1
            record[time_field] = timestamp
            records[memory_id] = dict(sorted(record.items()))
            document["memory"] = dict(sorted(records.items()))
            document["updated_at"] = timestamp
            _atomic_write(self.path, document)
            return _validate_document(document)
