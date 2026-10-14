"""Why does Brain-Eleven remember this? One memory back to its source.

A memory keeps evidence ids; an evidence record keeps only hashes and the
byte range in the transcript (never the text). ``why`` finds the transcript
whose path hash matches inside the trusted client roots, re-reads that byte
range with the normal reader and shows the text only when the recomputed
evidence id is the stored one, so a changed or different file can never be
quoted as the source. When the client has deleted the transcript (Claude Code
does after ``cleanupPeriodDays``, 30 by default) it says so instead.
"""
import json
from pathlib import Path

QUOTE_LIMIT = 600
SCAN_LIMIT = 20_000


def _memory(vault, memory_id):
    from brain_eleven.memory import MemoryStore
    document = MemoryStore(vault).load()
    for bucket in ('validated_memory', 'rejected_memory'):
        for item in document.get(bucket, []):
            if isinstance(item, dict) and item.get('memory_id') == memory_id:
                return item, bucket
    return None, None


def _evidence(vault, evidence_id):
    from .evidence import EvidenceStore
    path = EvidenceStore(vault).root / (evidence_id + '.json')
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def _find_transcript(vault, client, path_hash):
    from .capture_provenance import TranscriptProvenanceError, _legacy as provenance
    from .evidence import _legacy_evidence as evidence
    try:
        roots = provenance._configured_roots(vault, client)
    except TranscriptProvenanceError:
        return None
    seen = 0
    for root in roots:
        if not Path(root).is_dir():
            continue
        for candidate in Path(root).rglob('*.jsonl'):
            seen += 1
            if seen > SCAN_LIMIT:
                return None
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if evidence._hash(str(resolved)) == path_hash:
                return resolved
    return None


def _quote(vault, record, path, client):
    """The source text, only if re-reading the byte range reproduces the evidence id."""
    from context_compiler_v2.safety import contains_secret
    from .evidence import _parse_lines
    locator = record['source'].get('locator', {})
    start, end = locator.get('byte_start'), locator.get('byte_end')
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end:
        return None, 'LOCATOR_INVALID'
    try:
        with path.open('rb') as stream:
            stream.seek(start)
            line = stream.read(end - start)
        messages, *_ = _parse_lines(vault, path, client, record.get('session_id'), record.get('project_id'),
                                    record['captured_at'], line, start)
    except OSError:
        return None, 'SOURCE_UNREADABLE'
    except ValueError:
        # The stored byte range no longer holds one whole record: the file changed.
        return None, 'SOURCE_CHANGED'
    match = next((m for m in messages if m.record.evidence_id == record['evidence_id']), None)
    if match is None:
        return None, 'SOURCE_CHANGED'
    text = ' '.join(match.content.split())
    if contains_secret(text):
        return None, 'SOURCE_HAS_SECRET'
    return text[:QUOTE_LIMIT] + ('…' if len(text) > QUOTE_LIMIT else ''), 'FOUND'


def why(vault, memory_id):
    item, bucket = _memory(vault, memory_id)
    if item is None:
        raise ValueError('Unknown memory id')
    sources = []
    for evidence_id in item.get('evidence_refs') or []:
        record = _evidence(vault, evidence_id)
        if record is None:
            sources.append({'evidence_id': evidence_id, 'status': 'EVIDENCE_MISSING'})
            continue
        adapter = str(record.get('source', {}).get('locator', {}).get('adapter', ''))
        client = adapter.split('-')[0] if adapter.split('-')[0] in {'claude', 'codex'} else None
        entry = {'evidence_id': evidence_id, 'role': record.get('role'),
                 'occurred_at': (record.get('occurred_at') or {}).get('value'), 'client': client}
        path = _find_transcript(vault, client, record['source'].get('path_hash')) if client else None
        if path is None:
            entry['status'] = 'SOURCE_DELETED'
        else:
            entry['quote'], entry['status'] = _quote(vault, record, path, client)
            if entry['quote'] is None:
                entry.pop('quote')
        sources.append(entry)
    return {
        'memory_id': memory_id, 'content': item.get('content'), 'type': item.get('type'),
        'status': item.get('status') or 'active', 'bucket': bucket, 'approved_by_owner': item.get('is_approved'),
        'source': item.get('source'), 'written_at': item.get('timestamp'), 'project_id': item.get('project_id'),
        'scope': item.get('scope'), 'sources': sources,
        'note': None if sources else 'Bu kayıt bir konuşma kanıtına bağlı değil (elle ya da /study ile yazılmış olabilir).',
    }
