#!/usr/bin/env python3
"""Strict schema primitives for Phase 16 canonical project state.

Persistence and typed state mutations are deliberately added in later modules
of this file.  The schema is independent of MemoryStore and never writes to it.
"""

from __future__ import annotations

import re
import secrets
import json
import os
import shutil
import sys
import tempfile
import time
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from brain_eleven.infrastructure.locking import MemoryStoreLockTimeout, file_lock
    from brain_eleven.memory import MemoryStore, MemoryStoreError
    from brain_eleven.projects.registry import ProjectRegistry, ProjectRegistryError
except ModuleNotFoundError as exc:  # pragma: no cover - copied-hook fallback
    if exc.name != "brain_eleven":
        raise
    from memory_store import MemoryStore, MemoryStoreError
    from memory_store_lock import MemoryStoreLockTimeout, file_lock
    from project_registry import ProjectRegistry, ProjectRegistryError


STATE_SCHEMA_VERSION = 1
STATE_FILENAME = "project-state.json"
MAX_AUDIT_EVENTS = 1000
STATE_SOURCE_TYPES = frozenset({"user", "system", "tool", "ai_proposed"})
CANONICAL_SOURCE_TYPES = frozenset({"user", "system", "tool"})
MILESTONE_STATUSES = frozenset({"PLANNED", "ACTIVE", "BLOCKED", "COMPLETED", "CANCELLED"})
WORK_ITEM_STATUSES = frozenset({"TODO", "ACTIVE", "BLOCKED", "DONE", "DROPPED"})
REQUIREMENT_STATUSES = frozenset({"ACTIVE", "RESOLVED", "CANCELLED"})
BLOCKER_STATUSES = frozenset({"ACTIVE", "RESOLVED"})
SEVERITIES = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ID_PREFIXES = {
    "milestone": "mil_",
    "objective": "obj_",
    "requirement": "req_",
    "work_item": "wrk_",
    "blocker": "blk_",
    "constraint": "con_",
    "risk": "rsk_",
    "event": "evt_",
}
_SENSITIVE_PATTERNS = (
    re.compile(r"\b(?:api[_ -]?key|password|secret|token)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\b(?:sk|ghp|xox[baprs])_[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


class StateError(RuntimeError):
    """Base failure for canonical StateStore operations."""


class StateSchemaError(StateError):
    """Raised when state is malformed, unsafe, or unsupported."""


class StateProvenanceError(StateSchemaError):
    """Raised when an untrusted source tries to become canonical state."""


class StateStoreCorrupt(StateError):
    """Raised when the canonical state document cannot be read or validated."""


class StateStoreConflict(StateError):
    """Raised when a state writer presents a stale project revision."""

    def __init__(self, project_id: str, expected_revision: int, actual_revision: int):
        self.project_id = project_id
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision
        super().__init__(
            f"STATE_CONFLICT for {project_id}: expected {expected_revision}, actual {actual_revision}"
        )


class StateStoreLockTimeout(StateError):
    """Raised when a writer cannot acquire the project-state lock."""


class StateStorePersistenceError(StateError):
    """Raised when the previous canonical state could not be safely replaced."""


class StateProjectUnknown(StateError):
    """Raised when a state mutation targets no registered project."""


class StateProjectArchived(StateError):
    """Raised when a state mutation targets a read-only archived project."""


class StateTransitionError(StateError):
    """Raised when a typed lifecycle transition is not allowed."""


class StateReferenceError(StateError):
    """Raised when state attempts to reference invalid durable knowledge."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def state_store_path(vault_path: str | Path) -> Path:
    candidate = Path(vault_path).expanduser()
    return candidate if candidate.name == STATE_FILENAME else candidate / ".claude" / STATE_FILENAME


def _encode_crockford(value: int, length: int) -> str:
    result = []
    for _ in range(length):
        result.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(result))


def new_state_id(kind: str) -> str:
    """Mint a semantic, ULID-shaped ID without persisting any state."""
    if kind not in _ID_PREFIXES:
        raise ValueError(f"Unsupported state ID kind: {kind}")
    timestamp = _encode_crockford(int(time.time() * 1000), 10)
    random_part = _encode_crockford(int.from_bytes(secrets.token_bytes(10), "big"), 16)
    return _ID_PREFIXES[kind] + timestamp + random_part


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StateSchemaError(f"{field} must be an object")
    return value


def _exact_keys(
    value: Mapping[str, Any],
    field: str,
    required: set[str],
    optional: set[str] | frozenset[str] = frozenset(),
) -> None:
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    if missing:
        raise StateSchemaError(f"{field} missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        raise StateSchemaError(f"{field} has unknown field(s): {', '.join(sorted(unknown))}")


def _string(value: Any, field: str, *, prefix: Optional[str] = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StateSchemaError(f"{field} must be a non-empty string")
    result = value.strip()
    if prefix and not result.startswith(prefix):
        raise StateSchemaError(f"{field} must use {prefix} namespace")
    if any(pattern.search(result) for pattern in _SENSITIVE_PATTERNS):
        raise StateSchemaError(f"{field} must not contain credentials or secrets")
    return result


def _integer(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise StateSchemaError(f"{field} must be a non-negative integer")
    return value


def _string_list(value: Any, field: str, *, prefix: Optional[str] = None) -> list[str]:
    if not isinstance(value, list):
        raise StateSchemaError(f"{field} must be an array")
    normalized = [_string(item, f"{field}[{index}]", prefix=prefix) for index, item in enumerate(value)]
    if len(normalized) != len(set(normalized)):
        raise StateSchemaError(f"{field} must not contain duplicate values")
    return normalized


def _provenance(value: Any, field: str, *, canonical: bool) -> dict[str, Any]:
    document = _mapping(value, field)
    _exact_keys(document, field, {"type"}, {"reference"})
    source_type = _string(document["type"], f"{field}.type")
    if source_type not in STATE_SOURCE_TYPES:
        raise StateProvenanceError(f"{field}.type is unsupported: {source_type}")
    if canonical and source_type not in CANONICAL_SOURCE_TYPES:
        raise StateProvenanceError(f"{field}.type cannot create canonical state")
    reference = document.get("reference")
    if reference is not None:
        reference = _string(reference, f"{field}.reference")
    return {"type": source_type, "reference": reference}


def _timestamp(value: Any, field: str) -> str:
    result = _string(value, field)
    try:
        datetime.fromisoformat(result.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StateSchemaError(f"{field} must be an ISO-8601 timestamp") from exc
    return result


def _record_base(
    value: Any,
    field: str,
    *,
    prefix: str,
    statuses: frozenset[str],
    text_field: str = "text",
    extra_required: Optional[set[str]] = None,
    extra_optional: Optional[set[str]] = None,
) -> dict[str, Any]:
    document = _mapping(value, field)
    required = {"id", text_field, "status", "source", "created_at", "updated_at"} | (extra_required or set())
    _exact_keys(document, field, required, extra_optional or set())
    status = _string(document["status"], f"{field}.status")
    if status not in statuses:
        raise StateSchemaError(f"{field}.status is unsupported: {status}")
    result = {
        "id": _string(document["id"], f"{field}.id", prefix=prefix),
        text_field: _string(document[text_field], f"{field}.{text_field}"),
        "status": status,
        "source": _provenance(document["source"], f"{field}.source", canonical=True),
        "created_at": _timestamp(document["created_at"], f"{field}.created_at"),
        "updated_at": _timestamp(document["updated_at"], f"{field}.updated_at"),
    }
    return result


def _milestone(value: Any, field: str) -> dict[str, Any]:
    result = _record_base(
        value,
        field,
        prefix="mil_",
        statuses=MILESTONE_STATUSES,
        text_field="title",
        extra_required={"phase_id"},
    )
    result["phase_id"] = _string(_mapping(value, field)["phase_id"], f"{field}.phase_id")
    return result


def _objective(value: Any, field: str) -> dict[str, Any]:
    return _record_base(
        value,
        field,
        prefix="obj_",
        statuses=frozenset({"ACTIVE"}),
    )


def _requirement(value: Any, field: str) -> dict[str, Any]:
    return _record_base(value, field, prefix="req_", statuses=REQUIREMENT_STATUSES)


def _work_item(value: Any, field: str) -> dict[str, Any]:
    return _record_base(value, field, prefix="wrk_", statuses=WORK_ITEM_STATUSES)


def _blocker(value: Any, field: str) -> dict[str, Any]:
    result = _record_base(
        value,
        field,
        prefix="blk_",
        statuses=BLOCKER_STATUSES,
        extra_required={"severity"},
        extra_optional={"memory_ref"},
    )
    severity = _string(_mapping(value, field)["severity"], f"{field}.severity")
    if severity not in SEVERITIES:
        raise StateSchemaError(f"{field}.severity is unsupported: {severity}")
    result["severity"] = severity
    memory_ref = _mapping(value, field).get("memory_ref")
    if memory_ref is not None:
        result["memory_ref"] = _string(memory_ref, f"{field}.memory_ref", prefix="mem_")
    return result


def _constraint(value: Any, field: str) -> dict[str, Any]:
    return _record_base(value, field, prefix="con_", statuses=frozenset({"ACTIVE"}))


def _risk(value: Any, field: str) -> dict[str, Any]:
    result = _record_base(
        value,
        field,
        prefix="rsk_",
        statuses=frozenset({"ACTIVE"}),
        extra_required={"severity"},
    )
    severity = _string(_mapping(value, field)["severity"], f"{field}.severity")
    if severity not in SEVERITIES:
        raise StateSchemaError(f"{field}.severity is unsupported: {severity}")
    result["severity"] = severity
    return result


def _records(value: Any, field: str, parser) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise StateSchemaError(f"{field} must be an array")
    records = [parser(item, f"{field}[{index}]") for index, item in enumerate(value)]
    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)):
        raise StateSchemaError(f"{field} contains duplicate IDs")
    return records


def _project_state(value: Any, project_id: str) -> dict[str, Any]:
    field = f"projects.{project_id}"
    document = _mapping(value, field)
    _exact_keys(
        document,
        field,
        {
            "project_id",
            "revision",
            "created_at",
            "updated_at",
            "current",
            "requirements",
            "work_items",
            "blockers",
            "constraints",
            "risks",
            "references",
        },
    )
    if _string(document["project_id"], f"{field}.project_id") != project_id:
        raise StateSchemaError(f"{field}.project_id must match its dictionary key")
    current = _mapping(document["current"], f"{field}.current")
    _exact_keys(current, f"{field}.current", {"milestone", "objective"})
    milestone = current["milestone"]
    objective = current["objective"]
    if milestone is not None:
        milestone = _milestone(milestone, f"{field}.current.milestone")
    if objective is not None:
        objective = _objective(objective, f"{field}.current.objective")
    references = _mapping(document["references"], f"{field}.references")
    _exact_keys(references, f"{field}.references", {"memory_ids"})
    return {
        "project_id": project_id,
        "revision": _integer(document["revision"], f"{field}.revision"),
        "created_at": _timestamp(document["created_at"], f"{field}.created_at"),
        "updated_at": _timestamp(document["updated_at"], f"{field}.updated_at"),
        "current": {"milestone": milestone, "objective": objective},
        "requirements": _records(document["requirements"], f"{field}.requirements", _requirement),
        "work_items": _records(document["work_items"], f"{field}.work_items", _work_item),
        "blockers": _records(document["blockers"], f"{field}.blockers", _blocker),
        "constraints": _records(document["constraints"], f"{field}.constraints", _constraint),
        "risks": _records(document["risks"], f"{field}.risks", _risk),
        "references": {
            "memory_ids": _string_list(references["memory_ids"], f"{field}.references.memory_ids", prefix="mem_")
        },
    }


def _event(value: Any, field: str) -> dict[str, Any]:
    document = _mapping(value, field)
    _exact_keys(
        document,
        field,
        {"event_id", "project_id", "operation", "at", "old_revision", "new_revision", "source", "record_ids"},
    )
    old_revision = _integer(document["old_revision"], f"{field}.old_revision")
    new_revision = _integer(document["new_revision"], f"{field}.new_revision")
    if new_revision != old_revision + 1:
        raise StateSchemaError(f"{field}.new_revision must increment old_revision by one")
    return {
        "event_id": _string(document["event_id"], f"{field}.event_id", prefix="evt_"),
        "project_id": _string(document["project_id"], f"{field}.project_id"),
        "operation": _string(document["operation"], f"{field}.operation"),
        "at": _timestamp(document["at"], f"{field}.at"),
        "old_revision": old_revision,
        "new_revision": new_revision,
        "source": _provenance(document["source"], f"{field}.source", canonical=True),
        "record_ids": _string_list(document["record_ids"], f"{field}.record_ids"),
    }


def empty_state_document() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "store_revision": 0,
        "updated_at": utc_now(),
        "projects": {},
        "events": [],
    }


def validate_state_document(value: Any) -> dict[str, Any]:
    """Validate and normalize a canonical state snapshot without filesystem I/O."""
    document = _mapping(value, "state")
    _exact_keys(document, "state", {"schema_version", "store_revision", "updated_at", "projects", "events"})
    if document["schema_version"] != STATE_SCHEMA_VERSION:
        raise StateSchemaError(f"Unsupported state schema: {document['schema_version']}")
    projects_value = _mapping(document["projects"], "state.projects")
    projects: dict[str, dict[str, Any]] = {}
    for project_id, project_state in projects_value.items():
        normalized_id = _string(project_id, "state.projects key")
        if normalized_id in projects:
            raise StateSchemaError(f"state.projects duplicate project_id: {normalized_id}")
        projects[normalized_id] = _project_state(project_state, normalized_id)
    events_value = document["events"]
    if not isinstance(events_value, list):
        raise StateSchemaError("state.events must be an array")
    if len(events_value) > MAX_AUDIT_EVENTS:
        raise StateSchemaError(f"state.events must not exceed {MAX_AUDIT_EVENTS} entries")
    events = [_event(event, f"state.events[{index}]") for index, event in enumerate(events_value)]
    event_ids = [event["event_id"] for event in events]
    if len(event_ids) != len(set(event_ids)):
        raise StateSchemaError("state.events contains duplicate event IDs")
    for event in events:
        if event["project_id"] not in projects:
            raise StateSchemaError(f"state.events references unknown project_id: {event['project_id']}")
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "store_revision": _integer(document["store_revision"], "state.store_revision"),
        "updated_at": _timestamp(document["updated_at"], "state.updated_at"),
        "projects": projects,
        "events": events,
    }


def empty_project_state(project_id: str, source: Mapping[str, Any], *, now: Optional[str] = None) -> dict[str, Any]:
    """Create a valid but not-yet-persisted project state for explicit init."""
    project_id = _string(project_id, "project_id")
    timestamp = now or utc_now()
    return {
        "project_id": project_id,
        "revision": 0,
        "created_at": timestamp,
        "updated_at": timestamp,
        "current": {"milestone": None, "objective": None},
        "requirements": [],
        "work_items": [],
        "blockers": [],
        "constraints": [],
        "risks": [],
        "references": {"memory_ids": []},
        # Kept only for construction; the strict document validator receives
        # the source in the event and does not permit unrecognized fields.
    }


class StateStore:
    """Canonical state persistence with per-project CAS and atomic audit lineage."""

    def __init__(self, vault_path: str | Path):
        self.vault_path = Path(vault_path).expanduser()
        self.path = state_store_path(self.vault_path)
        self.backup_path = self.path.with_name("project-state.backup.json")

    def exists(self) -> bool:
        return self.path.exists()

    def _read_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return empty_state_document()
        for attempt in range(8):
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                return validate_state_document(payload)
            except PermissionError as exc:
                if attempt == 7:
                    raise StateStoreCorrupt(f"Cannot read canonical project state: {self.path}") from exc
                time.sleep(0.005 * (attempt + 1))
            except (OSError, json.JSONDecodeError, StateSchemaError) as exc:
                raise StateStoreCorrupt(f"Cannot read canonical project state: {self.path}") from exc
        raise AssertionError("unreachable state read retry exhaustion")

    def load(self) -> dict[str, Any]:
        """Read the latest valid snapshot; missing and corrupt remain distinct via exists()."""
        return self._read_unlocked()

    def get_project(self, project_id: str) -> Optional[dict[str, Any]]:
        return deepcopy(self.load()["projects"].get(_string(project_id, "project_id")))

    def project_revision(self, project_id: str) -> Optional[int]:
        project = self.get_project(project_id)
        return None if project is None else int(project["revision"])

    def _write_unlocked(self, state: Mapping[str, Any]) -> None:
        normalized = validate_state_document(state)
        temporary: Optional[Path] = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                shutil.copy2(self.path, self.backup_path)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".project-state-",
                suffix=".json",
                dir=self.path.parent,
            )
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(normalized, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._replace_with_retry(temporary)
        except OSError as exc:
            raise StateStorePersistenceError(f"Cannot persist canonical project state: {self.path}") from exc
        finally:
            if temporary is not None and temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass

    def _replace_with_retry(self, temporary: Path) -> None:
        """Handle only short-lived Windows sharing locks while holding the write lock."""
        for attempt in range(8):
            try:
                temporary.replace(self.path)
                return
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(0.005 * (attempt + 1))

    @staticmethod
    def _append_event(
        state: dict[str, Any],
        *,
        project_id: str,
        operation: str,
        source: Mapping[str, Any],
        old_revision: int,
        record_ids: list[str],
        at: Optional[str] = None,
    ) -> dict[str, Any]:
        event = {
            "event_id": new_state_id("event"),
            "project_id": project_id,
            "operation": _string(operation, "operation"),
            "at": at or utc_now(),
            "old_revision": old_revision,
            "new_revision": old_revision + 1,
            "source": _provenance(source, "source", canonical=True),
            "record_ids": _string_list(record_ids, "record_ids"),
        }
        state["events"] = (state["events"] + [event])[-MAX_AUDIT_EVENTS:]
        return event

    def init_project(
        self,
        project_id: str,
        *,
        source: Mapping[str, Any],
        now: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create one empty state only when explicitly requested by a caller."""
        project_id = _string(project_id, "project_id")
        timestamp = now or utc_now()
        try:
            with file_lock(self.path):
                state = self._read_unlocked()
                if project_id in state["projects"]:
                    raise StateError(f"State already exists for project_id: {project_id}")
                project = empty_project_state(project_id, source, now=timestamp)
                project["revision"] = 1
                project["updated_at"] = timestamp
                state["projects"][project_id] = project
                state["store_revision"] += 1
                self._append_event(
                    state,
                    project_id=project_id,
                    operation="state_initialized",
                    source=source,
                    old_revision=0,
                    record_ids=[],
                    at=timestamp,
                )
                state["updated_at"] = timestamp
                self._write_unlocked(state)
                return deepcopy(project)
        except MemoryStoreLockTimeout as exc:
            raise StateStoreLockTimeout(str(exc)) from exc

    def _transact_project(
        self,
        project_id: str,
        *,
        expected_revision: int,
        operation: str,
        source: Mapping[str, Any],
        record_ids: list[str],
        mutator,
        now: Optional[str] = None,
    ) -> tuple[Any, dict[str, Any]]:
        """Perform one validated, revisioned project-state transaction."""
        project_id = _string(project_id, "project_id")
        expected_revision = _integer(expected_revision, "expected_revision")
        timestamp = now or utc_now()
        try:
            with file_lock(self.path):
                state = self._read_unlocked()
                project = state["projects"].get(project_id)
                if project is None:
                    raise StateError(f"STATE_NOT_FOUND for project_id: {project_id}")
                actual_revision = int(project["revision"])
                if expected_revision != actual_revision:
                    raise StateStoreConflict(project_id, expected_revision, actual_revision)

                candidate = deepcopy(project)
                result = mutator(candidate)
                candidate["project_id"] = project_id
                candidate["revision"] = actual_revision + 1
                candidate["updated_at"] = timestamp
                state["projects"][project_id] = candidate
                state["store_revision"] += 1
                self._append_event(
                    state,
                    project_id=project_id,
                    operation=operation,
                    source=source,
                    old_revision=actual_revision,
                    record_ids=record_ids,
                    at=timestamp,
                )
                state["updated_at"] = timestamp
                self._write_unlocked(state)
                return result, deepcopy(candidate)
        except MemoryStoreLockTimeout as exc:
            raise StateStoreLockTimeout(str(exc)) from exc


_MILESTONE_TRANSITIONS = {
    "PLANNED": frozenset({"ACTIVE", "CANCELLED"}),
    "ACTIVE": frozenset({"BLOCKED", "COMPLETED", "CANCELLED"}),
    "BLOCKED": frozenset({"ACTIVE", "CANCELLED"}),
    "COMPLETED": frozenset(),
    "CANCELLED": frozenset(),
}
_WORK_ITEM_TRANSITIONS = {
    "TODO": frozenset({"ACTIVE", "BLOCKED", "DONE", "DROPPED"}),
    "ACTIVE": frozenset({"BLOCKED", "DONE", "DROPPED"}),
    "BLOCKED": frozenset({"ACTIVE", "DONE", "DROPPED"}),
    "DONE": frozenset(),
    "DROPPED": frozenset(),
}


class StateService:
    """The only public typed mutation surface for canonical project state."""

    def __init__(self, vault_path: str | Path):
        self.vault_path = Path(vault_path).expanduser()
        self.store = StateStore(self.vault_path)
        self.registry = ProjectRegistry(self.vault_path)
        self.memory_store = MemoryStore(self.vault_path)

    @staticmethod
    def _source(source: Mapping[str, Any]) -> dict[str, Any]:
        return _provenance(source, "source", canonical=True)

    def _require_active_project(self, project_id: str) -> dict[str, Any]:
        project_id = _string(project_id, "project_id")
        try:
            record = self.registry.get(project_id)
        except ProjectRegistryError as exc:
            raise StateError("Project registry is unavailable for state mutation") from exc
        if record is None:
            raise StateProjectUnknown(f"PROJECT_UNKNOWN: {project_id}")
        if record["status"] != "active":
            raise StateProjectArchived(f"PROJECT_ARCHIVED: {project_id}")
        return record

    def init_project(
        self,
        project_id: str,
        *,
        source: Mapping[str, Any],
        now: Optional[str] = None,
    ) -> dict[str, Any]:
        self._require_active_project(project_id)
        return self.store.init_project(project_id, source=self._source(source), now=now)

    def _mutate(
        self,
        project_id: str,
        *,
        expected_revision: int,
        operation: str,
        source: Mapping[str, Any],
        record_ids: list[str],
        mutator,
        now: Optional[str] = None,
    ) -> tuple[Any, dict[str, Any]]:
        self._require_active_project(project_id)
        return self.store._transact_project(
            project_id,
            expected_revision=expected_revision,
            operation=operation,
            source=self._source(source),
            record_ids=record_ids,
            mutator=mutator,
            now=now,
        )

    @staticmethod
    def _record(
        *,
        kind: str,
        text: str,
        status: str,
        source: Mapping[str, Any],
        now: str,
        record_id: Optional[str] = None,
        title: bool = False,
        severity: Optional[str] = None,
        memory_ref: Optional[str] = None,
    ) -> dict[str, Any]:
        field = "title" if title else "text"
        result = {
            "id": record_id or new_state_id(kind),
            field: _string(text, field),
            "status": status,
            "source": StateService._source(source),
            "created_at": now,
            "updated_at": now,
        }
        if severity is not None:
            severity = _string(severity, "severity").upper()
            if severity not in SEVERITIES:
                raise StateSchemaError(f"severity is unsupported: {severity}")
            result["severity"] = severity
        if memory_ref is not None:
            result["memory_ref"] = _string(memory_ref, "memory_ref", prefix="mem_")
        return result

    def set_current_milestone(
        self,
        project_id: str,
        *,
        phase_id: str,
        title: str,
        expected_revision: int,
        source: Mapping[str, Any],
        record_id: Optional[str] = None,
        now: Optional[str] = None,
    ) -> dict[str, Any]:
        timestamp = now or utc_now()
        milestone = self._record(
            kind="milestone",
            text=title,
            status="ACTIVE",
            source=source,
            now=timestamp,
            record_id=record_id,
            title=True,
        )
        phase_id = _string(phase_id, "phase_id")

        def mutate(project):
            existing = project["current"]["milestone"]
            if existing is not None and existing["status"] not in {"COMPLETED", "CANCELLED"}:
                raise StateTransitionError("INVALID_TRANSITION: current milestone is not terminal")
            milestone["phase_id"] = phase_id
            project["current"]["milestone"] = milestone
            return deepcopy(milestone)

        _result, persisted = self._mutate(
            project_id,
            expected_revision=expected_revision,
            operation="milestone_set",
            source=source,
            record_ids=[milestone["id"]],
            mutator=mutate,
            now=timestamp,
        )
        return persisted

    def transition_milestone(
        self,
        project_id: str,
        *,
        milestone_id: str,
        target_status: str,
        expected_revision: int,
        source: Mapping[str, Any],
        now: Optional[str] = None,
    ) -> dict[str, Any]:
        target_status = _string(target_status, "target_status").upper()
        if target_status not in MILESTONE_STATUSES:
            raise StateTransitionError(f"INVALID_TRANSITION: unsupported milestone status {target_status}")
        timestamp = now or utc_now()

        def mutate(project):
            milestone = project["current"]["milestone"]
            if milestone is None or milestone["id"] != milestone_id:
                raise StateTransitionError(f"INVALID_TRANSITION: unknown current milestone {milestone_id}")
            if target_status not in _MILESTONE_TRANSITIONS[milestone["status"]]:
                raise StateTransitionError(
                    f"INVALID_TRANSITION: {milestone['status']} -> {target_status}"
                )
            milestone["status"] = target_status
            milestone["updated_at"] = timestamp
            return deepcopy(milestone)

        _result, persisted = self._mutate(
            project_id,
            expected_revision=expected_revision,
            operation="milestone_transitioned",
            source=source,
            record_ids=[_string(milestone_id, "milestone_id", prefix="mil_")],
            mutator=mutate,
            now=timestamp,
        )
        return persisted

    def set_current_objective(
        self,
        project_id: str,
        *,
        text: str,
        expected_revision: int,
        source: Mapping[str, Any],
        record_id: Optional[str] = None,
        now: Optional[str] = None,
    ) -> dict[str, Any]:
        timestamp = now or utc_now()
        objective = self._record(
            kind="objective",
            text=text,
            status="ACTIVE",
            source=source,
            now=timestamp,
            record_id=record_id,
        )

        def mutate(project):
            project["current"]["objective"] = objective
            return deepcopy(objective)

        _result, persisted = self._mutate(
            project_id,
            expected_revision=expected_revision,
            operation="objective_set",
            source=source,
            record_ids=[objective["id"]],
            mutator=mutate,
            now=timestamp,
        )
        return persisted

    def add_requirement(
        self,
        project_id: str,
        *,
        text: str,
        expected_revision: int,
        source: Mapping[str, Any],
        record_id: Optional[str] = None,
        now: Optional[str] = None,
    ) -> dict[str, Any]:
        return self._add_record(
            project_id,
            collection="requirements",
            kind="requirement",
            text=text,
            status="ACTIVE",
            expected_revision=expected_revision,
            source=source,
            record_id=record_id,
            operation="requirement_added",
            now=now,
        )

    def resolve_requirement(
        self,
        project_id: str,
        *,
        requirement_id: str,
        expected_revision: int,
        source: Mapping[str, Any],
        cancelled: bool = False,
        now: Optional[str] = None,
    ) -> dict[str, Any]:
        target_status = "CANCELLED" if cancelled else "RESOLVED"
        timestamp = now or utc_now()

        def mutate(project):
            record = next((item for item in project["requirements"] if item["id"] == requirement_id), None)
            if record is None or record["status"] != "ACTIVE":
                raise StateTransitionError(f"INVALID_TRANSITION: requirement {requirement_id}")
            record["status"] = target_status
            record["updated_at"] = timestamp
            return deepcopy(record)

        _result, persisted = self._mutate(
            project_id,
            expected_revision=expected_revision,
            operation="requirement_resolved" if not cancelled else "requirement_cancelled",
            source=source,
            record_ids=[_string(requirement_id, "requirement_id", prefix="req_")],
            mutator=mutate,
            now=timestamp,
        )
        return persisted

    def add_work_item(
        self,
        project_id: str,
        *,
        text: str,
        expected_revision: int,
        source: Mapping[str, Any],
        record_id: Optional[str] = None,
        now: Optional[str] = None,
    ) -> dict[str, Any]:
        return self._add_record(
            project_id,
            collection="work_items",
            kind="work_item",
            text=text,
            status="TODO",
            expected_revision=expected_revision,
            source=source,
            record_id=record_id,
            operation="work_item_added",
            now=now,
        )

    def transition_work_item(
        self,
        project_id: str,
        *,
        work_item_id: str,
        target_status: str,
        expected_revision: int,
        source: Mapping[str, Any],
        now: Optional[str] = None,
    ) -> dict[str, Any]:
        target_status = _string(target_status, "target_status").upper()
        if target_status not in WORK_ITEM_STATUSES:
            raise StateTransitionError(f"INVALID_TRANSITION: unsupported work status {target_status}")
        timestamp = now or utc_now()

        def mutate(project):
            record = next((item for item in project["work_items"] if item["id"] == work_item_id), None)
            if record is None or target_status not in _WORK_ITEM_TRANSITIONS[record["status"]]:
                raise StateTransitionError(f"INVALID_TRANSITION: work item {work_item_id} -> {target_status}")
            record["status"] = target_status
            record["updated_at"] = timestamp
            return deepcopy(record)

        _result, persisted = self._mutate(
            project_id,
            expected_revision=expected_revision,
            operation="work_item_transitioned",
            source=source,
            record_ids=[_string(work_item_id, "work_item_id", prefix="wrk_")],
            mutator=mutate,
            now=timestamp,
        )
        return persisted

    def _validate_memory_reference(self, project_id: str, memory_id: str) -> str:
        memory_id = _string(memory_id, "memory_id", prefix="mem_")
        try:
            records = self.memory_store.load()["validated_memory"]
        except MemoryStoreError as exc:
            raise StateReferenceError("MemoryStore is unavailable for state reference validation") from exc
        record = next((item for item in records if item.get("memory_id") == memory_id), None)
        if record is None:
            raise StateReferenceError(f"DANGLING_MEMORY_REFERENCE: {memory_id}")
        scope = record.get("scope")
        if scope == "global":
            return memory_id
        if scope == "project" and record.get("project_id") == project_id:
            return memory_id
        raise StateReferenceError(f"WRONG_PROJECT_MEMORY_REFERENCE: {memory_id}")

    def add_memory_reference(
        self,
        project_id: str,
        *,
        memory_id: str,
        expected_revision: int,
        source: Mapping[str, Any],
        now: Optional[str] = None,
    ) -> dict[str, Any]:
        memory_id = self._validate_memory_reference(project_id, memory_id)

        def mutate(project):
            references = project["references"]["memory_ids"]
            if memory_id in references:
                raise StateError(f"State already references memory_id: {memory_id}")
            references.append(memory_id)
            return memory_id

        _result, persisted = self._mutate(
            project_id,
            expected_revision=expected_revision,
            operation="memory_reference_added",
            source=source,
            record_ids=[memory_id],
            mutator=mutate,
            now=now,
        )
        return persisted

    def add_blocker(
        self,
        project_id: str,
        *,
        text: str,
        severity: str,
        expected_revision: int,
        source: Mapping[str, Any],
        record_id: Optional[str] = None,
        memory_ref: Optional[str] = None,
        now: Optional[str] = None,
    ) -> dict[str, Any]:
        if memory_ref is not None:
            memory_ref = self._validate_memory_reference(project_id, memory_ref)
        timestamp = now or utc_now()
        blocker = self._record(
            kind="blocker",
            text=text,
            status="ACTIVE",
            source=source,
            now=timestamp,
            record_id=record_id,
            severity=severity,
            memory_ref=memory_ref,
        )

        def mutate(project):
            if any(item["id"] == blocker["id"] for item in project["blockers"]):
                raise StateError(f"Duplicate blocker ID: {blocker['id']}")
            project["blockers"].append(blocker)
            return deepcopy(blocker)

        _result, persisted = self._mutate(
            project_id,
            expected_revision=expected_revision,
            operation="blocker_added",
            source=source,
            record_ids=[blocker["id"]],
            mutator=mutate,
            now=timestamp,
        )
        return persisted

    def resolve_blocker(
        self,
        project_id: str,
        *,
        blocker_id: str,
        expected_revision: int,
        source: Mapping[str, Any],
        now: Optional[str] = None,
    ) -> dict[str, Any]:
        timestamp = now or utc_now()

        def mutate(project):
            record = next((item for item in project["blockers"] if item["id"] == blocker_id), None)
            if record is None or record["status"] != "ACTIVE":
                raise StateTransitionError(f"INVALID_TRANSITION: blocker {blocker_id}")
            record["status"] = "RESOLVED"
            record["updated_at"] = timestamp
            return deepcopy(record)

        _result, persisted = self._mutate(
            project_id,
            expected_revision=expected_revision,
            operation="blocker_resolved",
            source=source,
            record_ids=[_string(blocker_id, "blocker_id", prefix="blk_")],
            mutator=mutate,
            now=timestamp,
        )
        return persisted

    def add_constraint(
        self,
        project_id: str,
        *,
        text: str,
        expected_revision: int,
        source: Mapping[str, Any],
        record_id: Optional[str] = None,
        now: Optional[str] = None,
    ) -> dict[str, Any]:
        return self._add_record(
            project_id,
            collection="constraints",
            kind="constraint",
            text=text,
            status="ACTIVE",
            expected_revision=expected_revision,
            source=source,
            record_id=record_id,
            operation="constraint_added",
            now=now,
        )

    def add_risk(
        self,
        project_id: str,
        *,
        text: str,
        severity: str,
        expected_revision: int,
        source: Mapping[str, Any],
        record_id: Optional[str] = None,
        now: Optional[str] = None,
    ) -> dict[str, Any]:
        timestamp = now or utc_now()
        risk = self._record(
            kind="risk",
            text=text,
            status="ACTIVE",
            source=source,
            now=timestamp,
            record_id=record_id,
            severity=severity,
        )

        def mutate(project):
            if any(item["id"] == risk["id"] for item in project["risks"]):
                raise StateError(f"Duplicate risk ID: {risk['id']}")
            project["risks"].append(risk)
            return deepcopy(risk)

        _result, persisted = self._mutate(
            project_id,
            expected_revision=expected_revision,
            operation="risk_added",
            source=source,
            record_ids=[risk["id"]],
            mutator=mutate,
            now=timestamp,
        )
        return persisted

    def _add_record(
        self,
        project_id: str,
        *,
        collection: str,
        kind: str,
        text: str,
        status: str,
        expected_revision: int,
        source: Mapping[str, Any],
        record_id: Optional[str],
        operation: str,
        now: Optional[str],
    ) -> dict[str, Any]:
        timestamp = now or utc_now()
        record = self._record(
            kind=kind,
            text=text,
            status=status,
            source=source,
            now=timestamp,
            record_id=record_id,
        )

        def mutate(project):
            if any(item["id"] == record["id"] for item in project[collection]):
                raise StateError(f"Duplicate {kind} ID: {record['id']}")
            project[collection].append(record)
            return deepcopy(record)

        _result, persisted = self._mutate(
            project_id,
            expected_revision=expected_revision,
            operation=operation,
            source=source,
            record_ids=[record["id"]],
            mutator=mutate,
            now=timestamp,
        )
        return persisted
