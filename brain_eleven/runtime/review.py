"""Seven-day review candidates. These are proposals, not canonical memory."""
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

    def add(self, candidate, reason, source):
        from capture_safety import evaluate_capture
        text_key = 'text' if candidate.get('candidate_type') == 'STATE_MUTATION' else 'content'
        content = candidate.get(text_key, '')
        if not isinstance(content, str) or not evaluate_capture(content).accepted or contains_secret(content) or len(content) > 8000:
            return None
        fields = {'candidate_id', 'candidate_type', 'project_id', 'scope', text_key, 'memory_type', 'commitment', 'confidence', 'evidence_refs', 'operation', 'occurred_at'}
        candidate = {key: value for key, value in candidate.items() if key in fields}
        source = {key: value for key, value in source.items() if key in {'client', 'session_hash', 'evidence_id', 'role'}}
        key = identity('rev_', candidate['candidate_id'], candidate['project_id'])
        path = self.path(key)
        with file_lock(path):
            if path.exists():
                return key
            write_json(path, {'id': key, 'status': 'PENDING', 'created_at': now(),
                             'expires_at': (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                             'candidate': candidate, 'reason': reason, 'source': source})
        return key

    def expire(self):
        for path in self.root.glob('rev_*.json'):
            with file_lock(path):
                item = read_json(path)
                if item['status'] == 'PENDING' and datetime.fromisoformat(item['expires_at']) <= datetime.now(timezone.utc):
                    self.finish(item, 'EXPIRED')

    def finish(self, item, status, result=None):
        value = {key: item[key] for key in ('id', 'created_at', 'expires_at')}
        value.update(status=status, finished_at=now(), result=result)
        write_json(self.path(item['id']), value)
        return value

    def list(self):
        self.expire()
        return [read_json(path) for path in sorted(self.root.glob('rev_*.json'))]
