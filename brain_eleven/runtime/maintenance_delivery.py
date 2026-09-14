"""Durable, project-bound delivery of native post-session maintenance reports."""

from __future__ import annotations

import hashlib
import json
import re
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
    if report.get("schema_version") != SCHEMA_VERSION:
        return None
    if report.get("intent_id") != intent.get("intent_id"):
        return None
    if report.get("project_id") != intent.get("project_id"):
        return None
    if report.get("status") not in {"SUCCESS", "DEGRADED"}:
        return None
    if report.get("source_memory_revision") != intent.get("source_memory_revision"):
        return None
    if report.get("source_state_revision") != intent.get("source_state_revision"):
        return None
    if report.get("source_graph_revision") != intent.get("source_memory_revision"):
        return None
    return report


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
    for path in sorted(completed.glob("*.json"))[:limit]:
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
        processing = _intent_path(directories, PROCESSING, intent_id)
        with file_lock(_root(vault) / "index", timeout=.5):
            current = _find(directories, intent_id)
            if not current or current[0] not in {QUEUED, PROCESSING}:
                continue
            intent = read_json(current[1])
            if not isinstance(intent, dict):
                continue
            if current[1] != processing:
                current[1].replace(processing)
            intent["status"] = PROCESSING
            intent["attempt"] = int(intent.get("attempt", 0)) + 1
            intent["started_at"] = now()
            write_json(processing, intent)
        try:
            report_path = _root(vault) / "reports" / (intent_id + ".json")
            published = _published_report(report_path, intent)
            if published is not None:
                # A crash after atomic report publication but before the
                # terminal intent move must not rerun derived work.
                intent.update({"status": COMPLETED, "completed_at": now(),
                               "report_path": str(report_path.name)})
                write_json(_intent_path(directories, COMPLETED, intent_id), intent)
                processing.unlink(missing_ok=True)
                processed += 1
                continue
            staged_path = _stage_path(vault, intent_id)
            staged = _published_report(staged_path, intent)
            if staged is not None:
                # A crash between staging and public report replacement is
                # recoverable without rerunning graph/anomaly/digest work.
                write_json(report_path, staged)
                intent.update({"status": COMPLETED, "completed_at": now(),
                               "report_path": str(report_path.name)})
                write_json(_intent_path(directories, COMPLETED, intent_id), intent)
                staged_path.unlink(missing_ok=True)
                processing.unlink(missing_ok=True)
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
            write_json(staged_path, report)
            write_json(report_path, report)
            intent.update({"status": COMPLETED, "completed_at": now(), "report_path": str(report_path.name)})
            write_json(_intent_path(directories, COMPLETED, intent_id), intent)
            staged_path.unlink(missing_ok=True)
            processing.unlink(missing_ok=True)
            processed += 1
        except Exception as exc:
            attempts = int(intent.get("attempt", 1))
            intent.update({"status": FAILED if attempts >= _MAX_ATTEMPTS else QUEUED,
                           "error_code": _error_code(exc), "finished_at": now()})
            destination = _intent_path(directories, intent["status"], intent_id)
            write_json(destination, intent)
            processing.unlink(missing_ok=True)
            if intent["status"] == FAILED:
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
        if not isinstance(report, dict) or report.get("status") != "SUCCESS" or report.get("project_id") != project_id:
            continue
        if report.get("source_memory_revision") != current_memory or report.get("source_state_revision") != current_state:
            continue
        if report.get("source_graph_revision") != current_memory:
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
