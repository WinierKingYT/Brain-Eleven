#!/usr/bin/env python3
"""Canonical transactional access to Brain-Eleven's memory store.

All canonical mutations go through this module.  The JSON file remains the
storage format, but every write now has a monotonically increasing revision
and is protected by the existing cross-platform sidecar lock.
"""

import json
import os
import shutil
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple, Union
from collections.abc import Mapping

try:
    from brain_eleven.infrastructure.locking import memory_store_lock
except ModuleNotFoundError as exc:  # pragma: no cover - copied-hook fallback
    if exc.name != "brain_eleven":
        raise
    from memory_store_lock import memory_store_lock


CANONICAL_SCHEMA_VERSION = 2


class MemoryStoreError(RuntimeError):
    """Base class for canonical-store failures."""


class MemoryStoreConflict(MemoryStoreError):
    """Raised when a caller writes against an obsolete store revision."""

    def __init__(self, expected_revision: int, actual_revision: int):
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision
        super().__init__(
            f"Memory store revision conflict: expected {expected_revision}, "
            f"actual {actual_revision}"
        )


class MemoryStoreCorrupt(MemoryStoreError):
    """Raised when the canonical JSON cannot be trusted."""


class MemoryStoreRecordInvalid(MemoryStoreError):
    """Raised when a nested canonical memory record is malformed."""


class _NoChange:
    def __init__(self, value):
        self.value = value


def no_change(value=None) -> _NoChange:
    """Return a transaction result that deliberately skips persistence."""
    return _NoChange(value)


_VALID_RECORD_SCOPE = {"global", "project"}
_RECORD_STRING_FIELDS = {
    "timestamp",
    "source_id",
    "source",
    "dedup_fingerprint",
    "project_id",
    "project",
    "project_label",
}


def _validate_record(record: Mapping) -> None:
    """Validate the minimum canonical record boundary before locking."""
    if not isinstance(record, Mapping):
        raise MemoryStoreRecordInvalid("Canonical memory record must be an object")
    for field in ("memory_id", "type", "content"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            raise MemoryStoreRecordInvalid(f"Canonical memory {field} must be a non-empty string")

    for field in _RECORD_STRING_FIELDS:
        if field in record and not isinstance(record[field], str):
            raise MemoryStoreRecordInvalid(f"Canonical memory {field} must be a string")

    status = record.get("status")
    if "status" in record and (not isinstance(status, str) or not status.strip()):
        raise MemoryStoreRecordInvalid("Canonical memory status is invalid")

    scope = record.get("scope")
    if "scope" in record and (not isinstance(scope, str) or scope not in _VALID_RECORD_SCOPE):
        raise MemoryStoreRecordInvalid("Canonical memory scope is invalid")
    # A missing scope is legacy-global.  Do not silently attach project
    # identity to such a record.
    effective_scope = scope if scope is not None else "global"
    project_id = record.get("project_id", "")
    project = record.get("project", "")
    project_label = record.get("project_label", "")
    if effective_scope == "project" and not project_id.strip():
        raise MemoryStoreRecordInvalid("Project-scoped memory requires project_id")
    if effective_scope == "global" and any(value.strip() for value in (project_id, project, project_label)):
        raise MemoryStoreRecordInvalid("Global memory cannot carry project identity")

    if "is_approved" in record and not isinstance(record["is_approved"], bool):
        raise MemoryStoreRecordInvalid("Canonical memory is_approved must be boolean")
    for field in ("issues", "related_notes"):
        if field in record and not isinstance(record[field], list):
            raise MemoryStoreRecordInvalid(f"Canonical memory {field} must be a list")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fsync_parent_directory(path: Path) -> None:
    """Persist the directory entry after replacement where supported."""
    if os.name == "nt":
        # Directory handles are not consistently openable for fsync on the
        # supported Windows versions; the file handle was already fsynced.
        return
    descriptor = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class MemoryStore:
    """Read and mutate the canonical store with lock/reload/revision semantics."""

    def __init__(self, vault_path: Union[str, Path]):
        self.vault_path = Path(vault_path).expanduser()
        self.path = self.vault_path / ".claude" / "validated-memory.json"
        self.backup_path = self.path.with_name("validated-memory.backup.json")

    @staticmethod
    def empty_document() -> Dict:
        return {
            "schema_version": CANONICAL_SCHEMA_VERSION,
            "revision": 0,
            "updated_at": _utc_now(),
            "validated_at": _utc_now(),
            "summary": {},
            "validated_memory": [],
            "rejected_memory": [],
        }

    @staticmethod
    def _normalize(data: Dict) -> Dict:
        if not isinstance(data, dict):
            raise MemoryStoreCorrupt("Canonical memory store must be a JSON object")

        schema_version = data.get("schema_version", 1)
        if schema_version not in (1, CANONICAL_SCHEMA_VERSION, 3):
            raise MemoryStoreCorrupt(f"Unsupported canonical schema version: {schema_version}")

        normalized = dict(data)
        normalized["schema_version"] = max(CANONICAL_SCHEMA_VERSION, schema_version)
        if schema_version == 3:
            from brain_eleven.operations import validate_receipts
            try:
                validate_receipts(normalized.get("operation_receipts"))
            except ValueError as exc:
                raise MemoryStoreCorrupt("Invalid operation receipts") from exc
        try:
            normalized["revision"] = int(data.get("revision", 0))
        except (TypeError, ValueError) as exc:
            raise MemoryStoreCorrupt("Canonical revision must be an integer") from exc
        if normalized["revision"] < 0:
            raise MemoryStoreCorrupt("Canonical revision cannot be negative")
        normalized.setdefault("updated_at", data.get("validated_at") or _utc_now())
        normalized.setdefault("validated_at", normalized["updated_at"])
        normalized.setdefault("summary", {})
        for bucket in ("validated_memory", "rejected_memory"):
            if not isinstance(normalized.get(bucket, []), list):
                raise MemoryStoreCorrupt(f"Canonical bucket is not a list: {bucket}")
            normalized.setdefault(bucket, [])
        return normalized

    def _read_unlocked(self) -> Dict:
        if not self.path.exists():
            return self.empty_document()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MemoryStoreCorrupt(f"Cannot read canonical memory store: {self.path}") from exc
        return self._normalize(data)

    def load(self) -> Dict:
        """Load the latest canonical snapshot without holding a writer lock."""
        return self._read_unlocked()

    def revision(self) -> int:
        return int(self.load()["revision"])

    def _write_unlocked(self, data: Dict) -> None:
        normalized = self._normalize(data)
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                shutil.copy2(self.path, self.backup_path)

            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".memory-store-", suffix=".json", dir=self.path.parent
            )
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(normalized, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(self.path)
            _fsync_parent_directory(self.path)
        except OSError as exc:
            raise MemoryStoreError(f"Cannot persist canonical memory store: {self.path}") from exc
        finally:
            if temporary is not None and temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass

    def transact(
        self,
        mutator: Callable[[Dict], object],
        expected_revision: Optional[int] = None,
    ) -> Tuple[object, Dict]:
        """Run one lock/reload/mutate/revision/atomic-write transaction."""
        with memory_store_lock(self.vault_path):
            latest = self._read_unlocked()
            actual_revision = int(latest["revision"])
            if expected_revision is not None and expected_revision != actual_revision:
                raise MemoryStoreConflict(expected_revision, actual_revision)

            result = mutator(latest)
            if isinstance(result, _NoChange):
                return result.value, deepcopy(latest)
            latest["revision"] = actual_revision + 1
            latest["schema_version"] = max(latest.get("schema_version", 2), CANONICAL_SCHEMA_VERSION)
            latest["updated_at"] = _utc_now()
            self._write_unlocked(latest)
            return result, deepcopy(latest)

    def replace(self, data: Dict, expected_revision: Optional[int] = None) -> Dict:
        """Replace the canonical payload while preserving transactional metadata."""
        def mutate(latest):
            replacement = dict(data)
            replacement["revision"] = latest["revision"]
            replacement["schema_version"] = max(latest["schema_version"], replacement.get("schema_version", 2))
            if latest.get("schema_version") == 3:
                receipts = latest["operation_receipts"]
                if receipts and replacement.get("operation_receipts") != receipts:
                    raise MemoryStoreCorrupt("Replacement would discard runtime operation receipts")
                replacement["operation_receipts"] = deepcopy(receipts)
            latest.clear()
            latest.update(replacement)
            return None

        _result, persisted = self.transact(mutate, expected_revision=expected_revision)
        return persisted
    def append(
        self,
        record: Dict,
        bucket: str = "validated_memory",
        expected_revision: Optional[int] = None,
    ) -> Dict:
        """Append one canonical record through the transaction boundary."""
        if bucket not in {"validated_memory", "rejected_memory"}:
            raise ValueError(f"Unsupported canonical bucket: {bucket}")
        _validate_record(record)

        def mutate(latest):
            latest.setdefault(bucket, []).append(dict(record))
            return None

        _result, persisted = self.transact(mutate, expected_revision=expected_revision)
        return persisted
