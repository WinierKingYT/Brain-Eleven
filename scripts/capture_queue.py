#!/usr/bin/env python3
"""Durable, content-safe PRE-02 capture queue.

This module is intentionally a delivery boundary only.  It accepts a bounded
``HookEvent`` and records an at-least-once local job.  It never reads a
transcript, invokes an extractor, or writes canonical MemoryStore/StateStore
data.  A later worker owns those responsibilities.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from capture_event import (
    CAPTURE_EVENT_SCHEMA_VERSION,
    EVENT_TYPES,
    MAX_HOOK_EVENT_BYTES,
    CaptureEventError,
    HookEvent,
    parse_native_hook_event_json,
)
try:
    from brain_eleven.infrastructure.locking import MemoryStoreLockTimeout, file_lock
except ImportError:  # pragma: no cover - deployed copied-hook fallback
    from memory_store_lock import MemoryStoreLockTimeout, file_lock


CAPTURE_QUEUE_SCHEMA_VERSION = 1
JOB_PREFIX = "cap_"
QUEUED = "QUEUED"
CLAIMED = "CLAIMED"
PROCESSING = "PROCESSING"
COMMITTED = "COMMITTED"
DEAD_LETTER = "DEAD_LETTER"
JOB_STATUSES = frozenset({QUEUED, CLAIMED, PROCESSING, COMMITTED, DEAD_LETTER})
QUEUE_DIRECTORIES = {
    QUEUED: "queued",
    CLAIMED: "processing",
    PROCESSING: "processing",
    COMMITTED: "completed",
    DEAD_LETTER: "dead-letter",
}


class CaptureQueueError(RuntimeError):
    """Base error with a stable, content-safe queue failure code."""

    code = "CAPTURE_QUEUE_FAILED"


class CaptureQueueFullError(CaptureQueueError):
    code = "CAPTURE_QUEUE_FULL"


class CaptureQueueCorruptError(CaptureQueueError):
    code = "CAPTURE_QUEUE_CORRUPT"


class CaptureQueueStateError(CaptureQueueError):
    code = "CAPTURE_QUEUE_STATE"


class CaptureQueueWriteError(CaptureQueueError):
    code = "CAPTURE_QUEUE_WRITE_FAILED"


class CaptureQueueLockError(CaptureQueueError):
    code = "CAPTURE_QUEUE_LOCK_TIMEOUT"


@dataclass(frozen=True)
class CaptureQueueConfig:
    """Bounded local-delivery settings; no user-controlled runtime policy yet."""

    max_queued_jobs: int = 1000
    max_attempts: int = 3
    lease_seconds: int = 300
    lock_timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.max_queued_jobs <= 0:
            raise ValueError("max_queued_jobs must be positive")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if self.lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if self.lock_timeout_seconds <= 0:
            raise ValueError("lock_timeout_seconds must be positive")


@dataclass(frozen=True)
class QueueReceipt:
    """Content-safe acknowledgement returned by a queue operation."""

    job_id: str
    status: str
    duplicate: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"job_id": self.job_id, "status": self.status, "duplicate": self.duplicate}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise CaptureQueueCorruptError(f"{field} is missing from capture job")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CaptureQueueCorruptError(f"{field} is not an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise CaptureQueueCorruptError(f"{field} has no timezone")
    return parsed.astimezone(timezone.utc)


def _hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _job_id(idempotency_key: str) -> str:
    return JOB_PREFIX + hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:32]


def _atomic_write_json(path: Path, document: Mapping[str, Any]) -> None:
    """Write a queue document atomically and durably on its local filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        temporary_path = Path(temporary)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(document, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary_path.replace(path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                # Windows may not expose POSIX mode bits.  The local directory
                # remains gitignored and no path/content is written to the ledger.
                pass
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
    except OSError as exc:
        raise CaptureQueueWriteError("capture queue job could not be written") from exc


class CaptureQueue:
    """Atomic local spool with bounded retry and content-safe ledger records."""

    def __init__(self, vault_path: str | Path, *, config: Optional[CaptureQueueConfig] = None):
        self.vault_path = Path(vault_path)
        self.config = config or CaptureQueueConfig()
        self.root = self.vault_path / ".brain-eleven" / "capture"
        self.ledger_path = self.root / "capture-ledger.jsonl"
        self._lock_target = self.root / "queue-state"

    def _directory(self, status: str) -> Path:
        if status not in QUEUE_DIRECTORIES:
            raise CaptureQueueStateError("capture queue status is unsupported")
        return self.root / QUEUE_DIRECTORIES[status]

    def _job_path(self, status: str, job_id: str) -> Path:
        if not job_id.startswith(JOB_PREFIX):
            raise CaptureQueueStateError("capture queue job id is unsupported")
        return self._directory(status) / f"{job_id}.json"

    def job_path(self, job_id: str) -> Optional[Path]:
        """Return the current local job path, if one exists, without reading it."""
        for status in (QUEUED, CLAIMED, COMMITTED, DEAD_LETTER):
            candidate = self._job_path(status, job_id)
            if candidate.exists():
                return candidate
        return None

    def _ensure_layout(self) -> None:
        try:
            for directory in set(QUEUE_DIRECTORIES.values()):
                path = self.root / directory
                path.mkdir(parents=True, exist_ok=True)
                try:
                    os.chmod(path, 0o700)
                except OSError:
                    pass
        except OSError as exc:
            raise CaptureQueueWriteError("capture queue layout could not be created") from exc

    def _locked(self):
        try:
            return file_lock(self._lock_target, timeout=self.config.lock_timeout_seconds)
        except MemoryStoreLockTimeout as exc:
            raise CaptureQueueLockError("capture queue lock timed out") from exc

    def _ledger(self, *, action: str, job: Mapping[str, Any], error_code: Optional[str] = None) -> None:
        """Append only identifiers, hashes, state and counts; never evidence content."""
        event = job["event"]
        project = event["project"]
        record: dict[str, Any] = {
            "schema_version": CAPTURE_QUEUE_SCHEMA_VERSION,
            "recorded_at": _utc_now(),
            "action": action,
            "job_id": job["job_id"],
            "event_id": event["event_id"],
            "event_type": event["event_type"],
            "session_id_hash": _hash(event["session_id"]),
            "project_id": project["project_id"],
            "project_status": project["status"],
            "attempt": job["attempt"],
            "source_hash": _hash(event["event_id"]),
        }
        if error_code is not None:
            record["error_code"] = error_code
        try:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with self.ledger_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(self.ledger_path, 0o600)
            except OSError:
                pass
        except OSError as exc:
            raise CaptureQueueWriteError("capture queue ledger could not be written") from exc

    def _job_from_event(self, event: HookEvent, *, created_at: Optional[str] = None) -> dict[str, Any]:
        return {
            "schema_version": CAPTURE_QUEUE_SCHEMA_VERSION,
            "job_id": _job_id(event.idempotency_key),
            "idempotency_key": event.idempotency_key,
            "status": QUEUED,
            "attempt": 0,
            "created_at": created_at or _utc_now(),
            "event": event.to_dict(),
        }

    @staticmethod
    def _validate_event(event: Any) -> None:
        if not isinstance(event, Mapping):
            raise CaptureQueueCorruptError("capture job event is invalid")
        required = {"schema_version", "event_id", "idempotency_key", "event_type", "session_id", "project_root", "project", "event_at"}
        if not required.issubset(event):
            raise CaptureQueueCorruptError("capture job event is incomplete")
        if event.get("schema_version") != CAPTURE_EVENT_SCHEMA_VERSION:
            raise CaptureQueueCorruptError("capture job event schema is unsupported")
        if event.get("event_type") not in EVENT_TYPES:
            raise CaptureQueueCorruptError("capture job event type is unsupported")
        if not isinstance(event.get("session_id"), str) or not event["session_id"]:
            raise CaptureQueueCorruptError("capture job session identity is invalid")
        project = event.get("project")
        if not isinstance(project, Mapping) or "project_id" not in project or "status" not in project:
            raise CaptureQueueCorruptError("capture job project metadata is invalid")
        if "prompt" in event:
            prompt = event["prompt"]
            if not isinstance(prompt, Mapping) or not isinstance(prompt.get("sha256"), str):
                raise CaptureQueueCorruptError("capture job contains unsafe prompt content")
        for forbidden in ("raw_prompt", "prompt_content", "transcript_content", "content"):
            if forbidden in event:
                raise CaptureQueueCorruptError("capture job contains unsafe evidence content")

    def _read_job(self, path: Path) -> dict[str, Any]:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CaptureQueueCorruptError("capture queue job is unreadable") from exc
        if not isinstance(document, dict):
            raise CaptureQueueCorruptError("capture queue job must be an object")
        required = {"schema_version", "job_id", "idempotency_key", "status", "attempt", "created_at", "event"}
        if not required.issubset(document):
            raise CaptureQueueCorruptError("capture queue job is incomplete")
        if document["schema_version"] != CAPTURE_QUEUE_SCHEMA_VERSION:
            raise CaptureQueueCorruptError("capture queue schema is unsupported")
        if not isinstance(document["job_id"], str) or not document["job_id"].startswith(JOB_PREFIX):
            raise CaptureQueueCorruptError("capture queue job identity is invalid")
        if document["status"] not in JOB_STATUSES:
            raise CaptureQueueCorruptError("capture queue job state is unsupported")
        if not isinstance(document["attempt"], int) or isinstance(document["attempt"], bool) or document["attempt"] < 0:
            raise CaptureQueueCorruptError("capture queue attempt is invalid")
        _parse_utc(document["created_at"], field="created_at")
        self._validate_event(document["event"])
        return document

    def _move(self, source: Path, destination: Path) -> None:
        try:
            if destination.exists():
                raise CaptureQueueStateError("capture queue destination already exists")
            source.replace(destination)
        except CaptureQueueStateError:
            raise
        except OSError as exc:
            raise CaptureQueueWriteError("capture queue job could not change state") from exc

    def _existing_job(self, job_id: str) -> Optional[tuple[str, Path]]:
        for status in (QUEUED, CLAIMED, COMMITTED, DEAD_LETTER):
            candidate = self._job_path(status, job_id)
            if candidate.exists():
                return status, candidate
        return None

    def _queued_count(self) -> int:
        return sum(1 for path in self._directory(QUEUED).glob("*.json") if path.is_file())

    def enqueue(self, event: HookEvent) -> QueueReceipt:
        """Durably enqueue an event once; duplicate delivery is acknowledged safely."""
        self._ensure_layout()
        job = self._job_from_event(event)
        try:
            with self._locked():
                existing = self._existing_job(job["job_id"])
                if existing is not None:
                    status, path = existing
                    existing_job = self._read_job(path)
                    if existing_job["idempotency_key"] != event.idempotency_key:
                        raise CaptureQueueCorruptError("capture queue job identity collision")
                    self._ledger(action="DUPLICATE", job=existing_job)
                    return QueueReceipt(job_id=job["job_id"], status=status, duplicate=True)
                if self._queued_count() >= self.config.max_queued_jobs:
                    raise CaptureQueueFullError("capture queue is full")
                self._validate_event(job["event"])
                _atomic_write_json(self._job_path(QUEUED, job["job_id"]), job)
                self._ledger(action="ENQUEUED", job=job)
                return QueueReceipt(job_id=job["job_id"], status=QUEUED)
        except MemoryStoreLockTimeout as exc:
            raise CaptureQueueLockError("capture queue lock timed out") from exc

    def claim_next(self, *, now: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Atomically claim the oldest queued job for a future local worker."""
        self._ensure_layout()
        claimed_at = now or _utc_now()
        _parse_utc(claimed_at, field="claimed_at")
        try:
            with self._locked():
                for source in sorted(self._directory(QUEUED).glob("*.json")):
                    job = self._read_job(source)
                    # The directory is the durable delivery state.  A crash
                    # between a retry's rename and document rewrite can leave
                    # a prior processing value in a queued file; it is safe to
                    # claim again because no worker can see it in processing.
                    if job["status"] not in {QUEUED, CLAIMED, PROCESSING}:
                        raise CaptureQueueCorruptError("queued job has an invalid state")
                    destination = self._job_path(CLAIMED, job["job_id"])
                    job["status"] = CLAIMED
                    job["attempt"] += 1
                    job["claimed_at"] = claimed_at
                    self._move(source, destination)
                    _atomic_write_json(destination, job)
                    self._ledger(action="CLAIMED", job=job)
                    return job
        except MemoryStoreLockTimeout as exc:
            raise CaptureQueueLockError("capture queue lock timed out") from exc
        return None

    def start_processing(self, job_id: str) -> dict[str, Any]:
        self._ensure_layout()
        try:
            with self._locked():
                path = self._job_path(CLAIMED, job_id)
                if not path.exists():
                    raise CaptureQueueStateError("capture job is not claimed")
                job = self._read_job(path)
                if job["status"] != CLAIMED:
                    raise CaptureQueueStateError("capture job cannot enter processing")
                job["status"] = PROCESSING
                job["processing_at"] = _utc_now()
                _atomic_write_json(path, job)
                self._ledger(action="PROCESSING", job=job)
                return job
        except MemoryStoreLockTimeout as exc:
            raise CaptureQueueLockError("capture queue lock timed out") from exc

    def commit(self, job_id: str) -> QueueReceipt:
        """Mark a future worker's completed side-effect transaction as committed."""
        self._ensure_layout()
        try:
            with self._locked():
                source = self._job_path(CLAIMED, job_id)
                if not source.exists():
                    raise CaptureQueueStateError("capture job is not processing")
                job = self._read_job(source)
                if job["status"] not in {CLAIMED, PROCESSING}:
                    raise CaptureQueueStateError("capture job cannot be committed")
                destination = self._job_path(COMMITTED, job_id)
                self._move(source, destination)
                job["status"] = COMMITTED
                job["committed_at"] = _utc_now()
                _atomic_write_json(destination, job)
                self._ledger(action="COMMITTED", job=job)
                return QueueReceipt(job_id=job_id, status=COMMITTED)
        except MemoryStoreLockTimeout as exc:
            raise CaptureQueueLockError("capture queue lock timed out") from exc

    def retry_or_dead_letter(self, job_id: str, *, error_code: str) -> QueueReceipt:
        """Return a failed future worker job to delivery or retain it for review."""
        if not isinstance(error_code, str) or not error_code:
            raise CaptureQueueStateError("capture job retry requires an error code")
        self._ensure_layout()
        try:
            with self._locked():
                source = self._job_path(CLAIMED, job_id)
                if not source.exists():
                    raise CaptureQueueStateError("capture job is not processing")
                job = self._read_job(source)
                if job["status"] not in {CLAIMED, PROCESSING}:
                    raise CaptureQueueStateError("capture job cannot be retried")
                job["last_error_code"] = error_code
                if job["attempt"] >= self.config.max_attempts:
                    destination = self._job_path(DEAD_LETTER, job_id)
                    self._move(source, destination)
                    job["status"] = DEAD_LETTER
                    job["dead_lettered_at"] = _utc_now()
                    _atomic_write_json(destination, job)
                    self._ledger(action="DEAD_LETTER", job=job, error_code=error_code)
                    return QueueReceipt(job_id=job_id, status=DEAD_LETTER)
                destination = self._job_path(QUEUED, job_id)
                self._move(source, destination)
                job["status"] = QUEUED
                job["retry_enqueued_at"] = _utc_now()
                _atomic_write_json(destination, job)
                self._ledger(action="REQUEUED", job=job, error_code=error_code)
                return QueueReceipt(job_id=job_id, status=QUEUED)
        except MemoryStoreLockTimeout as exc:
            raise CaptureQueueLockError("capture queue lock timed out") from exc

    def recover_expired_claims(self, *, now: Optional[str] = None) -> int:
        """Recover jobs stranded by a worker crash after their explicit lease expires."""
        self._ensure_layout()
        current = _parse_utc(now or _utc_now(), field="recovery_at")
        recovered = 0
        try:
            with self._locked():
                for source in sorted(self._directory(CLAIMED).glob("*.json")):
                    job = self._read_job(source)
                    if job["status"] not in {CLAIMED, PROCESSING}:
                        raise CaptureQueueCorruptError("processing job has an invalid state")
                    claimed_at = _parse_utc(job.get("claimed_at"), field="claimed_at")
                    if current - claimed_at < timedelta(seconds=self.config.lease_seconds):
                        continue
                    job["last_error_code"] = "CAPTURE_LEASE_EXPIRED"
                    if job["attempt"] >= self.config.max_attempts:
                        destination = self._job_path(DEAD_LETTER, job["job_id"])
                        self._move(source, destination)
                        job["status"] = DEAD_LETTER
                        job["dead_lettered_at"] = current.isoformat().replace("+00:00", "Z")
                        _atomic_write_json(destination, job)
                        self._ledger(action="DEAD_LETTER", job=job, error_code="CAPTURE_LEASE_EXPIRED")
                    else:
                        destination = self._job_path(QUEUED, job["job_id"])
                        self._move(source, destination)
                        job["status"] = QUEUED
                        job["retry_enqueued_at"] = current.isoformat().replace("+00:00", "Z")
                        _atomic_write_json(destination, job)
                        self._ledger(action="RECOVERED", job=job, error_code="CAPTURE_LEASE_EXPIRED")
                    recovered += 1
        except MemoryStoreLockTimeout as exc:
            raise CaptureQueueLockError("capture queue lock timed out") from exc
        return recovered


def _bounded_stdin() -> bytes:
    raw = sys.stdin.buffer.read(MAX_HOOK_EVENT_BYTES + 1)
    if len(raw) > MAX_HOOK_EVENT_BYTES:
        raise CaptureEventError(f"hook event exceeds {MAX_HOOK_EVENT_BYTES} bytes")
    return raw


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Queue a bounded Brain-Eleven hook event")
    subparsers = parser.add_subparsers(dest="command", required=True)
    enqueue = subparsers.add_parser("enqueue-hook", help="normalize hook stdin and enqueue it")
    enqueue.add_argument("--vault", default=".", help="Brain-Eleven vault path")
    enqueue.add_argument("--event-type", required=True, choices=sorted(EVENT_TYPES))
    enqueue.add_argument("--project-root", required=True, help="trusted fallback project root from hook")
    arguments = parser.parse_args(argv)

    try:
        event = parse_native_hook_event_json(
            _bounded_stdin(),
            event_type=arguments.event_type,
            vault_path=arguments.vault,
            default_project_root=arguments.project_root,
        )
        receipt = CaptureQueue(arguments.vault).enqueue(event)
    except (CaptureEventError, CaptureQueueError) as exc:
        print(json.dumps({"error": {"code": exc.code}}))
        return 2
    print(json.dumps({"event_id": event.event_id, **receipt.to_dict()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
