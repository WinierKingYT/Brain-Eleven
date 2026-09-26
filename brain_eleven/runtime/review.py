"""Seven-day review candidates. These are proposals, not canonical memory.

The review store is deliberately separate from canonical memory.  Terminal
records retain only bounded, content-free audit metadata so a rejected capture
can be suppressed on replay without retaining the candidate text.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
import math
import re
from context_compiler_v2.safety import contains_secret
from .capture_safety import evaluate_capture
from .storage import read_json, write_json, identity, now, RuntimeConfig, runtime_file_lock as file_lock

_REVIEW_CANDIDATE_TYPE_ORDER = {
    'STATE_MUTATION': 0,
    'NEW_MEMORY': 1,
}


_SHELL_LINE = re.compile(r"^\s*(PS [A-Za-z]:\\|>>|\$ |[A-Za-z]:\\[^\n]*>|Traceback|\{\s*$|\}\s*$|\"[\w-]+\":)", re.M)


def content_shape(text):
    """Coarse shape of a candidate: terminal_or_code, short_ack, question or prose."""
    stripped = text.strip()
    if len(_SHELL_LINE.findall(stripped)) >= 2 or stripped.startswith(('{', '[', '```')):
        return 'terminal_or_code'
    if len(stripped) <= 20:
        return 'short_ack'
    if stripped.endswith('?'):
        return 'question'
    return 'prose'


_WORD = re.compile(r"\w{3,}", re.UNICODE)


def _words(text):
    return {w.lower() for w in _WORD.findall(text or '')}


def rank_similar(content, memories, *, limit=None):
    """Active memories ordered by word overlap with ``content`` (Jaccard, 0..1).

    Deterministic and local: it only helps a reviewer spot a likely duplicate
    or the record a correction should supersede; it never decides anything.
    """
    words = _words(content)
    scored = []
    for memory in memories:
        other = _words(memory.get('content', ''))
        union = words | other
        score = len(words & other) / len(union) if union else 0.0
        scored.append((round(score, 2), memory))
    scored.sort(key=lambda pair: (-pair[0], str(pair[1].get('memory_id', ''))))
    return scored[:limit] if limit else scored


DECISION_NOTE_MAX = 280


class ReviewStore:
    def __init__(self, vault):
        self.root = RuntimeConfig(vault).root / 'review'

    def path(self, candidate_id):
        if not re.fullmatch(r'rev_[a-f0-9]{64}', candidate_id):
            raise ValueError('Invalid review identity')
        return self.root / (candidate_id + '.json')

    @staticmethod
    def fingerprint(candidate):
        """Return the project-scoped content identity used by B2 dedup."""
        text_key = 'text' if candidate.get('candidate_type') == 'STATE_MUTATION' else 'content'
        values = {
            'project_id': candidate.get('project_id'),
            'candidate_type': candidate.get('candidate_type'),
            'scope': candidate.get('scope'),
            'memory_type': candidate.get('memory_type'),
            'operation': candidate.get('operation'),
            'content': candidate.get(text_key),
        }
        return 'fp_' + hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def event_fingerprint(candidate):
        """Return an exact capture identity, including evidence references."""
        text_key = 'text' if candidate.get('candidate_type') == 'STATE_MUTATION' else 'content'
        evidence = candidate.get('evidence_refs', [])
        if not isinstance(evidence, list):
            evidence = []
        values = {
            'project_id': candidate.get('project_id'),
            'candidate_type': candidate.get('candidate_type'),
            'scope': candidate.get('scope'),
            'memory_type': candidate.get('memory_type'),
            'operation': candidate.get('operation'),
            'content': candidate.get(text_key),
            'evidence_refs': sorted(str(item) for item in evidence),
        }
        return 'efp_' + hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def content_fingerprint(candidate):
        """Backward-compatible alias for the B2 content fingerprint."""
        return ReviewStore.fingerprint(candidate)

    @staticmethod
    def _candidate(item):
        candidate = item.get('candidate')
        if isinstance(candidate, dict):
            return candidate
        return item

    @classmethod
    def _project_id(cls, item):
        candidate = cls._candidate(item)
        return candidate.get('project_id') or item.get('project_id')

    @classmethod
    def _content_fingerprint(cls, item):
        stored = item.get('content_fingerprint')
        if isinstance(stored, str) and stored:
            return stored
        candidate = item.get('candidate')
        if isinstance(candidate, dict):
            return cls.content_fingerprint(candidate)
        return None

    @staticmethod
    def _created_timestamp(value):
        if not isinstance(value, str):
            return float('inf')
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except (TypeError, ValueError, OverflowError):
            return float('inf')

    @classmethod
    def _sort_key(cls, item):
        candidate = cls._candidate(item)
        confidence = candidate.get('confidence', 0)
        try:
            confidence = float(confidence)
            if not math.isfinite(confidence):
                confidence = 0.0
        except (TypeError, ValueError):
            confidence = 0.0
        type_rank = _REVIEW_CANDIDATE_TYPE_ORDER.get(candidate.get('candidate_type'), 2)
        return (-confidence, cls._created_timestamp(item.get('created_at')), type_rank, str(item.get('id', '')))

    def _items(self):
        return [read_json(path) for path in sorted(self.root.glob('rev_*.json'))]

    def find_by_fingerprint(self, project_id, fingerprint):
        """Find an existing item for one project/content fingerprint."""
        if not isinstance(project_id, str) or not isinstance(fingerprint, str):
            return None
        for item in self._items():
            if isinstance(item, dict) and self._project_id(item) == project_id:
                if self._content_fingerprint(item) == fingerprint:
                    return item.get('id')
        return None

    def find_by_event_fingerprint(self, project_id, event_fingerprint):
        """Find an existing item for one exact capture/evidence identity."""
        if not isinstance(project_id, str) or not isinstance(event_fingerprint, str):
            return None
        for item in self._items():
            if not isinstance(item, dict) or self._project_id(item) != project_id:
                continue
            stored = item.get('event_fingerprint')
            candidate = item.get('candidate')
            if stored is None and isinstance(candidate, dict):
                stored = self.event_fingerprint(candidate)
            if stored == event_fingerprint:
                return item.get('id')
        return None

    def add(self, candidate, reason, source):
        text_key = 'text' if candidate.get('candidate_type') == 'STATE_MUTATION' else 'content'
        content = candidate.get(text_key, '')
        if not isinstance(content, str) or not evaluate_capture(content).accepted or contains_secret(content) or len(content) > 8000:
            return None
        fields = {'candidate_id', 'candidate_type', 'project_id', 'scope', text_key, 'memory_type', 'commitment', 'confidence', 'evidence_refs', 'operation', 'occurred_at'}
        candidate = {key: value for key, value in candidate.items() if key in fields}
        source = {key: value for key, value in source.items() if key in {'client', 'session_hash', 'evidence_id', 'role'}}
        fingerprint = self.fingerprint(candidate)
        event_fingerprint = self.event_fingerprint(candidate)
        key = identity('rev_', candidate['candidate_id'], candidate['project_id'])
        path = self.path(key)
        # The index lock serializes different candidate IDs that describe the
        # same capture.  Without it two concurrent deliveries could both pass
        # the fingerprint scan and create duplicate review records.
        with file_lock(self.root / 'index'):
            existing = self.find_by_event_fingerprint(candidate.get('project_id'), event_fingerprint)
            if existing:
                return existing
            with file_lock(path):
                if path.exists():
                    existing_item = read_json(path)
                    if isinstance(existing_item, dict):
                        existing_fingerprint = existing_item.get('event_fingerprint')
                        if existing_fingerprint is None and isinstance(existing_item.get('candidate'), dict):
                            existing_fingerprint = self.event_fingerprint(existing_item['candidate'])
                        if existing_fingerprint == event_fingerprint or (
                                existing_fingerprint is None and 'candidate' not in existing_item):
                            return existing_item.get('id', key)
                        # A stable candidate ID must never be reused for a
                        # materially different proposal.
                        return None
                    return None
                write_json(path, {'id': key, 'status': 'PENDING', 'created_at': now(),
                                 'expires_at': (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                                 'candidate': candidate, 'candidate_fingerprint': fingerprint,
                                 'event_fingerprint': event_fingerprint,
                                 'content_fingerprint': fingerprint,
                                 'project_id': candidate['project_id'], 'reason': reason, 'source': source})
        return key

    def expire(self):
        with file_lock(self.root / 'index'):
            for path in self.root.glob('rev_*.json'):
                item = read_json(path)
                if (isinstance(item, dict) and item.get('status') == 'PENDING'
                        and datetime.fromisoformat(item['expires_at']) <= datetime.now(timezone.utc)):
                    # Expiry remains a per-candidate B1 lifecycle operation.
                    # A surviving duplicate may become the next visible item.
                    self.finish(item, 'EXPIRED', grouped=False)

    def primary(self, item):
        """Return the deterministic visible item for an item's B2 group."""
        if not isinstance(item, dict) or item.get('status') != 'PENDING':
            return item
        project_id = self._project_id(item)
        content_fingerprint = self._content_fingerprint(item)
        group = [candidate for candidate in self._items()
                 if isinstance(candidate, dict) and candidate.get('status') == 'PENDING'
                 and self._project_id(candidate) == project_id
                 and self._content_fingerprint(candidate) == content_fingerprint]
        return sorted(group, key=self._sort_key)[0] if group else item

    def _terminal_value(self, item, status, result=None, *, duplicate_of=None):
        candidate = item.get('candidate') if isinstance(item.get('candidate'), dict) else {}
        source = item.get('source') if isinstance(item.get('source'), dict) else {}
        value = {key: item[key] for key in ('id', 'created_at', 'expires_at')}
        value.update({
            'status': status,
            'finished_at': now(),
            'result': result,
            'reason': item.get('reason'),
            'decision_note': item.get('decision_note'),
            'source': {key: source[key] for key in ('client', 'session_hash', 'evidence_id', 'role') if key in source},
            'candidate_fingerprint': item.get('candidate_fingerprint') or self.fingerprint(candidate),
            'event_fingerprint': item.get('event_fingerprint') or self.event_fingerprint(candidate),
            'content_fingerprint': item.get('content_fingerprint') or self.content_fingerprint(candidate),
            'candidate_id': candidate.get('candidate_id') or item.get('candidate_id'),
            'candidate_type': candidate.get('candidate_type') or item.get('candidate_type'),
            'project_id': candidate.get('project_id') or item.get('project_id'),
            'scope': candidate.get('scope') or item.get('scope'),
            'memory_type': candidate.get('memory_type') or item.get('memory_type'),
            'confidence': candidate.get('confidence', item.get('confidence', 0)),
            'evidence_refs': candidate.get('evidence_refs', item.get('evidence_refs', [])),
            'occurred_at': candidate.get('occurred_at') or item.get('occurred_at'),
        })
        if duplicate_of:
            value['duplicate_of'] = duplicate_of
        return value

    def finish(self, item, status, result=None, *, grouped=True):
        if status not in {'ACCEPTED', 'REJECTED', 'EXPIRED'}:
            raise ValueError('Invalid review terminal status')
        if item.get('status') != 'PENDING':
            return item
        if not grouped:
            value = self._terminal_value(item, status, result)
            write_json(self.path(item['id']), value)
            return value
        group = [candidate for candidate in self._items()
                 if isinstance(candidate, dict) and candidate.get('status') == 'PENDING'
                 and self._project_id(candidate) == self._project_id(item)
                 and self._content_fingerprint(candidate) == self._content_fingerprint(item)]
        primary = sorted(group, key=self._sort_key)[0] if group else item
        primary_id = primary.get('id')
        primary_value = None
        for candidate in group or [item]:
            if candidate.get('id') == item.get('id') and item.get('decision_note'):
                # The reviewer's note lives on the in-memory item, not yet on disk.
                candidate = {**candidate, 'decision_note': item['decision_note']}
            duplicate_of = None if candidate.get('id') == primary_id else primary_id
            candidate_result = result if duplicate_of is None else {'status': status, 'duplicate_of': primary_id}
            value = self._terminal_value(candidate, status, candidate_result, duplicate_of=duplicate_of)
            write_json(self.path(candidate['id']), value)
            if candidate.get('id') == primary_id:
                primary_value = value
        return primary_value or self._terminal_value(item, status, result)

    def reject_matching(self, predicate, note, *, dry_run=True, sample=3):
        """Reject every pending review group whose visible primary matches ``predicate``.

        Reads the queue once (a per-item ``finish`` rescans it every time),
        applies the same grouping as ``finish``/``list`` under the same index
        lock, and records ``note`` on each rejected primary. Duplicates in a
        group are rejected as duplicates of their primary. Nothing is deleted.
        """
        self.expire()
        with file_lock(self.root / 'index'):
            groups = {}
            for item in self._items():
                if isinstance(item, dict) and item.get('status') == 'PENDING':
                    groups.setdefault((self._project_id(item), self._content_fingerprint(item)), []).append(item)
            matched = []
            for group in groups.values():
                ordered = sorted(group, key=self._sort_key)
                if predicate(ordered[0]):
                    matched.append(ordered)
            samples = [self._candidate(group[0]).get('content') or self._candidate(group[0]).get('text') or ''
                       for group in matched[:sample]]
            if not dry_run:
                for ordered in matched:
                    primary = {**ordered[0], 'decision_note': note}
                    write_json(self.path(primary['id']), self._terminal_value(primary, 'REJECTED'))
                    for duplicate in ordered[1:]:
                        write_json(self.path(duplicate['id']), self._terminal_value(
                            duplicate, 'REJECTED', {'status': 'REJECTED', 'duplicate_of': primary['id']},
                            duplicate_of=primary['id']))
            return {'matched': len(matched), 'items': sum(len(g) for g in matched),
                    'samples': samples, 'dry_run': dry_run}

    def list(self):
        self.expire()
        with file_lock(self.root / 'index'):
            items = self._items()
            groups = {}
            for item in items:
                if isinstance(item, dict) and item.get('status') == 'PENDING':
                    group_key = (self._project_id(item), self._content_fingerprint(item))
                    groups.setdefault(group_key, []).append(item)
            visible = [item for item in items if not (isinstance(item, dict) and item.get('status') == 'PENDING')]
            for group in groups.values():
                ordered = sorted(group, key=self._sort_key)
                primary = ordered[0]
                primary_view = dict(primary)
                primary_view.pop('duplicate_of', None)
                primary_view['duplicate_count'] = len(ordered) - 1
                primary_view['duplicate_ids'] = [item['id'] for item in ordered[1:]]
                visible.append(primary_view)
                for duplicate in ordered[1:]:
                    if duplicate.get('duplicate_of') != primary['id'] or duplicate.get('duplicate_status') != 'DUPLICATE_PENDING':
                        duplicate['duplicate_of'] = primary['id']
                        duplicate['duplicate_status'] = 'DUPLICATE_PENDING'
                        write_json(self.path(duplicate['id']), duplicate)
            return sorted(visible, key=self._sort_key)
