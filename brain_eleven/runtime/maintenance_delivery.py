"""Durable, project-bound delivery of native post-session maintenance reports."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any, Mapping, Optional

from brain_eleven.infrastructure.locking import file_lock
from brain_eleven.memory import MemoryStore
from brain_eleven.state import StateStore

from .storage import identity, now, read_json, write_json


SCHEMA_VERSION = 1
QUEUED = "QUEUED"
PROCESSING = "PROCESSING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
_TERMINAL = {COMPLETED, FAILED}
_MAX_ATTEMPTS = 3
_LEASE_SECONDS = 300


class _LeaseLost(RuntimeError):
    """Raised when a worker no longer owns an intent lease."""


def _root(vault: str | Path) -> Path:
    return Path(vault) / ".brain-eleven" / "runtime" / "maintenance-delivery"


def _dirs(vault: str | Path) -> dict[str, Path]:
    root = _root(vault)
    return {status: root / status.lower() for status in (QUEUED, PROCESSING, COMPLETED, FAILED)}


def _ensure(vault: str | Path) -> dict[str, Path]:
    directories = _dirs(vault)
    for path in directories.values():
        path.mkdir(parents=True, exist_ok=True)
    for name in ("reports", "staging", "delivered"):
        (_root(vault) / name).mkdir(parents=True, exist_ok=True)
    return directories


def _project_id(job: Mapping[str, Any]) -> Optional[str]:
    project = job.get("event", {}).get("project", {})
    value = project.get("project_id") if isinstance(project, Mapping) else None
    return value if isinstance(value, str) and value else None


def _revisions(vault: str | Path, project_id: str) -> tuple[int, Optional[int]]:
    memory_revision = int(MemoryStore(vault).revision())
    state_revision = StateStore(vault).project_revision(project_id)
    return memory_revision, None if state_revision is None else int(state_revision)


def _intent_id(job: Mapping[str, Any], project_id: str) -> str:
    return identity("maintenance_", project_id, job.get("job_id"), job.get("event", {}).get("event_id"))


def _intent_path(directories: Mapping[str, Path], status: str, intent_id: str) -> Path:
    return directories[status] / (intent_id + ".json")


def _find(directories: Mapping[str, Path], intent_id: str) -> tuple[str, Path] | None:
    for status, directory in directories.items():
        path = _intent_path(directories, status, intent_id)
        if path.exists():
            return status, path
    return None


def enqueue(vault: str | Path, job: Mapping[str, Any], result: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """Create one intent after a verified native SessionEnd capture commit."""
    event = job.get("event", {})
    if event.get("event_type") != "SESSION_END" or result.get("status") != "PROCESSED":
        return None
    if result.get("effect_verified") is not True:
        return None
    project_id = _project_id(job)
    if not project_id:
        return None
    memory_revision, state_revision = _revisions(vault, project_id)
    directories = _ensure(vault)
    intent_id = _intent_id(job, project_id)
    record = {
        "schema_version": SCHEMA_VERSION,
        "intent_id": intent_id,
        "status": QUEUED,
        "attempt": 0,
        "created_at": now(),
        "project_id": project_id,
        "event_id_hash": hashlib.sha256(str(event.get("event_id", "")).encode()).hexdigest(),
        "job_id": str(job.get("job_id", "")),
        "source_memory_revision": memory_revision,
        "source_state_revision": state_revision,
    }
    with file_lock(_root(vault) / "index", timeout=.5):
        existing = _find(directories, intent_id)
        if existing:
            return read_json(existing[1])
        write_json(_intent_path(directories, QUEUED, intent_id), record)
    return record


def _safe_report(raw: Mapping[str, Any], intent: Mapping[str, Any], *, memory_revision: int,
                 state_revision: Optional[int]) -> dict[str, Any]:
    """Project maintenance output to counts/statuses; never persist content."""
    def count(value: Any) -> int:
        try:
            value = int(value)
        except (TypeError, ValueError, OverflowError):
            return 0
        return max(0, min(value, 1_000_000))

    graph = raw.get("graph", {}) if isinstance(raw.get("graph"), Mapping) else {}
    anomalies = raw.get("anomalies", {}) if isinstance(raw.get("anomalies"), Mapping) else {}
    digest = raw.get("digest", {}) if isinstance(raw.get("digest"), Mapping) else {}
    graph_data = graph.get("data", {}) if isinstance(graph.get("data"), Mapping) else {}
    graph_projection = graph_data.get("projection", {}) if isinstance(graph_data.get("projection"), Mapping) else {}
    anomaly_data = anomalies.get("data", {}) if isinstance(anomalies.get("data"), Mapping) else {}
    digest_data = digest.get("data", {}) if isinstance(digest.get("data"), Mapping) else {}
    severity = anomaly_data.get("by_severity", {})
    severity = severity if isinstance(severity, Mapping) else {}
    bounded_severity = {
        name: count(severity.get(name, 0))
        for name in ("critical", "error", "warning", "info")
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "SUCCESS" if all(x.get("ok") for x in (graph, anomalies, digest)) else "DEGRADED",
        "report_id": identity("maintenance_report_", intent["intent_id"], memory_revision, state_revision),
        "generated_at": now(),
        "intent_id": intent["intent_id"],
        "event_id_hash": intent.get("event_id_hash"),
        "project_id": intent["project_id"],
        "source_memory_revision": memory_revision,
        "source_state_revision": state_revision,
        "source_graph_revision": graph_projection.get("source_memory_revision"),
        "graph": {"ok": bool(graph.get("ok")), "status": "rebuilt" if graph.get("ok") else "failed"},
        "anomalies": {
            "ok": bool(anomalies.get("ok")),
            "total_memories_scanned": count(anomaly_data.get("total_memories_scanned", 0)),
            "total_anomalies": count(anomaly_data.get("total_anomalies", 0)),
            "by_severity": bounded_severity,
        },
        "digest": {
            "ok": bool(digest.get("ok")),
            "total_memories_considered": count(digest_data.get("total_memories_considered", 0)),
            "total_after_dedup": count(digest_data.get("total_after_dedup", 0)),
        },
        "surface_at_next_session": bool(raw.get("surface_at_next_session")),
    }


def _error_code(exc: Exception) -> str:
    value = getattr(exc, "code", None)
    if isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", value):
        return value
    return "MAINTENANCE_FAILED"


def _published_report(path: Path, intent: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """Return a valid atomically published report, without exposing parse errors."""
    try:
        report = read_json(path)
    except (OSError, TypeError, ValueError):
        return None
    if not isinstance(report, dict):
        return None
    if not _valid_report(report, intent=intent):
        return None
    return report


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _bounded_count(value: Any) -> bool:
    return _nonnegative_int(value) and value <= 1_000_000


def _valid_report(report: Any, *, intent: Optional[Mapping[str, Any]] = None,
                  project_id: Optional[str] = None, memory_revision: Optional[int] = None,
                  state_revision: Optional[int] = None, require_success: bool = False) -> bool:
    """Validate the content-free report envelope before it can be surfaced."""
    if not isinstance(report, dict) or report.get("schema_version") != SCHEMA_VERSION:
        return False
    if not isinstance(report.get("report_id"), str) or not re.fullmatch(
            r"maintenance_report_[0-9a-f]{64}", report["report_id"]):
        return False
    if not isinstance(report.get("intent_id"), str) or not re.fullmatch(
            r"maintenance_[0-9a-f]{64}", report["intent_id"]):
        return False
    if not isinstance(report.get("event_id_hash"), str) or not re.fullmatch(r"[0-9a-f]{64}", report["event_id_hash"]):
        return False
    if not isinstance(report.get("project_id"), str) or not report["project_id"]:
        return False
    if project_id is not None and report["project_id"] != project_id:
        return False
    status = report.get("status")
    if status not in {"SUCCESS", "DEGRADED"} or (require_success and status != "SUCCESS"):
        return False
    source_memory = report.get("source_memory_revision")
    source_state = report.get("source_state_revision")
    source_graph = report.get("source_graph_revision")
    if not _nonnegative_int(source_memory) or source_state is not None and not _nonnegative_int(source_state):
        return False
    if not _nonnegative_int(source_graph) or source_graph != source_memory:
        return False
    if memory_revision is not None and source_memory != memory_revision:
        return False
    if state_revision is not None and source_state != state_revision:
        return False
    if intent is not None:
        if report.get("intent_id") != intent.get("intent_id"):
            return False
        if report.get("project_id") != intent.get("project_id"):
            return False
        if source_memory != intent.get("source_memory_revision"):
            return False
        if source_state != intent.get("source_state_revision"):
            return False
    graph = report.get("graph")
    anomalies = report.get("anomalies")
    digest = report.get("digest")
    if not isinstance(graph, dict) or not isinstance(anomalies, dict) or not isinstance(digest, dict):
        return False
    if not isinstance(graph.get("ok"), bool) or graph.get("status") not in {"rebuilt", "failed"}:
        return False
    if not isinstance(anomalies.get("ok"), bool) or not _bounded_count(anomalies.get("total_memories_scanned")):
        return False
    if not _bounded_count(anomalies.get("total_anomalies")):
        return False
    severity = anomalies.get("by_severity")
    if not isinstance(severity, dict) or set(severity) != {"critical", "error", "warning", "info"}:
        return False
    if not all(_bounded_count(value) for value in severity.values()):
        return False
    if not isinstance(digest.get("ok"), bool):
        return False
    if not _bounded_count(digest.get("total_memories_considered")) or not _bounded_count(digest.get("total_after_dedup")):
        return False
    if status == "SUCCESS" and not (graph["ok"] and anomalies["ok"] and digest["ok"] and graph["status"] == "rebuilt"):
        return False
    return isinstance(report.get("surface_at_next_session"), bool)


def _lease_active(intent: Mapping[str, Any]) -> bool:
    value = intent.get("lease_expires_at")
    try:
        return math.isfinite(float(value)) and float(value) > time.time()
    except (TypeError, ValueError, OverflowError):
        return False


def _owned_path(directories: Mapping[str, Path], intent_id: str, owner: str) -> Path:
    current = _find(directories, intent_id)
    if not current:
        raise _LeaseLost("MAINTENANCE_LEASE_LOST")
    current_intent = read_json(current[1])
    if (not isinstance(current_intent, dict) or current_intent.get("status") != PROCESSING or
            current_intent.get("lease_owner") != owner or not _lease_active(current_intent)):
        raise _LeaseLost("MAINTENANCE_LEASE_LOST")
    return current[1]


def _owned_write(vault: str | Path, directories: Mapping[str, Path], intent_id: str,
                 owner: str, path: Path, value: Mapping[str, Any]) -> None:
    with file_lock(_root(vault) / "index", timeout=.5):
        _owned_path(directories, intent_id, owner)
        write_json(path, value)


def _owned_finalize(vault: str | Path, directories: Mapping[str, Path], intent: dict[str, Any],
                    owner: str, claimed_path: Path, *, report_path: Optional[Path] = None,
                    report: Optional[Mapping[str, Any]] = None,
                    staged_path: Optional[Path] = None) -> None:
    with file_lock(_root(vault) / "index", timeout=.5):
        _owned_path(directories, intent["intent_id"], owner)
        if report_path is not None and report is not None:
            write_json(report_path, report)
        write_json(_intent_path(directories, COMPLETED, intent["intent_id"]), intent)
        if staged_path is not None:
            staged_path.unlink(missing_ok=True)
        claimed_path.unlink(missing_ok=True)


def _owned_failure(vault: str | Path, directories: Mapping[str, Path], intent: dict[str, Any],
                   owner: str, claimed_path: Path) -> bool:
    with file_lock(_root(vault) / "index", timeout=.5):
        try:
            _owned_path(directories, intent["intent_id"], owner)
        except _LeaseLost:
            return False
        destination = _intent_path(directories, intent["status"], intent["intent_id"])
        write_json(destination, intent)
        if destination != claimed_path:
            claimed_path.unlink(missing_ok=True)
        return True


def _stage_path(vault: str | Path, intent_id: str) -> Path:
    return _root(vault) / "staging" / (intent_id + ".json")


def _delivery_path(vault: str | Path, project_id: str, report_id: str, delivery_key: str) -> Path:
    delivery_id = identity("maintenance_delivery_", project_id, report_id, delivery_key)
    return _root(vault) / "delivered" / (delivery_id + ".json")


def reconcile_completed(vault: str | Path, *, limit: int = 16) -> int:
    """Recreate intents for committed SessionEnd jobs if enqueue was interrupted."""
    if limit <= 0:
        return 0
    scheduled = 0
    completed = Path(vault) / ".brain-eleven" / "capture" / "completed"
    for path in sorted(completed.glob("*.json")):
        if scheduled >= limit:
            break
        try:
            job = read_json(path)
            event = job.get("event", {}) if isinstance(job, dict) else {}
            project_id = _project_id(job) if isinstance(job, dict) else None
            if event.get("event_type") != "SESSION_END" or not project_id:
                continue
            directories = _ensure(vault)
            intent_id = _intent_id(job, project_id)
            if _find(directories, intent_id):
                continue
            from .worker import Worker
            receipt = Worker(vault)._read_receipt(job)
            result = {
                "status": "PROCESSED",
                "effect_verified": True,
                "canonical_effect_count": receipt.get("canonical_effect_count", 0),
            }
            if enqueue(vault, job, result):
                scheduled += 1
        except (OSError, TypeError, ValueError, KeyError, RuntimeError):
            # A malformed/unfinished capture remains visible to the normal
            # capture reconciliation path; never persist its source content.
            continue
    return scheduled


def process_pending(vault: str | Path, *, limit: int = 1) -> int:
    """Process a bounded number of queued intents; safe to call repeatedly."""
    if limit <= 0:
        return 0
    reconcile_completed(vault, limit=max(limit, 1))
    directories = _ensure(vault)
    candidates = []
    for status in (QUEUED, PROCESSING):
        candidates.extend(sorted(directories[status].glob("*.json")))
    processed = 0
    for path in candidates[:max(0, limit)]:
        intent = read_json(path)
        if not isinstance(intent, dict) or intent.get("schema_version") != SCHEMA_VERSION:
            continue
        intent_id = intent.get("intent_id")
        if not isinstance(intent_id, str):
            continue
        claimed_path = path
        with file_lock(_root(vault) / "index", timeout=.5):
            current = _find(directories, intent_id)
            if not current or current[0] not in {QUEUED, PROCESSING}:
                continue
            intent = read_json(current[1])
            if not isinstance(intent, dict):
                continue
            if intent.get("status") == PROCESSING and _lease_active(intent):
                continue
            claimed_path = current[1]
            intent["status"] = PROCESSING
            intent["attempt"] = int(intent.get("attempt", 0)) + 1
            intent["started_at"] = now()
            intent["lease_owner"] = identity("maintenance_worker_", os.getpid(), time.time_ns())
            intent["lease_expires_at"] = time.time() + _LEASE_SECONDS
            # Persist the lease in the existing location before any derived
            # work.  A crash leaves a recoverable PROCESSING record instead
            # of a disappearing queued document.
            write_json(claimed_path, intent)
        owner = intent["lease_owner"]
        try:
            report_path = _root(vault) / "reports" / (intent_id + ".json")
            published = _published_report(report_path, intent)
            if published is not None:
                # A crash after atomic report publication but before the
                # terminal intent move must not rerun derived work.
                intent.update({"status": COMPLETED, "completed_at": now(),
                               "report_path": str(report_path.name)})
                _owned_finalize(vault, directories, intent, owner, claimed_path)
                processed += 1
                continue
            staged_path = _stage_path(vault, intent_id)
            staged = _published_report(staged_path, intent)
            if staged is not None:
                # A crash between staging and public report replacement is
                # recoverable without rerunning graph/anomaly/digest work.
                intent.update({"status": COMPLETED, "completed_at": now(),
                               "report_path": str(report_path.name)})
                _owned_finalize(vault, directories, intent, owner, claimed_path,
                                report_path=report_path, report=staged, staged_path=staged_path)
                processed += 1
                continue
            from .maintenance import run_maintenance
            raw = run_maintenance(vault, generated_by_run=intent_id, project_id=intent["project_id"])
            current_memory, current_state = _revisions(vault, intent["project_id"])
            if (current_memory != intent.get("source_memory_revision") or
                    current_state != intent.get("source_state_revision")):
                raise RuntimeError("MAINTENANCE_SOURCE_CHANGED")
            report = _safe_report(raw, intent, memory_revision=current_memory, state_revision=current_state)
            if report.get("source_graph_revision") != current_memory:
                raise RuntimeError("MAINTENANCE_GRAPH_STALE")
            _owned_write(vault, directories, intent_id, owner, staged_path, report)
            intent.update({"status": COMPLETED, "completed_at": now(), "report_path": str(report_path.name)})
            _owned_finalize(vault, directories, intent, owner, claimed_path,
                            report_path=report_path, report=report, staged_path=staged_path)
            processed += 1
        except _LeaseLost:
            # A recovered worker owns the intent now; never overwrite its
            # report or failure state with this stale worker's result.
            continue
        except Exception as exc:
            attempts = int(intent.get("attempt", 1))
            intent.update({"status": FAILED if attempts >= _MAX_ATTEMPTS else QUEUED,
                           "error_code": _error_code(exc), "finished_at": now()})
            owned = _owned_failure(vault, directories, intent, owner, claimed_path)
            if owned and intent["status"] == FAILED:
                processed += 1
    return processed


def latest_reminder(vault: str | Path, project_id: str, *, budget: int = 600,
                    delivery_key: Optional[str] = None) -> dict[str, Any]:
    """Return a bounded reminder only for a current project/revision report."""
    directories = _ensure(vault)
    reports = sorted((_root(vault) / "reports").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    current_memory, current_state = _revisions(vault, project_id)
    for path in reports:
        try:
            report = read_json(path)
        except (OSError, TypeError, ValueError):
            continue
        if not _valid_report(report, project_id=project_id, memory_revision=current_memory,
                             state_revision=current_state, require_success=True):
            continue
        if report.get("surface_at_next_session") is not True:
            continue
        anomalies = report.get("anomalies", {})
        digest = report.get("digest", {})
        text = (f"Maintenance report: {anomalies.get('total_anomalies', 0)} anomalies; "
                f"{digest.get('total_after_dedup', 0)} recent memories after dedup.")
        if len(text.encode("utf-8")) > budget:
            text = text.encode("utf-8")[:budget].decode("utf-8", "ignore")
        report_id = report.get("report_id")
        if isinstance(delivery_key, str) and delivery_key:
            if _delivery_path(vault, project_id, report_id, delivery_key).exists():
                return {"status": "ALREADY_DELIVERED", "context": "", "report_id": report_id,
                        "project_id": project_id}
        return {"status": "FRESH", "context": text, "report_id": report_id, "project_id": project_id}
    return {"status": "STALE_OR_MISSING", "context": "", "project_id": project_id}


def ack_reminder(vault: str | Path, project_id: str, report_id: str, delivery_key: str) -> bool:
    """Record one content-free SessionStart delivery receipt."""
    if not all(isinstance(value, str) and value for value in (project_id, report_id, delivery_key)):
        return False
    path = _delivery_path(vault, project_id, report_id, delivery_key)
    with file_lock(_root(vault) / "delivery", timeout=.5):
        if path.exists():
            return False
        write_json(path, {
            "schema_version": SCHEMA_VERSION,
            "delivery_id": path.stem,
            "project_id": project_id,
            "report_id": report_id,
            "session_hash": identity("session_", delivery_key),
            "delivered_at": now(),
        })
    return True


__all__ = ["SCHEMA_VERSION", "ack_reminder", "enqueue", "latest_reminder",
           "process_pending", "reconcile_completed"]
