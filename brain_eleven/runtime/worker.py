"""One durable event consumer shared by both native clients."""
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import threading
from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.state import StateStore
from brain_eleven.infrastructure.locking import file_lock
from brain_eleven.operations import operation, operation_result
from capture_event import parse_hook_event
from capture_queue import CaptureQueue
from evidence import EvidenceStore, EvidenceBatch
from extraction import DeterministicExtractor, _segments, _classify_commitment, _memory_type
from memory_truth import MemoryTruthEngine
from state_boundary import StateBoundary
from .storage import RuntimeConfig, read_json, write_json, identity, now
from .evidence import read_increment
from .review import ReviewStore
from .model import propose


CAPTURE_RECEIPT_SCHEMA_VERSION = 1


class WorkerProcessingError(RuntimeError):
    """A content-free processing failure that must keep the queue retryable."""

    def __init__(self, code: str):
        self.code = code if isinstance(code, str) and code else "WORKER_PROCESSING_FAILED"
        super().__init__(self.code)


def allowed(vault, project_root):
    config = RuntimeConfig(vault).load()
    registry = ProjectRegistry(vault)
    record = registry.resolve(project_root)
    if not record or record['status'] != 'active' or record['project_id'] not in config['project_ids'] or not record['proactive_capture']:
        return None
    return record


def enqueue(vault, client, payload):
    if client not in {'claude', 'codex'}:
        raise ValueError('Unsupported client')
    if RuntimeConfig(vault).load()['mode'] == 'OFF':
        return {'status': 'OFF'}
    root = payload.get('cwd')
    record = allowed(vault, root)
    if not record:
        return {'status': 'SCOPE_DISABLED'}
    source = payload.get('transcript_path')
    if not source:
        return {'status': 'DEGRADED', 'error': 'TRANSCRIPT_NOT_FOUND'}
    session = payload.get('session_id')
    if not isinstance(session, str) or not session:
        raise ValueError('Session identity required')
    path = Path(source)
    try:
        stamp = path.stat()
    except OSError:
        return {'status': 'DEGRADED', 'error': 'TRANSCRIPT_NOT_FOUND'}
    session_key = client + ':' + hashlib.sha256(session.encode()).hexdigest()
    event = parse_hook_event({'event_type': 'SESSION_END', 'session_id': session_key,
                             'project_root': str(root), 'transcript_path': str(path), 'event_at': now()}, vault_path=vault)
    key = identity('capture_', session_key, str(path), stamp.st_size, stamp.st_mtime_ns)
    event = replace(event, idempotency_key=key, event_id=identity('evt_', key)[:30])
    return CaptureQueue(vault).enqueue(event).to_dict()


def apply_candidate(vault, candidate, *, op_id, approved=False, target_id=None, expected_revision=None):
    """Apply one effect. Receipt and effect share the store transaction."""
    from capture_safety import evaluate_capture
    from context_compiler_v2.safety import contains_secret
    if RuntimeConfig(vault).load()['mode'] not in {'CANARY', 'ACTIVE'}:
        return {'status': 'SCOPE_ERROR'}
    content = candidate.get('text' if candidate.get('candidate_type') == 'STATE_MUTATION' else 'content', '')
    if not evaluate_capture(content).accepted or contains_secret(content):
        return {'status': 'REJECTED', 'error': 'SENSITIVE_CANDIDATE'}
    project = ProjectRegistry(vault).get(candidate['project_id'])
    if not project or not allowed(vault, project['root']):
        return {'status': 'SCOPE_ERROR'}
    if candidate['candidate_type'] == 'STATE_MUTATION':
        store = StateStore(vault)
        revision = store.project_revision(project['project_id']) if expected_revision is None else expected_revision
        with operation(op_id, identity('request_', candidate, target_id)):
            result = StateBoundary(vault).apply(candidate, expected_revision=revision, source={'type': 'user', 'reference': op_id}, commit=True, target_id=target_id)
            receipt = operation_result.get()
            if receipt:
                return {**result.to_dict(), 'revision_before': receipt['revision_before'], 'revision_after': receipt['revision_after'],
                        'record_id': next(iter(receipt['record_ids']), None), 'canonical_write': not receipt['replayed'], 'replayed': receipt['replayed']}
        return result.to_dict()
    values = {key: value for key, value in candidate.items() if key in {'candidate_id', 'content', 'memory_type', 'scope', 'project_id', 'commitment', 'confidence', 'evidence_refs'}}
    values['confidence'] = max(values.get('confidence', 0), 0.97) if approved else values.get('confidence', 0)
    values['commitment'] = 'COMMITTED' if approved else values.get('commitment', 'UNCERTAIN')
    if target_id:
        values.update(operation='SUPERSEDE_EXISTING', target_memory_id=target_id, successor_memory_id=identity('mem_', op_id)[:30])
    result = MemoryTruthEngine(vault).process([values], commit=True, commit_new=True, expected_revision=expected_revision, operation_id=op_id)
    return result.to_dict()


class Worker:
    def __init__(self, vault):
        self.vault = Path(vault).resolve()
        self.config = RuntimeConfig(vault)
        self.queue = CaptureQueue(vault)
        self.review = ReviewStore(vault)

    def _receipt_path(self, job_id):
        return self.config.root / 'capture-receipts' / (job_id + '.json')

    def _read_receipt(self, job):
        """Return a previously verified effect receipt, rejecting unsafe data."""
        value = read_json(self._receipt_path(job['job_id']))
        if value is None:
            return None
        if not isinstance(value, dict):
            raise WorkerProcessingError('CAPTURE_RECEIPT_CORRUPT')
        if value.get('schema_version') != CAPTURE_RECEIPT_SCHEMA_VERSION:
            raise WorkerProcessingError('CAPTURE_RECEIPT_CORRUPT')
        if value.get('job_id') != job['job_id'] or value.get('event_id') != job['event']['event_id']:
            raise WorkerProcessingError('CAPTURE_RECEIPT_IDENTITY_MISMATCH')
        if value.get('status') != 'EFFECT_VERIFIED' or value.get('canonical_verified') is not True:
            raise WorkerProcessingError('CAPTURE_EFFECT_UNVERIFIED')
        for field in ('evidence_count', 'canonical_effect_count', 'review_effect_count'):
            if isinstance(value.get(field), bool) or not isinstance(value.get(field), int) or value[field] < 0:
                raise WorkerProcessingError('CAPTURE_RECEIPT_CORRUPT')
        effect_ids = value.get('effect_ids', [])
        if not isinstance(effect_ids, list) or len(effect_ids) > 10000 or not all(isinstance(item, str) and item for item in effect_ids):
            raise WorkerProcessingError('CAPTURE_RECEIPT_CORRUPT')
        return value

    def _write_receipt(self, job, result):
        """Persist a content-free effect proof before acknowledging the queue job."""
        if result.get('status') != 'PROCESSED' or result.get('effect_verified') is not True:
            raise WorkerProcessingError('CAPTURE_EFFECT_UNVERIFIED')
        receipt = {
            'schema_version': CAPTURE_RECEIPT_SCHEMA_VERSION,
            'job_id': job['job_id'],
            'event_id': job['event']['event_id'],
            'project_id': job['event']['project']['project_id'],
            'status': 'EFFECT_VERIFIED',
            'canonical_verified': True,
            'evidence_count': int(result.get('evidence_count', 0)),
            'canonical_effect_count': int(result.get('canonical_effect_count', 0)),
            'review_effect_count': int(result.get('review_effect_count', 0)),
            'effect_ids': list(result.get('effect_ids', []))[:10000],
            'at': now(),
        }
        if any(isinstance(receipt[field], bool) or receipt[field] < 0 for field in ('evidence_count', 'canonical_effect_count', 'review_effect_count')):
            raise WorkerProcessingError('CAPTURE_RECEIPT_INVALID')
        write_json(self._receipt_path(job['job_id']), receipt)
        return receipt

    def _verify_canonical_effect(self, candidate, outcome, operation_id):
        """Re-read the canonical transaction receipt before acknowledging work."""
        if not isinstance(outcome, dict) or outcome.get('status') != 'SUCCESS':
            return False
        if candidate.get('candidate_type') == 'STATE_MUTATION':
            receipts = StateStore(self.vault).load().get('operation_receipts', {})
            receipt = receipts.get(operation_id) if isinstance(receipts, dict) else None
            record_id = outcome.get('record_id')
            return isinstance(receipt, dict) and isinstance(record_id, str) and record_id in receipt.get('record_ids', [])
        receipts = MemoryStore(self.vault).load().get('operation_receipts', {})
        receipt = receipts.get(operation_id) if isinstance(receipts, dict) else None
        decisions = outcome.get('decisions')
        return isinstance(receipt, dict) and isinstance(receipt.get('decisions'), list) and isinstance(decisions, list)

    def once(self):
        self.config.root.mkdir(parents=True, exist_ok=True)
        with file_lock(self.config.root / 'worker', timeout=1):
            if self.config.load()['mode'] == 'OFF':
                return {'status': 'OFF'}
            self.queue.recover_expired_claims()
            self.review.expire()
            job = self.queue.claim_next()
            if not job:
                return {'status': 'IDLE'}
            stop = threading.Event()
            def heartbeat():
                while not stop.wait(30):
                    try:
                        self.queue.renew(job['job_id'])
                    except Exception:
                        return
            thread = threading.Thread(target=heartbeat, daemon=True)
            thread.start()
            try:
                self.queue.start_processing(job['job_id'])
                prior_receipt = self._read_receipt(job)
                if prior_receipt is not None:
                    result = {
                        'status': 'PROCESSED',
                        'job_id': job['job_id'],
                        'messages': 0,
                        'effects': prior_receipt['canonical_effect_count'],
                        'evidence_count': prior_receipt['evidence_count'],
                        'canonical_effect_count': prior_receipt['canonical_effect_count'],
                        'review_effect_count': prior_receipt['review_effect_count'],
                        'effect_ids': prior_receipt['effect_ids'],
                        'effect_verified': True,
                        'receipt_replayed': True,
                        'has_more': False,
                    }
                else:
                    result = self.process(job)
                parts = [result]
                while parts[-1].get('has_more', False):
                    if self.config.load()['mode'] == 'OFF':
                        raise WorkerProcessingError('RUNTIME_STOPPED')
                    parts.append(self.process(job))
                result = {
                    **parts[-1],
                    'messages': sum(int(part.get('messages', 0)) for part in parts),
                    'effects': sum(int(part.get('effects', 0)) for part in parts),
                    'evidence_count': sum(int(part.get('evidence_count', 0)) for part in parts),
                    'canonical_effect_count': sum(int(part.get('canonical_effect_count', 0)) for part in parts),
                    'review_effect_count': sum(int(part.get('review_effect_count', 0)) for part in parts),
                    'effect_ids': [effect_id for part in parts for effect_id in part.get('effect_ids', [])],
                    'effect_verified': all(part.get('effect_verified') is True for part in parts),
                }
                if result.get('status') != 'PROCESSED':
                    raise WorkerProcessingError(str(result.get('status') or 'WORKER_PROCESSING_FAILED'))
                self._write_receipt(job, result)
                self.queue.commit(job['job_id'])
                write_json(self.config.root / 'last-worker.json', {'at': now(), **result})
                return result
            except Exception as exc:
                # Exceptions may contain source text or paths: never serialize them.
                code = getattr(exc, 'code', None) or ('EVIDENCE_INVALID' if isinstance(exc, (ValueError, UnicodeError)) else 'WORKER_FAILED')
                receipt = self.queue.retry_or_dead_letter(job['job_id'], error_code=code)
                result = {'status': receipt.status, 'error': code, 'job_id': job['job_id']}
                write_json(self.config.root / 'last-worker.json', {'at': now(), **result})
                return result
            finally:
                stop.set()
                thread.join(timeout=2)

    def process(self, job):
        event = job['event']
        project = allowed(self.vault, event['project_root'])
        if not project or project['project_id'] != event['project']['project_id']:
            return {'status': 'SCOPE_DISABLED', 'job_id': job['job_id']}
        if 'transcript_path' not in event:
            return {'status': 'NO_EVIDENCE', 'job_id': job['job_id']}
        session = event['session_id']
        client = session.split(':')[0]
        if client not in {'claude', 'codex'}:
            # Existing Foundation queue jobs are Claude SessionEnd events.
            client = 'claude'
            session = 'claude:' + hashlib.sha256(session.encode()).hexdigest()
        checkpoint = self.config.root / 'cursors' / (identity('src_', client, session, event['transcript_path']) + '.json')
        batch, cursor = read_increment(self.vault, event['transcript_path'], client, session, project['project_id'], event['event_at'], read_json(checkpoint))
        EvidenceStore(self.vault).persist(batch.records)
        outcomes = []
        effect_ids = []
        canonical_effect_count = 0
        review_effect_count = 0
        for message in batch.messages:
            self.queue.renew(job['job_id'])
            envelope = DeterministicExtractor().extract(EvidenceBatch((message.record,), (message,)))
            correction = any(x.reason == 'LIFECYCLE_TARGET_UNKNOWN' for x in envelope.quarantined)
            source = {'client': client, 'session_hash': identity('session_', session), 'evidence_id': message.record.evidence_id, 'role': message.record.role}
            for item in envelope.candidates:
                candidate = asdict(item)
                if candidate.get('occurred_at'):
                    candidate['occurred_at'] = candidate['occurred_at']['value']
                requires_review = correction or candidate.get('operation', '').startswith('RESOLVE') or message.record.role != 'user'
                if requires_review or self.config.load()['mode'] == 'SHADOW':
                    review_id = self.review.add(candidate, 'LIFECYCLE_TARGET_UNKNOWN' if correction else 'REVIEW_REQUIRED', source)
                    if not review_id:
                        raise WorkerProcessingError('REVIEW_PERSIST_FAILED')
                    effect_ids.append(review_id)
                    review_effect_count += 1
                    continue
                if self.config.load()['mode'] not in {'CANARY', 'ACTIVE'}:
                    raise ValueError('Runtime stopped during processing')
                op_id = identity('op_', candidate['candidate_id'], candidate['project_id'])
                outcome = apply_candidate(self.vault, candidate, op_id=op_id)
                if outcome['status'] == 'SUCCESS':
                    decisions = outcome.get('decisions', [])
                    if not isinstance(decisions, list):
                        raise WorkerProcessingError('CANONICAL_RECEIPT_INVALID')
                    if not self._verify_canonical_effect(candidate, outcome, op_id):
                        raise WorkerProcessingError('CANONICAL_EFFECT_UNVERIFIED')
                    effect_ids.extend(
                        str(item.get('successor_memory_id') or item.get('target_memory_id') or item.get('candidate_id'))
                        for item in decisions if isinstance(item, dict)
                    )
                    canonical_effect_count += 1
                    write_json(self.config.root / 'capture-observations' / (op_id + '.json'), {'operation_id':op_id, 'project_id':project['project_id'],
                               'client':client, 'role':message.record.role, 'evidence_id':message.record.evidence_id, 'at':now()})
                if outcome['status'] not in {'SUCCESS', 'EMPTY'}:
                    if outcome['status'] in {'REVIEW_REQUIRED', 'SCOPE_ERROR', 'DEGRADED'}:
                        review_id = self.review.add(candidate, outcome['status'], source)
                        if not review_id:
                            raise WorkerProcessingError('REVIEW_PERSIST_FAILED')
                        effect_ids.append(review_id)
                        review_effect_count += 1
                    else:
                        raise RuntimeError('Candidate not applied')
                outcomes.append(outcome['status'])
            # Preserve only bounded safe user proposals for review. Assistant
            # text is not saved unless the optional local extractor proposes it.
            if message.record.role == 'user' and not envelope.candidates:
                for index, content in enumerate(_segments(message.content)):
                    candidate = {'candidate_id': identity('cand_', message.record.evidence_id, index), 'candidate_type': 'NEW_MEMORY',
                                 'project_id': project['project_id'], 'scope': 'project', 'content': content,
                                 'memory_type': _memory_type(content), 'commitment': _classify_commitment(content, 'user').value,
                                 'confidence': 0, 'evidence_refs': [message.record.evidence_id]}
                    review_id = self.review.add(candidate, 'LOW_EVIDENCE_COMMITMENT', source)
                    if not review_id:
                        raise WorkerProcessingError('REVIEW_PERSIST_FAILED')
                    effect_ids.append(review_id)
                    review_effect_count += 1
            proposals, model_error = propose(self.config.load().get('local_model'), message)
            if model_error:
                write_json(self.config.root / 'model-status.json', {'at': now(), 'status': model_error})
            for index, item in enumerate(proposals):
                candidate = {**item, 'candidate_id': identity('cand_', message.record.evidence_id, 'model', index), 'candidate_type': 'NEW_MEMORY',
                             'project_id': project['project_id'], 'scope': 'project', 'commitment': 'PROPOSED', 'confidence': 0,
                             'evidence_refs': [message.record.evidence_id]}
                review_id = self.review.add(candidate, 'MODEL_PROPOSAL', source)
                if not review_id:
                    raise WorkerProcessingError('REVIEW_PERSIST_FAILED')
                effect_ids.append(review_id)
                review_effect_count += 1
        write_json(checkpoint, cursor)
        return {
            'status': 'PROCESSED',
            'job_id': job['job_id'],
            'messages': len(batch.messages),
            'effects': len(outcomes),
            'evidence_count': len(batch.records),
            'canonical_effect_count': canonical_effect_count,
            'review_effect_count': review_effect_count,
            'effect_ids': effect_ids,
            'effect_verified': True,
            'has_more': cursor['has_more'],
        }
