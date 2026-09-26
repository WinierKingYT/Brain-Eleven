"""Re-run the current extractor over recent transcripts, review-only.

Extractor improvements (Turkish decision phrasing, approved assistant
proposals) only reach sessions captured after they ship. ``backfill`` reads
the transcripts of registered projects from the last ``days`` days again and
offers what the current extractor finds to the review queue.

Safety boundary:

- Nothing is written to canonical memory; every candidate goes to review.
- ``ReviewStore.add`` returns the existing record for a candidate that was
  already accepted, rejected or expired, so a human decision is never undone.
  Expired candidates (no human decision, the 7-day timer ran out) are offered
  again only with ``reoffer_expired=True``.
- The default is a dry run that only counts.
- Local model and semantic providers are not re-run.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .evidence import EvidenceBatch, read_increment
from .extraction import DeterministicExtractor, _classify_commitment, _confirmed_proposals, _memory_type, _segments
from .review import ReviewStore
from .storage import identity, now, read_json, write_json

REASON = 'BACKFILL'
MAX_TRANSCRIPTS = 500


def _transcripts(vault, claude_home, codex_home, since):
    """(client, project, session, path) for recent transcripts of registered projects."""
    from brain_eleven.projects.registry import ProjectRegistry, normalize_registry_root
    from .ownership import _project_slug

    projects = [p for p in ProjectRegistry(vault).list_projects() if p.get('project_id') and p.get('root')]
    found = []
    for project in projects:
        directory = Path(claude_home) / 'projects' / _project_slug(str(project['root']))
        for path in sorted(directory.glob('*.jsonl')) if directory.is_dir() else []:
            if path.stat().st_mtime >= since:
                found.append(('claude', project, 'claude:' + path.stem, path))
    roots = {}
    for project in projects:
        try:
            roots[normalize_registry_root(project['root'])] = project
        except (OSError, ValueError):
            continue
    sessions = Path(codex_home) / 'sessions'
    import sys
    scripts = str(Path(__file__).resolve().parents[2] / 'scripts')
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from capture_gap_audit import _codex_meta
    for path in sorted(sessions.rglob('*.jsonl')) if sessions.is_dir() else []:
        if path.stat().st_mtime < since:
            continue
        meta = _codex_meta(path)
        if not meta:
            continue
        try:
            project = roots.get(normalize_registry_root(meta[1]))
        except (OSError, ValueError):
            project = None
        if project:
            found.append(('codex', project, 'codex:' + meta[0][0], path))
    return found[-MAX_TRANSCRIPTS:]


def _read_all(vault, path, client, session, project_id):
    messages, cursor = [], None
    while True:
        batch, cursor = read_increment(vault, path, client, session, project_id, now(), cursor)
        messages.extend(batch.messages)
        if not cursor['has_more']:
            return messages


def candidates_for(messages, project_id):
    """What the current extractor and the worker fallback would propose, review-only."""
    from .worker import fallback_worth_review

    found = []
    confirmations = _confirmed_proposals(messages)
    for position, message in enumerate(messages):
        if position - 1 in confirmations:
            continue
        pair = (message, messages[position + 1]) if position in confirmations else (message,)
        envelope = DeterministicExtractor().extract(EvidenceBatch(tuple(m.record for m in pair), pair))
        for item in envelope.candidates:
            candidate = asdict(item)
            if candidate.get('occurred_at'):
                candidate['occurred_at'] = candidate['occurred_at']['value']
            found.append((candidate, message))
        if message.record.role == 'user' and not envelope.candidates:
            for index, content in enumerate(_segments(message.content)):
                commitment = _classify_commitment(content, 'user').value
                if fallback_worth_review(content, commitment):
                    found.append(({'candidate_id': identity('cand_', message.record.evidence_id, index),
                                   'candidate_type': 'NEW_MEMORY', 'project_id': project_id, 'scope': 'project',
                                   'content': content, 'memory_type': _memory_type(content),
                                   'commitment': commitment, 'confidence': 0,
                                   'evidence_refs': [message.record.evidence_id]}, message))
    return found


def _reoffer(store, review_id, candidate):
    """Turn an EXPIRED record (no human decision) back into a pending candidate."""
    path = store.path(review_id)
    item = read_json(path, {}) or {}
    if item.get('status') != 'EXPIRED':
        return False
    item.update({'status': 'PENDING', 'created_at': now(), 'candidate': candidate,
                 'expires_at': (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                 'reoffered_by': REASON})
    for key in ('finished_at', 'result', 'duplicate_of'):
        item.pop(key, None)
    write_json(path, item)
    return True


def backfill(vault, *, days=14, apply=False, reoffer_expired=False, claude_home=None, codex_home=None):
    home = Path.home()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
    store = ReviewStore(vault)
    summary = {'dry_run': not apply, 'days': days, 'transcripts': 0, 'unreadable': 0, 'candidates': 0,
               'added': 0, 'already_pending': 0, 'decided_before': 0, 'reoffered': 0, 'by_commitment': {}}
    for client, project, session, path in _transcripts(vault, claude_home or home / '.claude',
                                                       codex_home or home / '.codex', since):
        try:
            messages = _read_all(vault, path, client, session, project['project_id'])
        except (OSError, ValueError, UnicodeDecodeError):
            summary['unreadable'] += 1
            continue
        summary['transcripts'] += 1
        for candidate, message in candidates_for(messages, project['project_id']):
            summary['candidates'] += 1
            commitment = str(candidate.get('commitment'))
            summary['by_commitment'][commitment] = summary['by_commitment'].get(commitment, 0) + 1
            if not apply:
                continue
            before = {x.get('id'): x.get('status') for x in store._items() if isinstance(x, dict)}
            source = {'client': client, 'session_hash': identity('session_', session),
                      'evidence_id': message.record.evidence_id, 'role': message.record.role}
            review_id = store.add(candidate, REASON, source)
            if not review_id:
                continue
            status = before.get(review_id)
            if status is None:
                summary['added'] += 1
            elif status == 'PENDING':
                summary['already_pending'] += 1
            elif status == 'EXPIRED' and reoffer_expired and _reoffer(store, review_id, candidate):
                summary['reoffered'] += 1
            else:
                summary['decided_before'] += 1
    return summary
