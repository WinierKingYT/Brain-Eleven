#!/usr/bin/env python3
"""Content-safe evidence metadata and local source readers for PRE-03.

Evidence is an observed source, never a canonical memory.  Readers keep raw
message text in an in-memory batch only; the local store persists only stable
identity, hashes, role, time and source locator metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from memory_store_lock import MemoryStoreLockTimeout, file_lock


EVIDENCE_SCHEMA_VERSION = 1
SOURCE_SESSION_TRANSCRIPT = "SESSION_TRANSCRIPT"
SOURCE_DAILY_NOTE = "DAILY_NOTE"
SOURCE_USER_PROMPT = "USER_PROMPT"
SOURCE_MANUAL_REMEMBER = "MANUAL_REMEMBER"
SOURCE_TOOL_RESULT = "TOOL_RESULT"
SOURCE_SYSTEM_EVENT = "SYSTEM_EVENT"
SOURCE_MIGRATED_LEGACY_NOTE = "MIGRATED_LEGACY_NOTE"
SOURCE_TYPES = frozenset(
    {
        SOURCE_SESSION_TRANSCRIPT,
        SOURCE_DAILY_NOTE,
        SOURCE_USER_PROMPT,
        SOURCE_MANUAL_REMEMBER,
        SOURCE_TOOL_RESULT,
        SOURCE_SYSTEM_EVENT,
        SOURCE_MIGRATED_LEGACY_NOTE,
    }
)
ROLE_VALUES = frozenset({"user", "assistant", "tool", "system", "legacy"})
MAX_TRANSCRIPT_BYTES = 2 * 1024 * 1024
MAX_TRANSCRIPT_MESSAGES = 10_000
_DAILY_HEADING = re.compile(r"^# Daily Notes - (\d{4}-\d{2}-\d{2})\s*$")


class EvidenceError(ValueError):
    code = "EVIDENCE_INVALID"


class EvidencePathError(EvidenceError):
    code = "TRANSCRIPT_INVALID"


class EvidenceMissingError(EvidenceError):
    code = "TRANSCRIPT_NOT_FOUND"


class EvidenceCorruptError(EvidenceError):
    code = "EVIDENCE_CORRUPT"


class EvidenceStoreError(EvidenceError):
    code = "EVIDENCE_STORE_FAILED"


class EvidenceStoreLockError(EvidenceStoreError):
    code = "EVIDENCE_STORE_LOCK_TIMEOUT"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _parse_instant(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"{field} must be a timezone-aware ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError(f"{field} must be a timezone-aware ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise EvidenceError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class EvidenceTime:
    """Observed time without inventing precision not present in the source."""

    value: str
    precision: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    source_type: str
    session_id: Optional[str]
    project_id: Optional[str]
    captured_at: str
    occurred_at: Optional[EvidenceTime]
    role: str
    source: dict[str, Any]
    retention: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Render only durable metadata; never raw prompt/transcript text."""
        payload = asdict(self)
        payload["schema_version"] = EVIDENCE_SCHEMA_VERSION
        return payload


@dataclass(frozen=True)
class EvidenceMessage:
    """Ephemeral source text associated with a content-safe EvidenceRecord."""

    record: EvidenceRecord
    content: str


@dataclass(frozen=True)
class EvidenceBatch:
    """In-memory reader result. Only ``records`` may be persisted by V1."""

    records: tuple[EvidenceRecord, ...]
    messages: tuple[EvidenceMessage, ...]


def _record(
    *,
    source_type: str,
    session_id: Optional[str],
    project_id: Optional[str],
    captured_at: str,
    occurred_at: Optional[EvidenceTime],
    role: str,
    source_path: Path,
    content: str,
    locator: Mapping[str, Any],
) -> EvidenceRecord:
    if source_type not in SOURCE_TYPES or role not in ROLE_VALUES:
        raise EvidenceError("evidence source type or role is unsupported")
    content_hash = _hash(content)
    path_hash = _hash(str(source_path))
    identity = "|".join(
        [source_type, session_id or "", project_id or "", content_hash, json.dumps(locator, sort_keys=True)]
    )
    return EvidenceRecord(
        evidence_id="evd_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32],
        source_type=source_type,
        session_id=session_id,
        project_id=project_id,
        captured_at=_parse_instant(captured_at, field="captured_at"),
        occurred_at=occurred_at,
        role=role,
        source={"path_hash": path_hash, "content_hash": content_hash, "locator": dict(locator)},
        retention={"raw_retained": False, "expires_at": None},
    )


def _safe_source_path(source_path: str | Path) -> Path:
    original = Path(source_path).expanduser()
    if not original.is_absolute() or ".." in original.parts:
        raise EvidencePathError("evidence path must be an absolute local path")
    if original.is_symlink():
        raise EvidencePathError("evidence path must not be a symbolic link")
    try:
        resolved = original.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise EvidenceMissingError("evidence source is unavailable") from exc
    if not resolved.is_file():
        raise EvidencePathError("evidence source must be a regular file")
    return resolved


def _read_bounded_utf8(path: Path, *, maximum_bytes: int) -> str:
    try:
        before = path.stat().st_size
        if before > maximum_bytes:
            raise EvidencePathError("evidence source exceeds the configured size limit")
        with path.open("rb") as handle:
            raw = handle.read(maximum_bytes + 1)
        after = path.stat().st_size
    except OSError as exc:
        raise EvidenceMissingError("evidence source is unavailable") from exc
    if len(raw) > maximum_bytes or before != after or len(raw) != after:
        raise EvidencePathError("evidence source changed or exceeded its size limit while reading")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceCorruptError("evidence source is not UTF-8") from exc


def _role(document: Mapping[str, Any]) -> Optional[str]:
    value = document.get("role", document.get("type"))
    if not isinstance(value, str):
        return None
    aliases = {"human": "user", "claude": "assistant", "chatgpt": "assistant"}
    normalized = aliases.get(value.lower(), value.lower())
    return normalized if normalized in ROLE_VALUES - {"legacy"} else None


def _message_content(document: Mapping[str, Any]) -> Optional[str]:
    container = document.get("message", document)
    if not isinstance(container, Mapping):
        return None
    value = container.get("content", document.get("content"))
    if isinstance(value, str) and value:
        return value
    if isinstance(value, list):
        fragments = [item.get("text") for item in value if isinstance(item, Mapping) and isinstance(item.get("text"), str)]
        return "\n".join(fragments) if fragments else None
    return None


class TranscriptReader:
    """Read a bounded JSONL transcript while preserving trusted source roles."""

    def __init__(self, *, maximum_bytes: int = MAX_TRANSCRIPT_BYTES, maximum_messages: int = MAX_TRANSCRIPT_MESSAGES):
        self.maximum_bytes = maximum_bytes
        self.maximum_messages = maximum_messages

    def read(
        self,
        transcript_path: str | Path,
        *,
        session_id: str,
        project_id: Optional[str],
        captured_at: Optional[str] = None,
    ) -> EvidenceBatch:
        if not isinstance(session_id, str) or not session_id:
            raise EvidenceError("session_id is required for transcript evidence")
        path = _safe_source_path(transcript_path)
        text = _read_bounded_utf8(path, maximum_bytes=self.maximum_bytes)
        captured = captured_at or _utc_now()
        records: list[EvidenceRecord] = []
        messages: list[EvidenceMessage] = []
        for index, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                document = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvidenceCorruptError("transcript contains invalid JSONL") from exc
            if not isinstance(document, Mapping):
                raise EvidenceCorruptError("transcript event must be an object")
            role = _role(document)
            content = _message_content(document)
            if role is None or content is None:
                continue
            if len(messages) >= self.maximum_messages:
                raise EvidencePathError("transcript exceeds the configured message limit")
            timestamp = document.get("timestamp", document.get("created_at"))
            occurred = EvidenceTime(_parse_instant(timestamp, field="transcript timestamp"), "instant") if timestamp else None
            record = _record(
                source_type=SOURCE_SESSION_TRANSCRIPT,
                session_id=session_id,
                project_id=project_id,
                captured_at=captured,
                occurred_at=occurred,
                role=role,
                source_path=path,
                content=content,
                locator={"message_start": index, "message_end": index},
            )
            records.append(record)
            messages.append(EvidenceMessage(record=record, content=content))
        if not records:
            raise EvidenceCorruptError("transcript contains no supported role-aware messages")
        return EvidenceBatch(records=tuple(records), messages=tuple(messages))


class DailyEvidenceAdapter:
    """Legacy/manual Daily.md adapter; it does not perform memory extraction."""

    def read(
        self,
        daily_path: str | Path,
        *,
        project_id: Optional[str],
        captured_at: Optional[str] = None,
    ) -> EvidenceBatch:
        path = _safe_source_path(daily_path)
        text = _read_bounded_utf8(path, maximum_bytes=MAX_TRANSCRIPT_BYTES)
        captured = captured_at or _utc_now()
        lines = text.splitlines()
        headings = [(index, match.group(1)) for index, line in enumerate(lines) if (match := _DAILY_HEADING.match(line))]
        records: list[EvidenceRecord] = []
        messages: list[EvidenceMessage] = []
        for position, (start, date) in enumerate(headings):
            end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
            content = "\n".join(lines[start + 1 : end]).strip()
            if not content:
                continue
            record = _record(
                source_type=SOURCE_DAILY_NOTE,
                session_id=None,
                project_id=project_id,
                captured_at=captured,
                occurred_at=EvidenceTime(date, "day"),
                role="legacy",
                source_path=path,
                content=content,
                locator={"date": date, "line_start": start + 2, "line_end": end},
            )
            records.append(record)
            messages.append(EvidenceMessage(record=record, content=content))
        if not records:
            raise EvidenceCorruptError("Daily evidence contains no dated entries")
        return EvidenceBatch(records=tuple(records), messages=tuple(messages))


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
        raise EvidenceStoreError("evidence metadata could not be written") from exc


class EvidenceStore:
    """Idempotent local metadata store with default zero-day raw retention."""

    def __init__(self, vault_path: str | Path):
        self.root = Path(vault_path) / ".brain-eleven" / "capture" / "evidence"
        self._lock_target = self.root / "evidence-store"

    def persist(self, records: Sequence[EvidenceRecord]) -> tuple[EvidenceRecord, ...]:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            with file_lock(self._lock_target):
                for record in records:
                    document = record.to_dict()
                    path = self.root / f"{record.evidence_id}.json"
                    if path.exists():
                        try:
                            prior = json.loads(path.read_text(encoding="utf-8"))
                        except (OSError, json.JSONDecodeError) as exc:
                            raise EvidenceCorruptError("persisted evidence metadata is unreadable") from exc
                        if prior != document:
                            raise EvidenceCorruptError("evidence identity does not match existing metadata")
                        continue
                    _atomic_write(path, document)
        except MemoryStoreLockTimeout as exc:
            raise EvidenceStoreLockError("evidence metadata lock timed out") from exc
        return tuple(records)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Read and persist content-safe Brain-Eleven evidence metadata")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--transcript", help="absolute JSONL transcript path")
    parser.add_argument("--daily", help="absolute Daily.md path")
    parser.add_argument("--session-id")
    parser.add_argument("--project-id")
    parser.add_argument("--captured-at")
    arguments = parser.parse_args(argv)
    try:
        if bool(arguments.transcript) == bool(arguments.daily):
            raise EvidenceError("provide exactly one of --transcript or --daily")
        if arguments.transcript:
            batch = TranscriptReader().read(
                arguments.transcript,
                session_id=arguments.session_id or "",
                project_id=arguments.project_id,
                captured_at=arguments.captured_at,
            )
        else:
            batch = DailyEvidenceAdapter().read(
                arguments.daily,
                project_id=arguments.project_id,
                captured_at=arguments.captured_at,
            )
        EvidenceStore(arguments.vault).persist(batch.records)
    except EvidenceError as exc:
        print(json.dumps({"error": {"code": exc.code}}))
        return 2
    print(json.dumps({"evidence_ids": [record.evidence_id for record in batch.records]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
