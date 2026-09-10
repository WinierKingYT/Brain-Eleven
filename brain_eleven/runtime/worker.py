"""One durable event consumer shared by both native clients."""
from dataclasses import asdict, replace
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import threading
from brain_eleven.memory import MemoryStore, MemoryStoreConflict
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.state import StateStore, StateStoreConflict
from brain_eleven.infrastructure.locking import MemoryStoreLockTimeout, file_lock
from brain_eleven.operations import operation, operation_result
from scripts.capture_event import parse_hook_event
from scripts.capture_queue import CaptureQueue
from scripts.evidence import EvidenceStore, EvidenceBatch
from scripts.extraction import DeterministicExtractor, _segments, _classify_commitment, _memory_type
from scripts.memory_truth import MemoryTruthEngine, TruthCandidate
from scripts.state_boundary import StateBoundary
from .storage import RuntimeConfig, read_json, write_json, identity, now
from .evidence import read_increment
from .review import ReviewStore
from .model import propose


CAPTURE_RECEIPT_SCHEMA_VERSION = 2

# StateBoundary proposals use extraction operation names while StateStore
# receipts intentionally use semantic mutation names.  Keep the translation
# explicit so receipt verification binds to the actual canonical contract.
_STATE_OPERATION_RECEIPTS = {
    'ADD_BLOCKER': 'blocker_added',
    'RESOLVE_BLOCKER': 'blocker_resolved',
    'SET_CURRENT_PHASE': 'milestone_set',
    'ADD_WORK_ITEM': 'work_item_added',
    'SET_OBJECTIVE': 'objective_set',
    'ADD_REQUIREMENT': 'requirement_added',
    'RESOLVE_REQUIREMENT': 'requirement_resolved',
}
_STATE_RECEIPT_RECORDS = {
    'blocker_added': ('blk_', frozenset({'ACTIVE', 'RESOLVED'})),
    'blocker_resolved': ('blk_', frozenset({'RESOLVED'})),
    'milestone_set': ('mil_', frozenset({'PLANNED', 'ACTIVE', 'BLOCKED', 'COMPLETED', 'CANCELLED'})),
    'work_item_added': ('wrk_', frozenset({'TODO', 'ACTIVE', 'BLOCKED', 'DONE', 'DROPPED'})),
    'objective_set': ('obj_', frozenset({'ACTIVE'})),
    'requirement_added': ('req_', frozenset({'ACTIVE', 'RESOLVED', 'CANCELLED'})),
    'requirement_resolved': ('req_', frozenset({'RESOLVED'})),
}
_REVIEW_REASONS = frozenset({
    'LIFECYCLE_TARGET_UNKNOWN', 'REVIEW_REQUIRED', 'MODEL_PROPOSAL',
    'LOW_EVIDENCE_COMMITMENT', 'SCOPE_ERROR', 'DEGRADED',
    'HUMAN_APPROVAL_REQUIRED',
})
_REVIEW_SOURCE_FIELDS = frozenset({'client', 'session_hash', 'evidence_id', 'role'})


class WorkerProcessingError(RuntimeError):
    """A content-free processing failure that must keep the queue retryable."""

    def __init__(self, code: str):
        self.code = code if isinstance(code, str) and code else "WORKER_PROCESSING_FAILED"
        super().__init__(self.code)


def _memory_candidate_values(candidate, *, approved=False, target_id=None):
    """Build the exact TruthCandidate payload used for a memory operation."""
    values = {key: value for key, value in candidate.items()
              if key in {'candidate_id', 'content', 'memory_type', 'scope', 'project_id',
                         'commitment', 'confidence', 'evidence_refs'}}
    values['confidence'] = max(values.get('confidence', 0), 0.97) if approved else values.get('confidence', 0)
    values['commitment'] = 'COMMITTED' if approved else values.get('commitment', 'UNCERTAIN')
    if target_id:
        values.update(operation='SUPERSEDE_EXISTING', target_memory_id=target_id,
                      successor_memory_id=identity('mem_', candidate.get('candidate_id'), target_id)[:30])
    return values


def _validate_cursor(value):
    """Validate the content-free transcript cursor persisted in receipts."""
    if not isinstance(value, dict) or set(value) != {'offset', 'prefix_hash', 'has_more'}:
        raise WorkerProcessingError('CAPTURE_CURSOR_CORRUPT')
    if isinstance(value['offset'], bool) or not isinstance(value['offset'], int) or value['offset'] < 0:
        raise WorkerProcessingError('CAPTURE_CURSOR_CORRUPT')
    if not isinstance(value['prefix_hash'], str) or len(value['prefix_hash']) != 64 or any(
        char not in '0123456789abcdef' for char in value['prefix_hash']
    ):
        raise WorkerProcessingError('CAPTURE_CURSOR_CORRUPT')
    if not isinstance(value['has_more'], bool):
        raise WorkerProcessingError('CAPTURE_CURSOR_CORRUPT')
    return {'offset': value['offset'], 'prefix_hash': value['prefix_hash'], 'has_more': value['has_more']}


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
    from scripts.capture_safety import evaluate_capture
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
    values = _memory_candidate_values(candidate, approved=approved, target_id=target_id)
    if target_id:
        values['successor_memory_id'] = identity('mem_', op_id)[:30]
    result = MemoryTruthEngine(vault).process([values], commit=True, commit_new=True, expected_revision=expected_revision, operation_id=op_id)
    return result.to_dict()


class Worker:
    def __init__(self, vault):
        self.vault = Path(vault).resolve()
        self.config = RuntimeConfig(vault)
        self.queue = CaptureQueue(vault)
        self.review = ReviewStore(vault)

    def _add_review(self, candidate, reason, source):
        """Persist a review item and suppress terminal fingerprint replays.

        A pending item is a receipt effect for the current job.  If the same
        candidate was already rejected, expired or accepted, the terminal
        audit record is returned by ``ReviewStore`` but must not be counted as
        a new effect in this job.
        """
        review_id = self.review.add(candidate, reason, source)
        if not review_id:
            raise WorkerProcessingError('REVIEW_PERSIST_FAILED')
        item = read_json(self.review.path(review_id))
        if not isinstance(item, dict):
            raise WorkerProcessingError('REVIEW_PERSIST_FAILED')
        if item.get('status') != 'PENDING':
            return None
        return review_id

    @contextmanager
    def _worker_lock(self):
        """Expose lock contention as a bounded, content-free worker result."""
        lock = file_lock(self.config.root / 'worker', timeout=1)
        try:
            lock.__enter__()
        except MemoryStoreLockTimeout:
            yield False
            return
        try:
            yield True
        finally:
            lock.__exit__(None, None, None)

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
        if (value.get('job_id') != job['job_id'] or value.get('event_id') != job['event']['event_id']
                or value.get('project_id') != job['event']['project']['project_id']):
            raise WorkerProcessingError('CAPTURE_RECEIPT_IDENTITY_MISMATCH')
        if value.get('status') != 'EFFECT_VERIFIED' or value.get('canonical_verified') is not True:
            raise WorkerProcessingError('CAPTURE_EFFECT_UNVERIFIED')
        for field in ('evidence_count', 'canonical_effect_count', 'review_effect_count'):
            if isinstance(value.get(field), bool) or not isinstance(value.get(field), int) or value[field] < 0:
                raise WorkerProcessingError('CAPTURE_RECEIPT_CORRUPT')
        effect_ids = value.get('effect_ids', [])
        if not isinstance(effect_ids, list) or len(effect_ids) > 10000 or not all(isinstance(item, str) and item for item in effect_ids):
            raise WorkerProcessingError('CAPTURE_RECEIPT_CORRUPT')
        for field in ('canonical_operation_ids', 'review_effect_ids'):
            items = value.get(field, [])
            if not isinstance(items, list) or len(items) > 10000 or not all(isinstance(item, str) and item for item in items):
                raise WorkerProcessingError('CAPTURE_RECEIPT_CORRUPT')
        if (len(value['canonical_operation_ids']) != value['canonical_effect_count']
                or len(value['review_effect_ids']) != value['review_effect_count']):
            raise WorkerProcessingError('CAPTURE_RECEIPT_CORRUPT')
        checkpoint_key = value.get('checkpoint_key')
        expected_checkpoint = self._checkpoint_for(job).name
        if checkpoint_key != expected_checkpoint:
            raise WorkerProcessingError('CAPTURE_RECEIPT_IDENTITY_MISMATCH')
        _validate_cursor(value.get('cursor'))
        if not self._verify_receipt_operations(job, value):
            raise WorkerProcessingError('CANONICAL_RECEIPT_MISMATCH')
        return value

    def _write_receipt(self, job, result):
        """Persist a content-free effect proof before acknowledging the queue job."""
        if result.get('status') != 'PROCESSED' or result.get('effect_verified') is not True:
            raise WorkerProcessingError('CAPTURE_EFFECT_UNVERIFIED')
        checkpoint_key = result.get('checkpoint_key')
        if checkpoint_key != self._checkpoint_for(job).name:
            raise WorkerProcessingError('CAPTURE_RECEIPT_IDENTITY_MISMATCH')
        cursor = _validate_cursor(result.get('cursor'))
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
            'canonical_operation_ids': list(result.get('canonical_operation_ids', []))[:10000],
            'review_effect_ids': list(result.get('review_effect_ids', []))[:10000],
            'checkpoint_key': checkpoint_key,
            'cursor': cursor,
            'at': now(),
        }
        if any(isinstance(receipt[field], bool) or receipt[field] < 0 for field in ('evidence_count', 'canonical_effect_count', 'review_effect_count')):
            raise WorkerProcessingError('CAPTURE_RECEIPT_INVALID')
        if (len(receipt['canonical_operation_ids']) != receipt['canonical_effect_count']
                or len(receipt['review_effect_ids']) != receipt['review_effect_count']):
            raise WorkerProcessingError('CAPTURE_RECEIPT_INVALID')
        write_json(self._receipt_path(job['job_id']), receipt)
        return receipt

    def _verify_receipt_operations(self, job, receipt):
        """Verify receipt operation identities and their surviving effects."""
        operation_ids = receipt.get('canonical_operation_ids', [])
        if not isinstance(operation_ids, list):
            return False
        review_ids = receipt.get('review_effect_ids', [])
        if not isinstance(review_ids, list):
            return False
        project_id = job['event']['project']['project_id']
        memory_doc = MemoryStore(self.vault).load()
        memory_receipts = memory_doc.get('operation_receipts', {})
        state_doc = StateStore(self.vault).load()
        state_receipts = state_doc.get('operation_receipts', {})
        memories = memory_doc.get('validated_memory', [])
        memory_by_id = {
            str(item.get('memory_id') or item.get('id')): item
            for item in memories if isinstance(item, dict) and (item.get('memory_id') or item.get('id'))
        }
        expected_effect_ids = []
        if (len(operation_ids) != len(set(operation_ids))
                or len(review_ids) != len(set(review_ids))):
            return False
        for operation_id in operation_ids:
            memory_receipt = memory_receipts.get(operation_id) if isinstance(memory_receipts, dict) else None
            if isinstance(memory_receipt, dict):
                decisions = memory_receipt.get('decisions')
                if not isinstance(decisions, list) or not decisions:
                    return False
                for decision in decisions:
                    if not isinstance(decision, dict):
                        return False
                    candidate_id = decision.get('candidate_id')
                    if (not isinstance(candidate_id, str)
                            or identity('op_', candidate_id, project_id) != operation_id):
                        return False
                    action = decision.get('action')
                    target = memory_by_id.get(decision.get('target_memory_id'))
                    successor = memory_by_id.get(decision.get('successor_memory_id'))
                    if any(
                        referenced is not None
                        and not self._memory_scope_allowed(referenced, project_id)
                        for referenced in (target, successor)
                    ):
                        return False
                    if action in {'NEW', 'SUPERSEDE_EXISTING'} and successor is None:
                        return False
                    if action in {'DUPLICATE', 'CONFIRM_EXISTING'} and target is None:
                        return False
                    if action == 'RESOLVE_EXISTING' and (target is None or str(target.get('status')).lower() != 'resolved'):
                        return False
                    if action == 'SUPERSEDE_EXISTING' and (target is None or str(target.get('status')).lower() != 'superseded'):
                        return False
                    if action in {'NEW', 'SUPERSEDE_EXISTING'}:
                        effect_id = decision.get('successor_memory_id')
                    elif action in {'DUPLICATE', 'CONFIRM_EXISTING', 'RESOLVE_EXISTING'}:
                        effect_id = decision.get('target_memory_id')
                    else:
                        return False
                    if not isinstance(effect_id, str) or not effect_id:
                        return False
                    expected_effect_ids.append(effect_id)
                continue
            state_receipt = state_receipts.get(operation_id) if isinstance(state_receipts, dict) else None
            if not isinstance(state_receipt, dict):
                return False
            if state_receipt.get('project_id') != project_id:
                return False
            record_ids = state_receipt.get('record_ids')
            if not isinstance(record_ids, list) or not record_ids:
                return False
            project = state_doc.get('projects', {}).get(project_id)
            if not isinstance(project, dict):
                return False
            if not self._state_receipt_records_valid(state_receipt, project, operation_id):
                return False
            for record_id in record_ids:
                if record_id not in receipt.get('effect_ids', []):
                    return False
                if not self._state_record_exists(project, record_id):
                    return False
            expected_effect_ids.extend(record_ids)
        for review_id in review_ids:
            try:
                item = read_json(self.review.path(review_id))
            except (OSError, ValueError, TypeError):
                return False
            if (not isinstance(item, dict) or item.get('id') != review_id
                    or item.get('status') not in {'PENDING', 'ACCEPTED', 'REJECTED', 'EXPIRED'}):
                return False
            source = item.get('source')
            if item.get('status') == 'PENDING':
                candidate = item.get('candidate')
                candidate_id = candidate.get('candidate_id') if isinstance(candidate, dict) else None
                candidate_project = candidate.get('project_id') if isinstance(candidate, dict) else None
                references = candidate.get('evidence_refs') if isinstance(candidate, dict) else None
            else:
                candidate = None
                candidate_id = item.get('candidate_id')
                candidate_project = item.get('project_id')
                references = item.get('evidence_refs')
            if (item.get('status') == 'PENDING' and not isinstance(candidate, dict)):
                return False
            if (candidate_project != project_id or not isinstance(candidate_id, str)
                    or identity('rev_', candidate_id, project_id) != review_id):
                return False
            evidence_id = source.get('evidence_id') if isinstance(source, dict) else None
            session_hash = source.get('session_hash') if isinstance(source, dict) else None
            if (not isinstance(source, dict)
                    or not isinstance(evidence_id, str)
                    or not re.fullmatch(r'evd_[a-f0-9]{32}', evidence_id)
                    or not isinstance(session_hash, str)
                    or not re.fullmatch(r'session_[a-f0-9]{64}', session_hash)):
                return False
            if item.get('reason') not in _REVIEW_REASONS or set(source) - _REVIEW_SOURCE_FIELDS:
                return False
            if source.get('client') not in {'claude', 'codex'} or source.get('role') not in {'user', 'assistant', 'tool', 'system'}:
                return False
            if (not isinstance(references, list) or not references or len(references) > 64
                    or len(references) != len(set(references))
                    or not all(isinstance(reference, str) and re.fullmatch(r'evd_[a-f0-9]{32}', reference)
                               for reference in references)
                    or evidence_id not in references):
                return False
            if any(field in item or (isinstance(candidate, dict) and field in candidate)
                   for field in ('raw_prompt', 'prompt_content', 'transcript_content', 'token')):
                return False
            duplicate_of = item.get('duplicate_of')
            if duplicate_of is not None and (not isinstance(duplicate_of, str)
                                              or not re.fullmatch(r'rev_[a-f0-9]{64}', duplicate_of)):
                return False
            expected_effect_ids.append(review_id)
        actual_effect_ids = receipt.get('effect_ids')
        if (not isinstance(actual_effect_ids, list)
                or len(actual_effect_ids) != len(expected_effect_ids)
                or sorted(actual_effect_ids) != sorted(expected_effect_ids)):
            return False
        return True

    @staticmethod
    def _state_record_exists(project, record_id):
        """Return whether a state receipt's record still exists in its project."""
        return Worker._state_record(project, record_id) is not None

    @staticmethod
    def _state_record(project, record_id):
        """Find one state record by ID, including the current objective/milestone."""
        if not isinstance(record_id, str) or not record_id:
            return None
        current = project.get('current') if isinstance(project, dict) else None
        if isinstance(current, dict):
            for record in current.values():
                if isinstance(record, dict) and record.get('id') == record_id:
                    return record
        if isinstance(project, dict):
            for collection in ('requirements', 'work_items', 'blockers', 'constraints', 'risks'):
                records = project.get(collection)
                if isinstance(records, list):
                    for record in records:
                        if isinstance(record, dict) and record.get('id') == record_id:
                            return record
        return None

    @staticmethod
    def _state_receipt_records_valid(receipt, project, operation_id=None):
        """Bind a semantic state operation to the surviving record kind/status."""
        operation = receipt.get('operation') if isinstance(receipt, dict) else None
        shape = _STATE_RECEIPT_RECORDS.get(operation)
        record_ids = receipt.get('record_ids') if isinstance(receipt, dict) else None
        if shape is None or not isinstance(record_ids, list) or not record_ids:
            return False
        prefix, statuses = shape
        for record_id in record_ids:
            record = Worker._state_record(project, record_id)
            source = record.get('source') if isinstance(record, dict) else None
            if (record is None or not isinstance(record_id, str) or not record_id.startswith(prefix)
                    or record.get('status') not in statuses
                    or (operation_id is not None
                        and (not isinstance(source, dict) or source.get('reference') != operation_id))):
                return False
        return True

    @staticmethod
    def _memory_scope_allowed(memory, project_id):
        """Allow global memory or memory explicitly scoped to this project."""
        if not isinstance(memory, dict):
            return False
        scope = memory.get('scope')
        if scope == 'global':
            return True
        return scope == 'project' and memory.get('project_id') == project_id

    def _checkpoint_for(self, job):
        event = job['event']
        session = event['session_id']
        client = session.split(':')[0]
        if client not in {'claude', 'codex'}:
            client = 'claude'
            session = 'claude:' + hashlib.sha256(session.encode()).hexdigest()
        return self.config.root / 'cursors' / (identity('src_', client, session, event['transcript_path']) + '.json')

    def _persist_checkpoint(self, job, checkpoint_key, cursor):
        checkpoint = self._checkpoint_for(job)
        if checkpoint_key != checkpoint.name:
            raise WorkerProcessingError('CAPTURE_CURSOR_IDENTITY_MISMATCH')
        write_json(checkpoint, _validate_cursor(cursor))

    def _verify_canonical_effect(self, candidate, outcome, operation_id):
        """Re-read the canonical transaction receipt before acknowledging work."""
        if not isinstance(outcome, dict) or outcome.get('status') != 'SUCCESS':
            return False
        if candidate.get('candidate_type') == 'STATE_MUTATION':
            state_doc = StateStore(self.vault).load()
            receipts = state_doc.get('operation_receipts', {})
            receipt = receipts.get(operation_id) if isinstance(receipts, dict) else None
            record_id = outcome.get('record_id')
            expected_hash = identity('request_', candidate, None)
            record_ids = receipt.get('record_ids') if isinstance(receipt, dict) else None
            expected_operation = _STATE_OPERATION_RECEIPTS.get(candidate.get('operation'))
            project = state_doc.get('projects', {}).get(candidate.get('project_id'))
            return (
                isinstance(receipt, dict)
                and receipt.get('project_id') == candidate.get('project_id')
                and receipt.get('operation') == expected_operation
                and receipt.get('request_hash') == expected_hash
                and isinstance(record_id, str)
                and isinstance(record_ids, list)
                and record_id in record_ids
                and self._state_receipt_records_valid(receipt, project, operation_id)
                and self._state_record_exists(project, record_id)
            )
        receipts = MemoryStore(self.vault).load().get('operation_receipts', {})
        receipt = receipts.get(operation_id) if isinstance(receipts, dict) else None
        decisions = outcome.get('decisions')
        try:
            values = _memory_candidate_values(candidate)
            expected_hash = identity('request_', [asdict(TruthCandidate.from_mapping(values))])
        except (TypeError, ValueError):
            return False
        stored_decisions = receipt.get('decisions') if isinstance(receipt, dict) else None
        if not (isinstance(receipt, dict) and receipt.get('request_hash') == expected_hash
                and isinstance(stored_decisions, list) and isinstance(decisions, list)
                and stored_decisions == decisions and decisions):
            return False
        memories = MemoryStore(self.vault).load().get('validated_memory', [])
        memory_by_id = {
            str(item.get('memory_id') or item.get('id')): item
            for item in memories if isinstance(item, dict) and (item.get('memory_id') or item.get('id'))
        }
        for item in decisions:
            if not (isinstance(item, dict) and item.get('candidate_id') == candidate.get('candidate_id')
                    and isinstance(item.get('action'), str)):
                return False
            if identity('op_', item['candidate_id'], candidate.get('project_id')) != operation_id:
                return False
            action = item['action']
            target = memory_by_id.get(item.get('target_memory_id'))
            successor = memory_by_id.get(item.get('successor_memory_id'))
            if any(
                referenced is not None
                and not self._memory_scope_allowed(referenced, candidate.get('project_id'))
                for referenced in (target, successor)
            ):
                return False
            if action in {'NEW', 'SUPERSEDE_EXISTING'} and successor is None:
                return False
            if action == 'DUPLICATE' and target is None:
                return False
            if action == 'CONFIRM_EXISTING' and target is None:
                return False
            if action == 'RESOLVE_EXISTING' and (target is None or str(target.get('status')).lower() != 'resolved'):
                return False
            if action == 'SUPERSEDE_EXISTING' and (target is None or str(target.get('status')).lower() != 'superseded'):
                return False
        return all(
            isinstance(item, dict) and item.get('candidate_id') == candidate.get('candidate_id')
            and isinstance(item.get('action'), str)
            for item in decisions
        )

    def once(self):
        self.config.root.mkdir(parents=True, exist_ok=True)
        with self._worker_lock() as lock_acquired:
            if not lock_acquired:
                result = {'status': 'DEGRADED', 'error': 'WORKER_LOCK_TIMEOUT'}
                write_json(self.config.root / 'last-worker.json', {'at': now(), **result})
                return result
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
                    self._persist_checkpoint(job, prior_receipt['checkpoint_key'], prior_receipt['cursor'])
                    result = {
                        'status': 'PROCESSED',
                        'job_id': job['job_id'],
                        'messages': 0,
                        'effects': prior_receipt['canonical_effect_count'],
                        'evidence_count': prior_receipt['evidence_count'],
                        'canonical_effect_count': prior_receipt['canonical_effect_count'],
                        'review_effect_count': prior_receipt['review_effect_count'],
                        'effect_ids': prior_receipt['effect_ids'],
                        'canonical_operation_ids': prior_receipt['canonical_operation_ids'],
                        'review_effect_ids': prior_receipt['review_effect_ids'],
                        'effect_verified': True,
                        'receipt_replayed': True,
                        'has_more': False,
                        'checkpoint_key': prior_receipt['checkpoint_key'],
                        'cursor': prior_receipt['cursor'],
                    }
                else:
                    result = self.process(job)
                parts = [result]
                while parts[-1].get('has_more', False):
                    if self.config.load()['mode'] == 'OFF':
                        raise WorkerProcessingError('RUNTIME_STOPPED')
                    parts.append(self.process(job, cursor_override=parts[-1].get('cursor')))
                result = {
                    **parts[-1],
                    'messages': sum(int(part.get('messages', 0)) for part in parts),
                    'effects': sum(int(part.get('effects', 0)) for part in parts),
                    'evidence_count': sum(int(part.get('evidence_count', 0)) for part in parts),
                    'canonical_effect_count': sum(int(part.get('canonical_effect_count', 0)) for part in parts),
                    'review_effect_count': sum(int(part.get('review_effect_count', 0)) for part in parts),
                    'effect_ids': [effect_id for part in parts for effect_id in part.get('effect_ids', [])],
                    'canonical_operation_ids': [operation_id for part in parts for operation_id in part.get('canonical_operation_ids', [])],
                    'review_effect_ids': [effect_id for part in parts for effect_id in part.get('review_effect_ids', [])],
                    'effect_verified': all(part.get('effect_verified') is True for part in parts),
                }
                if result.get('status') != 'PROCESSED':
                    raise WorkerProcessingError(str(result.get('status') or 'WORKER_PROCESSING_FAILED'))
                self._write_receipt(job, result)
                self._persist_checkpoint(job, result['checkpoint_key'], result['cursor'])
                self.queue.commit(job['job_id'])
                write_json(self.config.root / 'last-worker.json', {'at': now(), **result})
                return result
            except Exception as exc:
                # Exceptions may contain source text or paths: never serialize them.
                code = getattr(exc, 'code', None) or (
                    'CANONICAL_CONFLICT' if isinstance(exc, (MemoryStoreConflict, StateStoreConflict))
                    else 'EVIDENCE_INVALID' if isinstance(exc, (ValueError, UnicodeError))
                    else 'WORKER_FAILED'
                )
                receipt = self.queue.retry_or_dead_letter(job['job_id'], error_code=code)
                result = {'status': receipt.status, 'error': code, 'job_id': job['job_id']}
                write_json(self.config.root / 'last-worker.json', {'at': now(), **result})
                return result
            finally:
                stop.set()
                thread.join(timeout=2)

    def process(self, job, *, cursor_override=None):
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
        checkpoint = self._checkpoint_for(job)
        stored_cursor = read_json(checkpoint) if cursor_override is None else cursor_override
        if stored_cursor is not None:
            stored_cursor = _validate_cursor(stored_cursor)
        try:
            batch, cursor = read_increment(self.vault, event['transcript_path'], client, session,
                                           project['project_id'], event['event_at'], stored_cursor)
        except FileNotFoundError as exc:
            raise WorkerProcessingError('TRANSCRIPT_NOT_FOUND') from exc
        except OSError as exc:
            raise WorkerProcessingError('EVIDENCE_IO_FAILED') from exc
        cursor = _validate_cursor(cursor)
        EvidenceStore(self.vault).persist(batch.records)
        outcomes = []
        effect_ids = []
        canonical_operation_ids = []
        review_effect_ids = []
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
                config = self.config.load()
                requires_review = (config.get('b1_human_approval', False) or correction
                                   or candidate.get('operation', '').startswith('RESOLVE')
                                   or message.record.role != 'user')
                if requires_review or config['mode'] == 'SHADOW':
                    reason = ('LIFECYCLE_TARGET_UNKNOWN' if correction else
                              'HUMAN_APPROVAL_REQUIRED' if config.get('b1_human_approval', False) else
                              'REVIEW_REQUIRED')
                    review_id = self._add_review(candidate, reason, source)
                    if review_id:
                        effect_ids.append(review_id)
                        review_effect_ids.append(review_id)
                        review_effect_count += 1
                    continue
                if self.config.load()['mode'] not in {'CANARY', 'ACTIVE'}:
                    raise ValueError('Runtime stopped during processing')
                op_id = identity('op_', candidate['candidate_id'], candidate['project_id'])
                outcome = apply_candidate(self.vault, candidate, op_id=op_id)
                if outcome['status'] == 'SUCCESS':
                    if not self._verify_canonical_effect(candidate, outcome, op_id):
                        raise WorkerProcessingError('CANONICAL_EFFECT_UNVERIFIED')
                    if candidate.get('candidate_type') == 'STATE_MUTATION':
                        record_id = outcome.get('record_id')
                        if not isinstance(record_id, str) or not record_id:
                            raise WorkerProcessingError('CANONICAL_RECEIPT_INVALID')
                        effect_ids.append(record_id)
                    else:
                        decisions = outcome.get('decisions', [])
                        if not isinstance(decisions, list):
                            raise WorkerProcessingError('CANONICAL_RECEIPT_INVALID')
                        effect_ids.extend(
                            str(item.get('successor_memory_id') or item.get('target_memory_id') or item.get('candidate_id'))
                            for item in decisions if isinstance(item, dict)
                        )
                    canonical_effect_count += 1
                    canonical_operation_ids.append(op_id)
                    write_json(self.config.root / 'capture-observations' / (op_id + '.json'), {'operation_id':op_id, 'project_id':project['project_id'],
                               'client':client, 'role':message.record.role, 'evidence_id':message.record.evidence_id, 'at':now()})
                if outcome['status'] not in {'SUCCESS', 'EMPTY'}:
                    if outcome['status'] in {'REVIEW_REQUIRED', 'SCOPE_ERROR', 'DEGRADED'}:
                        review_id = self._add_review(candidate, outcome['status'], source)
                        if review_id:
                            effect_ids.append(review_id)
                            review_effect_ids.append(review_id)
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
                    review_id = self._add_review(candidate, 'LOW_EVIDENCE_COMMITMENT', source)
                    if review_id:
                        effect_ids.append(review_id)
                        review_effect_ids.append(review_id)
                        review_effect_count += 1
            proposals, model_error = propose(self.config.load().get('local_model'), message)
            if model_error:
                write_json(self.config.root / 'model-status.json', {'at': now(), 'status': model_error})
            for index, item in enumerate(proposals):
                candidate = {**item, 'candidate_id': identity('cand_', message.record.evidence_id, 'model', index), 'candidate_type': 'NEW_MEMORY',
                             'project_id': project['project_id'], 'scope': 'project', 'commitment': 'PROPOSED', 'confidence': 0,
                             'evidence_refs': [message.record.evidence_id]}
                review_id = self._add_review(candidate, 'MODEL_PROPOSAL', source)
                if review_id:
                    effect_ids.append(review_id)
                    review_effect_ids.append(review_id)
                    review_effect_count += 1
        return {
            'status': 'PROCESSED',
            'job_id': job['job_id'],
            'messages': len(batch.messages),
            'effects': len(outcomes),
            'evidence_count': len(batch.records),
            'canonical_effect_count': canonical_effect_count,
            'review_effect_count': review_effect_count,
            'effect_ids': effect_ids,
            'canonical_operation_ids': canonical_operation_ids,
            'review_effect_ids': review_effect_ids,
            'effect_verified': True,
            'has_more': cursor['has_more'],
            'checkpoint_key': checkpoint.name,
            'cursor': cursor,
        }
