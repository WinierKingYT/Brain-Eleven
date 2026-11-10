"""Content-safe evidence metadata and local source readers for PRE-03.

Evidence is an observed source, never a canonical memory.  Readers keep raw
message text in an in-memory batch only; the local store persists only stable
identity, hashes, role, time and source locator metadata.

Bounded native transcript adapters (``read_increment``/``previous_message``):
a recognised conversation record with an unknown role or content shape fails
visibly. A Claude record of an unrecognised *type* is skipped and counted, never
read as evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from brain_eleven.infrastructure.locking import MemoryStoreLockTimeout, file_lock

from .ownership import TranscriptBinding
from .storage import identity


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
ROLE_VALUES = frozenset({"user", "assistant", "tool", "system", "legacy", "summary", "subagent"})
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


def _meta_role_upgrade(prior, document) -> bool:
    """A record stored as 'user' before meta records became 'system' (2026-09-30).

    Same evidence, only the role differs: keep the stored metadata instead of
    failing the job, so a replay or backfill over old transcripts still runs.
    """
    if (isinstance(prior, dict) and prior.get("role") in {"user", "system"}
            and document.get("role") == "subagent"):
        # A subagent hand-back was stored as a meta ('system') record before
        # subagent reports got their own role (2026-10-13).
        return {**prior, "role": "subagent"} == document
    return (isinstance(prior, dict) and prior.get("role") == "user"
            and document.get("role") in {"system", "summary"}
            and {**prior, "role": document.get("role")} == document)


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
                        if prior != document and not _meta_role_upgrade(prior, document):
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


# Claude transcripts hold conversation records plus metadata records that never
# carry evidence. Newer clients keep adding metadata types, and rejecting a
# whole session for one of them dead-lettered every real session, so only the
# conversation types produce evidence and any other type is skipped and counted.
_CLAUDE_CONVERSATION_TYPES = frozenset({'user', 'assistant'})
_CLAUDE_METADATA_TYPES = frozenset({'system', 'progress', 'summary', 'file-history-snapshot', 'queue-operation',
                                    'last-prompt', 'custom-title', 'agent-name', 'agent-color'})
MAX_IGNORED_TYPE_NAMES = 32
_CODEX_METADATA_TYPES = frozenset({'session_meta', 'event_msg', 'turn_context', 'compacted'})
_CODEX_NON_MESSAGE_ITEMS = frozenset({'function_call', 'function_call_output', 'reasoning', 'custom_tool_call',
                                      'custom_tool_call_output', 'web_search_call', 'local_shell_call'})
_TYPE_NAME = re.compile(r'[A-Za-z0-9_-]{1,40}')


SUBAGENT_FINDINGS_HEADING = '### Brain-Eleven bulguları'


def _block_text(block):
    """Text of one content block, descending into a tool result's own content."""
    if not isinstance(block, dict):
        return ''
    if block.get('type') in {'text', 'input_text', 'output_text'} and isinstance(block.get('text'), str):
        return block['text']
    if block.get('type') == 'tool_result':
        inner = block.get('content')
        if isinstance(inner, str):
            return inner
        if isinstance(inner, list):
            return '\n'.join(_block_text(x) for x in inner)
    return ''


def subagent_report(content):
    """The report text when ``content`` carries a subagent findings section, else None."""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = '\n'.join(_block_text(x) for x in content)
    else:
        return None
    return text if SUBAGENT_FINDINGS_HEADING in text else None


def _count_ignored_type(counts, kind):
    """Count one unrecognised string record type by a bounded ASCII-identifier name."""
    name = kind if _TYPE_NAME.fullmatch(kind) else 'OTHER'
    if name != 'OTHER' and name not in counts and sum(1 for key in counts if key != 'OTHER') >= MAX_IGNORED_TYPE_NAMES:
        name = 'OTHER'
    counts[name] = counts.get(name, 0) + 1


def _parse_lines(vault, path, client, session, project, captured_at, complete, offset):
    """Parse complete transcript lines starting at byte ``offset`` into evidence messages."""
    messages = []
    position = offset
    records_seen = conversation_records = 0
    ignored_types = {}
    for line in complete.splitlines(keepends=True):
        start = position
        position += len(line)
        if not line.strip():
            continue
        doc = json.loads(line.decode('utf-8'))
        records_seen += 1
        role = content = None
        if client == 'codex':
            kind = doc.get('type')
            if not isinstance(kind, str):
                raise ValueError('UNSUPPORTED_CODEX_TRANSCRIPT')
            if kind == 'response_item':
                payload = doc.get('payload')
                item = payload.get('type') if isinstance(payload, dict) else None
                if not isinstance(item, str):
                    raise ValueError('UNSUPPORTED_CODEX_ITEM')
                if item == 'message':
                    conversation_records += 1
                    role, content = payload.get('role'), payload.get('content')
                elif item not in _CODEX_NON_MESSAGE_ITEMS:
                    # Newer Codex releases add item types; as with Claude, an
                    # unknown one is counted by name and never becomes evidence
                    # instead of dead-lettering the whole session.
                    _count_ignored_type(ignored_types, 'response_item-' + item)
                    continue
            elif kind not in _CODEX_METADATA_TYPES:
                _count_ignored_type(ignored_types, kind)
                continue
        elif client == 'claude':
            kind = doc.get('type')
            if not isinstance(kind, str):
                # Only a *string* type this reader does not know is tolerated as
                # newer metadata; a record with no usable type is malformed.
                raise ValueError('UNSUPPORTED_CLAUDE_TRANSCRIPT')
            if kind in _CLAUDE_CONVERSATION_TYPES:
                conversation_records += 1
                message = doc.get('message', {})
                role, content = message.get('role', kind), message.get('content')
                if role == 'user' and doc.get('isCompactSummary') is True:
                    # Owner decision 2026-09-30: a session summary is its own
                    # source (the main one), not the owner speaking.
                    role = 'summary'
                elif role == 'user' and doc.get('isMeta') is True:
                    # Claude Code writes injected text (skill bodies, subagent
                    # hand-backs, harness notes) as meta user records. It is
                    # kept as evidence but never counts as the user speaking:
                    # 2026-09-30 it was most of the review-queue noise.
                    role = 'system'
                if kind == 'user' and role in {'user', 'system'}:
                    report = subagent_report(content)
                    if report is not None:
                        # A subagent's report (a foreground tool result or a
                        # background hand-back) is never the owner speaking;
                        # only its findings section is captured, for review.
                        role, content = 'subagent', report
            elif kind not in _CLAUDE_METADATA_TYPES:
                # An unrecognised type never becomes evidence, even when it
                # carries a message-shaped field; it is only counted by name.
                _count_ignored_type(ignored_types, kind)
                continue
        else:
            raise ValueError('UNSUPPORTED_CLIENT')
        if role is None:
            continue
        if role not in {'user', 'assistant', 'system', 'developer', 'tool', 'summary', 'subagent'}:
            raise ValueError('UNSUPPORTED_MESSAGE_ROLE')
        if isinstance(content, list):
            # Tool results carried in a Claude user envelope are never treated
            # as user statements. Only native text blocks are eligible.
            content = '\n'.join(x['text'] for x in content if isinstance(x, dict) and x.get('type') in {'text', 'input_text', 'output_text'} and isinstance(x.get('text'), str))
        if not isinstance(content, str):
            raise ValueError('UNSUPPORTED_MESSAGE_CONTENT')
        if not content:
            continue
        timestamp = doc.get('timestamp')
        record = _record(source_type='SESSION_TRANSCRIPT', session_id=session, project_id=project,
                         captured_at=captured_at, occurred_at=EvidenceTime(timestamp, 'instant') if timestamp else None,
                         role='system' if role == 'developer' else role, source_path=path, content=content,
                         locator={'byte_start': start, 'byte_end': position, 'adapter': client + '-v1'})
        # First capture time is stable even when a later job retries a message.
        store = EvidenceStore(vault)
        prior_path = store.root / (record.evidence_id + '.json')
        if prior_path.exists():
            prior = json.loads(prior_path.read_text(encoding='utf-8'))
            record = replace(record, captured_at=prior['captured_at'])
        messages.append(EvidenceMessage(record, content))
        if len(messages) > 10000:
            raise ValueError('TRANSCRIPT_TOO_MANY_MESSAGES')
    return messages, records_seen, conversation_records, ignored_types


def _oversized_line(path, offset, head):
    """Bytes of the over-long line starting at ``offset`` through its newline, or b'' if unfinished."""
    parts = [head]
    with path.open('rb') as stream:
        stream.seek(offset + len(head))
        while True:
            chunk = stream.read(65536)
            if not chunk:
                return b''
            cut = chunk.find(b'\n')
            if cut >= 0:
                parts.append(chunk[:cut + 1])
                return b''.join(parts)
            parts.append(chunk)


def read_increment(vault, path, client, session, project, captured_at, cursor=None, *,
                   binding: TranscriptBinding | None = None, stats: dict | None = None):
    path = _safe_source_path(path)
    before = path.stat()
    if before.st_size > 128 * 1024 * 1024:
        raise ValueError('TRANSCRIPT_TOO_LARGE')
    if binding is not None:
        if path != binding.path:
            raise ValueError('TRANSCRIPT_CHANGED')
        if (int(getattr(before, 'st_dev', 0)), int(getattr(before, 'st_ino', 0)),
                int(before.st_size), int(getattr(before, 'st_mtime_ns', 0))) != binding.file_identity:
            raise ValueError('TRANSCRIPT_CHANGED')
    offset = (cursor or {}).get('offset', 0)
    if not isinstance(offset, int) or offset < 0 or offset > before.st_size:
        raise ValueError('TRANSCRIPT_REWRITTEN')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        opened_identity = (int(getattr(opened, 'st_dev', 0)), int(getattr(opened, 'st_ino', 0)),
                           int(opened.st_size), int(getattr(opened, 'st_mtime_ns', 0)))
        if binding is not None and opened_identity != binding.file_identity:
            raise ValueError('TRANSCRIPT_CHANGED')
        remaining = offset
        while remaining:
            chunk = stream.read(min(65536, remaining))
            if not chunk:
                raise ValueError('TRANSCRIPT_REWRITTEN')
            digest.update(chunk)
            remaining -= len(chunk)
        if cursor and digest.hexdigest() != cursor['prefix_hash']:
            raise ValueError('TRANSCRIPT_REWRITTEN')
        raw = stream.read(2 * 1024 * 1024)
        if binding is not None:
            # Hash the complete opened handle so an in-place, same-size
            # replacement cannot pass a path/stat-only check.
            # ``digest`` already contains the cursor prefix.  Hashing the
            # bytes after the prefix and comparing the full source below is
            # intentionally performed from this same handle.
            full_digest = hashlib.sha256()
            stream.seek(0)
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                full_digest.update(chunk)
            if full_digest.hexdigest() != binding.content_sha256:
                raise ValueError('TRANSCRIPT_CHANGED')
    after = path.stat()
    after_identity = (int(getattr(after, 'st_dev', 0)), int(getattr(after, 'st_ino', 0)),
                      int(after.st_size), int(getattr(after, 'st_mtime_ns', 0)))
    if binding is not None and after_identity != binding.file_identity:
        raise ValueError('TRANSCRIPT_CHANGED')
    if path.stat().st_size < before.st_size:
        raise ValueError('TRANSCRIPT_CHANGED')
    # A writer may append while we read; process complete lines only.
    end = raw.rfind(b'\n') + 1
    complete = raw[:end]
    if not end and len(raw) == 2 * 1024 * 1024:
        # One JSONL record over 2 MB (a huge tool output or attachment) used to
        # fail the whole transcript. Skip exactly that line, count it, and go on;
        # a line still being written (no newline yet) waits for the next read.
        skipped = _oversized_line(path, offset, raw)
        if stats is not None:
            stats.update(records_seen=0, conversation_records=0, ignored_record_types={},
                         oversized_lines=1 if skipped else 0)
        if not skipped:
            return EvidenceBatch((), ()), {'offset': offset, 'prefix_hash': digest.hexdigest(), 'has_more': False}
        digest.update(skipped)
        return EvidenceBatch((), ()), {'offset': offset + len(skipped), 'prefix_hash': digest.hexdigest(),
                                       'has_more': True}
    messages, records_seen, conversation_records, ignored_types = _parse_lines(
        vault, path, client, session, project, captured_at, complete, offset)
    digest.update(complete)
    if stats is not None:
        stats.update(records_seen=records_seen, conversation_records=conversation_records,
                     ignored_record_types=dict(ignored_types))
    return EvidenceBatch(tuple(x.record for x in messages), tuple(messages)), {'offset': offset + end, 'prefix_hash': digest.hexdigest(),
             'has_more': len(raw) == 2 * 1024 * 1024 and end > 0}


PREVIOUS_WINDOW = 256 * 1024


def previous_message(vault, path, client, session, project, captured_at, before_offset):
    """Return the conversation message that ends right before ``before_offset``, or None.

    Reads at most PREVIOUS_WINDOW bytes back so a short approval turn can be
    paired with the assistant proposal from the previous capture increment.
    Nothing is stored; evidence ids match the original read (absolute offsets).
    """
    path = _safe_source_path(path)
    if not isinstance(before_offset, int) or before_offset <= 0:
        return None
    start = max(0, before_offset - PREVIOUS_WINDOW)
    with path.open('rb') as stream:
        stream.seek(start)
        raw = stream.read(before_offset - start)
    if start:
        cut = raw.find(b'\n') + 1
        if not cut:
            return None
        raw, start = raw[cut:], start + cut
    try:
        messages = _parse_lines(vault, path, client, session, project, captured_at, raw, start)[0]
    except (ValueError, UnicodeDecodeError):
        return None
    return messages[-1] if messages else None


if __name__ == "__main__":
    raise SystemExit(main())
