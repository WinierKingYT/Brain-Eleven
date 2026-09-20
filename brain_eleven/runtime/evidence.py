"""Bounded native transcript adapters.

A recognised conversation record with an unknown role or content shape fails
visibly. A Claude record of an unrecognised *type* is skipped and counted, never
read as evidence.
"""
import json
import hashlib
import os
import re
from pathlib import Path
from dataclasses import replace
from brain_eleven._legacy import load_legacy_module
from .storage import identity
from .ownership import TranscriptBinding


_legacy_evidence = load_legacy_module("evidence", "evidence.py")
EvidenceBatch = _legacy_evidence.EvidenceBatch
EvidenceMessage = _legacy_evidence.EvidenceMessage
EvidenceTime = _legacy_evidence.EvidenceTime
EvidenceStore = _legacy_evidence.EvidenceStore
_record = _legacy_evidence._record
_safe_source_path = _legacy_evidence._safe_source_path


# Claude transcripts hold conversation records plus metadata records that never
# carry evidence. Newer clients keep adding metadata types, and rejecting a
# whole session for one of them dead-lettered every real session, so only the
# conversation types produce evidence and any other type is skipped and counted.
_CLAUDE_CONVERSATION_TYPES = frozenset({'user', 'assistant'})
_CLAUDE_METADATA_TYPES = frozenset({'system', 'progress', 'summary', 'file-history-snapshot', 'queue-operation',
                                    'last-prompt', 'custom-title', 'agent-name', 'agent-color'})
MAX_IGNORED_TYPE_NAMES = 32
_TYPE_NAME = re.compile(r'[A-Za-z0-9_-]{1,40}')


def _count_ignored_type(counts, kind):
    """Count one unrecognised record type by a bounded, content-free name."""
    name = kind if isinstance(kind, str) and _TYPE_NAME.fullmatch(kind) else 'OTHER'
    if name != 'OTHER' and name not in counts and sum(1 for key in counts if key != 'OTHER') >= MAX_IGNORED_TYPE_NAMES:
        name = 'OTHER'
    counts[name] = counts.get(name, 0) + 1


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
        raise ValueError('TRANSCRIPT_LINE_TOO_LARGE')
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
            if doc.get('type') == 'response_item':
                payload = doc.get('payload', {})
                if payload.get('type') == 'message':
                    conversation_records += 1
                    role, content = payload.get('role'), payload.get('content')
                elif payload.get('type') not in {'function_call', 'function_call_output', 'reasoning', 'custom_tool_call', 'custom_tool_call_output', 'web_search_call', 'local_shell_call'}:
                    raise ValueError('UNSUPPORTED_CODEX_ITEM')
            elif doc.get('type') not in {'session_meta', 'event_msg', 'turn_context', 'compacted'}:
                raise ValueError('UNSUPPORTED_CODEX_TRANSCRIPT')
        elif client == 'claude':
            kind = doc.get('type') if isinstance(doc.get('type'), str) else None
            if kind in _CLAUDE_CONVERSATION_TYPES:
                conversation_records += 1
                message = doc.get('message', {})
                role, content = message.get('role', kind), message.get('content')
            elif kind not in _CLAUDE_METADATA_TYPES:
                # An unrecognised type never becomes evidence, even when it
                # carries a message-shaped field; it is only counted by name.
                _count_ignored_type(ignored_types, doc.get('type'))
                continue
        else:
            raise ValueError('UNSUPPORTED_CLIENT')
        if role is None:
            continue
        if role not in {'user', 'assistant', 'system', 'developer', 'tool'}:
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
    digest.update(complete)
    if stats is not None:
        stats.update(records_seen=records_seen, conversation_records=conversation_records,
                     ignored_record_types=dict(ignored_types))
    return EvidenceBatch(tuple(x.record for x in messages), tuple(messages)), {'offset': offset + end, 'prefix_hash': digest.hexdigest(),
             'has_more': len(raw) == 2 * 1024 * 1024 and end > 0}
