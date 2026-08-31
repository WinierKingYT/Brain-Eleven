#!/usr/bin/env python3
"""Transactional access to Brain-Eleven's canonical memory store.

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


class _NoChange:
    def __init__(self, value):
        self.value = value


def no_change(value=None) -> _NoChange:
    """Return a transaction result that deliberately skips persistence."""
    return _NoChange(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
        if schema_version not in (1, CANONICAL_SCHEMA_VERSION):
            raise MemoryStoreCorrupt(f"Unsupported canonical schema version: {schema_version}")

        normalized = dict(data)
        normalized["schema_version"] = CANONICAL_SCHEMA_VERSION
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            shutil.copy2(self.path, self.backup_path)

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".memory-store-", suffix=".json", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(normalized, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            Path(temporary_name).replace(self.path)
        except OSError as exc:
            raise MemoryStoreError(f"Cannot persist canonical memory store: {self.path}") from exc
        finally:
            temporary = Path(temporary_name)
            if temporary.exists():
                temporary.unlink()

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
            latest["schema_version"] = CANONICAL_SCHEMA_VERSION
            latest["updated_at"] = _utc_now()
            self._write_unlocked(latest)
            return result, deepcopy(latest)

    def replace(self, data: Dict, expected_revision: Optional[int] = None) -> Dict:
        """Replace the canonical payload while preserving transactional metadata."""
        def mutate(latest):
            replacement = dict(data)
            replacement["revision"] = latest["revision"]
            replacement["schema_version"] = CANONICAL_SCHEMA_VERSION
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

        def mutate(latest):
            latest.setdefault(bucket, []).append(dict(record))
            return None

        _result, persisted = self.transact(mutate, expected_revision=expected_revision)
        return persisted
