"""Bounded native transcript adapters. Unknown message shapes fail visibly."""
import json
import hashlib
from pathlib import Path
from dataclasses import replace
from scripts.evidence import EvidenceBatch, EvidenceMessage, EvidenceTime, EvidenceStore, _record, _safe_source_path
from .storage import identity


def read_increment(vault, path, client, session, project, captured_at, cursor=None):
    path = _safe_source_path(path)
    before = path.stat()
    if before.st_size > 128 * 1024 * 1024:
        raise ValueError('TRANSCRIPT_TOO_LARGE')
    offset = (cursor or {}).get('offset', 0)
    if not isinstance(offset, int) or offset < 0 or offset > before.st_size:
        raise ValueError('TRANSCRIPT_REWRITTEN')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
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
    if path.stat().st_size < before.st_size:
        raise ValueError('TRANSCRIPT_CHANGED')
    # A writer may append while we read; process complete lines only.
    end = raw.rfind(b'\n') + 1
    complete = raw[:end]
    if not end and len(raw) == 2 * 1024 * 1024:
        raise ValueError('TRANSCRIPT_LINE_TOO_LARGE')
    messages = []
    position = offset
    for line in complete.splitlines(keepends=True):
        start = position
        position += len(line)
        if not line.strip():
            continue
        doc = json.loads(line.decode('utf-8'))
        role = content = None
        if client == 'codex':
            if doc.get('type') == 'response_item':
                payload = doc.get('payload', {})
                if payload.get('type') == 'message':
                    role, content = payload.get('role'), payload.get('content')
                elif payload.get('type') not in {'function_call', 'function_call_output', 'reasoning', 'custom_tool_call', 'custom_tool_call_output', 'web_search_call', 'local_shell_call'}:
                    raise ValueError('UNSUPPORTED_CODEX_ITEM')
            elif doc.get('type') not in {'session_meta', 'event_msg', 'turn_context', 'compacted'}:
                raise ValueError('UNSUPPORTED_CODEX_TRANSCRIPT')
        elif client == 'claude':
            if doc.get('type') in {'user', 'assistant'}:
                message = doc.get('message', {})
                role, content = message.get('role', doc['type']), message.get('content')
            elif doc.get('type') not in {'system', 'progress', 'summary', 'file-history-snapshot', 'queue-operation', 'last-prompt', 'custom-title', 'agent-name', 'agent-color'}:
                raise ValueError('UNSUPPORTED_CLAUDE_TRANSCRIPT')
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
    return EvidenceBatch(tuple(x.record for x in messages), tuple(messages)), {'offset': offset + end, 'prefix_hash': digest.hexdigest(),
             'has_more': len(raw) == 2 * 1024 * 1024 and end > 0}
