#!/usr/bin/env python3
"""Revision-bound provenance projection for legacy and evidence-backed memory.

The Phase 14 canonical MemoryStore remains the authority.  This projection
adds temporal/evidence metadata without rewriting canonical memory records or
changing their immutable IDs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from brain_eleven.memory import MemoryStore, MemoryStoreCorrupt
from memory_store_lock import MemoryStoreLockTimeout, file_lock


PROVENANCE_SCHEMA_VERSION = 1
PROVENANCE_FILENAME = "memory-provenance.json"
_DAILY_DATE = re.compile(r"(?:^|:)daily:(\d{4}-\d{2}-\d{2})(?::|$)")


class ProvenanceError(ValueError):
    code = "MEMORY_PROVENANCE_INVALID"


class ProvenanceCorruptError(ProvenanceError):
    code = "MEMORY_PROVENANCE_CORRUPT"


class ProvenanceStoreError(ProvenanceError):
    code = "MEMORY_PROVENANCE_WRITE_FAILED"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class TimeValue:
    value: str
    precision: str


@dataclass(frozen=True)
class MemoryProvenance:
    memory_id: str
    occurred_at: Optional[TimeValue]
    captured_at: Optional[TimeValue]
    canonicalized_at: Optional[TimeValue]
    updated_at: Optional[TimeValue]
    last_confirmed_at: Optional[TimeValue]
    evidence_refs: tuple[str, ...] = ()
    source_session_id: Optional[str] = None
    capture_job_id: Optional[str] = None
    migration_confidence: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_refs"] = list(self.evidence_refs)
        return payload


def provenance_path(vault_path: str | Path) -> Path:
    return Path(vault_path) / ".claude" / PROVENANCE_FILENAME


def _time(value: Any, precision: str) -> Optional[TimeValue]:
    if not isinstance(value, str) or not value:
        return None
    return TimeValue(value=value, precision=precision)


def _legacy_provenance(memory: Mapping[str, Any]) -> MemoryProvenance:
    memory_id = str(memory.get("memory_id") or "").strip()
    if not memory_id:
        raise ProvenanceCorruptError("canonical memory is missing memory_id")
    timestamp = memory.get("timestamp")
    captured = _time(timestamp, "instant") if isinstance(timestamp, str) else None
    occurred = None
    source_id = str(memory.get("source_id") or "")
    match = _DAILY_DATE.search(source_id)
    if match:
        occurred = TimeValue(value=match.group(1), precision="day")
    if captured is not None and "T" in captured.value and "+" not in captured.value and not captured.value.endswith("Z"):
        captured = TimeValue(value=captured.value, precision="unknown")
    return MemoryProvenance(
        memory_id=memory_id,
        occurred_at=occurred,
        captured_at=captured,
        canonicalized_at=None,
        updated_at=None,
        last_confirmed_at=None,
        migration_confidence="day_from_source_id" if occurred else "legacy_timestamp_as_capture",
    )


def _atomic_write(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        temporary_path = Path(temporary)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(document, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary_path.replace(path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
    except OSError as exc:
        raise ProvenanceStoreError("memory provenance could not be written") from exc


class MemoryProvenanceStore:
    """Derived provenance store keyed only by immutable canonical memory IDs."""

    def __init__(self, vault_path: str | Path):
        self.vault_path = Path(vault_path)
        self.path = provenance_path(vault_path)
        self.lock_path = self.path.with_name(f"{self.path.name}.lock-target")

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": PROVENANCE_SCHEMA_VERSION, "source_memory_revision": None, "updated_at": None, "records": {}}
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProvenanceCorruptError("memory provenance projection is unreadable") from exc
        if not isinstance(document, dict) or document.get("schema_version") != PROVENANCE_SCHEMA_VERSION or not isinstance(document.get("records"), dict):
            raise ProvenanceCorruptError("memory provenance projection schema is unsupported")
        source_revision = document.get("source_memory_revision")
        if source_revision is not None and (isinstance(source_revision, bool) or not isinstance(source_revision, int) or source_revision < 0):
            raise ProvenanceCorruptError("memory provenance source revision is invalid")
        for memory_id, record in document["records"].items():
            if not isinstance(memory_id, str) or not memory_id.strip() or not isinstance(record, dict) or record.get("memory_id") != memory_id:
                raise ProvenanceCorruptError("memory provenance record identity is invalid")
        return document

    def migrate_legacy(self) -> dict[str, Any]:
        try:
            canonical = MemoryStore(self.vault_path).load()
        except MemoryStoreCorrupt as exc:
            raise ProvenanceCorruptError("canonical memory is unavailable") from exc
        records: dict[str, Any] = {}
        for bucket in ("validated_memory", "rejected_memory"):
            for memory in canonical.get(bucket, []):
                if isinstance(memory, Mapping):
                    record = _legacy_provenance(memory)
                    records[record.memory_id] = record.to_dict()
        document = {
            "schema_version": PROVENANCE_SCHEMA_VERSION,
            "source_memory_revision": int(canonical["revision"]),
            "updated_at": _utc_now(),
            "records": records,
        }
        try:
            with file_lock(self.lock_path):
                existing = self.load() if self.path.exists() else None
                if existing is not None and existing.get("source_memory_revision") == document["source_memory_revision"] and existing.get("records") == records:
                    return existing
                _atomic_write(self.path, document)
        except MemoryStoreLockTimeout as exc:
            raise ProvenanceStoreError("memory provenance lock timed out") from exc
        return document


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build a revision-bound memory provenance projection")
    parser.add_argument("migrate", nargs="?", default="migrate")
    parser.add_argument("--vault", default=".")
    arguments = parser.parse_args(argv)
    try:
        result = MemoryProvenanceStore(arguments.vault).migrate_legacy()
    except ProvenanceError as exc:
        print(json.dumps({"error": {"code": exc.code}}))
        return 2
    print(json.dumps({"source_memory_revision": result["source_memory_revision"], "record_count": len(result["records"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
