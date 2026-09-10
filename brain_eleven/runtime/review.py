"""Seven-day review candidates. These are proposals, not canonical memory.

The review store is deliberately separate from canonical memory.  Terminal
records retain only bounded, content-free audit metadata so a rejected capture
can be suppressed on replay without retaining the candidate text.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
import re
from brain_eleven.infrastructure.locking import file_lock
from context_compiler_v2.safety import contains_secret
from .storage import read_json, write_json, identity, now, RuntimeConfig


class ReviewStore:
    def __init__(self, vault):
        self.root = RuntimeConfig(vault).root / 'review'

    def path(self, candidate_id):
        if not re.fullmatch(r'rev_[a-f0-9]{64}', candidate_id):
            raise ValueError('Invalid review identity')
        return self.root / (candidate_id + '.json')

    @staticmethod
    def fingerprint(candidate):
        """Return a stable, content-free identity for replay suppression."""
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
        return 'fp_' + hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    def find_by_fingerprint(self, project_id, fingerprint):
        """Find an existing review item for one project/content fingerprint."""
        if not isinstance(project_id, str) or not isinstance(fingerprint, str):
            return None
        for path in sorted(self.root.glob('rev_*.json')):
            item = read_json(path)
            if not isinstance(item, dict) or item.get('project_id') not in {None, project_id}:
                continue
            stored = item.get('candidate_fingerprint')
            if stored is None and isinstance(item.get('candidate'), dict):
                candidate = item['candidate']
                if candidate.get('project_id') == project_id:
                    stored = self.fingerprint(candidate)
            if stored == fingerprint:
                return item.get('id')
        return None

    def add(self, candidate, reason, source):
        from scripts.capture_safety import evaluate_capture
        text_key = 'text' if candidate.get('candidate_type') == 'STATE_MUTATION' else 'content'
        content = candidate.get(text_key, '')
        if not isinstance(content, str) or not evaluate_capture(content).accepted or contains_secret(content) or len(content) > 8000:
            return None
        fields = {'candidate_id', 'candidate_type', 'project_id', 'scope', text_key, 'memory_type', 'commitment', 'confidence', 'evidence_refs', 'operation', 'occurred_at'}
        candidate = {key: value for key, value in candidate.items() if key in fields}
        source = {key: value for key, value in source.items() if key in {'client', 'session_hash', 'evidence_id', 'role'}}
        fingerprint = self.fingerprint(candidate)
        key = identity('rev_', candidate['candidate_id'], candidate['project_id'])
        path = self.path(key)
        # The index lock serializes different candidate IDs that describe the
        # same capture.  Without it two concurrent deliveries could both pass
        # the fingerprint scan and create duplicate review records.
        with file_lock(self.root / 'index'):
            existing = self.find_by_fingerprint(candidate.get('project_id'), fingerprint)
            if existing:
                return existing
            with file_lock(path):
                if path.exists():
                    existing_item = read_json(path)
                    if isinstance(existing_item, dict):
                        existing_fingerprint = existing_item.get('candidate_fingerprint')
                        if existing_fingerprint is None and isinstance(existing_item.get('candidate'), dict):
                            existing_fingerprint = self.fingerprint(existing_item['candidate'])
                        if existing_fingerprint == fingerprint:
                            return existing_item.get('id', key)
                        # A stable candidate ID must never be reused for a
                        # materially different proposal.
                        return None
                    return None
                write_json(path, {'id': key, 'status': 'PENDING', 'created_at': now(),
                                 'expires_at': (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                                 'candidate': candidate, 'candidate_fingerprint': fingerprint,
                                 'project_id': candidate['project_id'], 'reason': reason, 'source': source})
        return key

    def expire(self):
        for path in self.root.glob('rev_*.json'):
            with file_lock(path):
                item = read_json(path)
                if item['status'] == 'PENDING' and datetime.fromisoformat(item['expires_at']) <= datetime.now(timezone.utc):
                    self.finish(item, 'EXPIRED')

    def finish(self, item, status, result=None):
        if status not in {'ACCEPTED', 'REJECTED', 'EXPIRED'}:
            raise ValueError('Invalid review terminal status')
        if item.get('status') != 'PENDING':
            return item
        candidate = item.get('candidate') if isinstance(item.get('candidate'), dict) else {}
        source = item.get('source') if isinstance(item.get('source'), dict) else {}
        value = {key: item[key] for key in ('id', 'created_at', 'expires_at')}
        value.update({
            'status': status,
            'finished_at': now(),
            'result': result,
            'reason': item.get('reason'),
            'source': {key: source[key] for key in ('client', 'session_hash', 'evidence_id', 'role') if key in source},
            'candidate_fingerprint': item.get('candidate_fingerprint') or self.fingerprint(candidate),
            'candidate_id': candidate.get('candidate_id'),
            'candidate_type': candidate.get('candidate_type'),
            'project_id': candidate.get('project_id') or item.get('project_id'),
            'scope': candidate.get('scope'),
            'memory_type': candidate.get('memory_type'),
            'evidence_refs': candidate.get('evidence_refs', []),
            'occurred_at': candidate.get('occurred_at'),
        })
        write_json(self.path(item['id']), value)
        return value

    def list(self):
        self.expire()
        return [read_json(path) for path in sorted(self.root.glob('rev_*.json'))]
