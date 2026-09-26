"""The worker pairs an approval turn with the assistant proposal from the previous increment."""

import json

from brain_eleven.runtime.review import ReviewStore
from brain_eleven.runtime.storage import RuntimeConfig
from brain_eleven.runtime.worker import Worker, enqueue
from tests.test_pre13_runtime import _native_path, runtime  # noqa: F401  (fixture)

PROPOSAL = "Bundan sonra her PR'da tam test takımını çalıştıracağız."


def _turn(role, text):
    return {'type': role, 'sessionId': 'approve', 'message': {'role': role, 'content': text}}


def _pending(vault):
    return [x for x in ReviewStore(vault)._items() if x.get('status') == 'PENDING']


def test_approval_in_next_increment_turns_the_proposal_into_a_review_candidate(runtime, tmp_path):  # noqa: F811
    vault, _ = runtime
    RuntimeConfig(vault).set_mode('SHADOW')
    path = _native_path(tmp_path, vault, 'claude', 'approve', [_turn('assistant', PROPOSAL)])
    enqueue(vault, 'claude', {'cwd': str(vault), 'session_id': 'approve', 'transcript_path': str(path)})
    assert Worker(vault).once()['status'] == 'PROCESSED'
    assert _pending(vault) == []  # an unapproved assistant proposal never reaches review

    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(_turn('user', 'Tamam, öyle yapalım.')) + '\n')
    enqueue(vault, 'claude', {'cwd': str(vault), 'session_id': 'approve', 'transcript_path': str(path)})
    assert Worker(vault).once()['status'] == 'PROCESSED'

    pending = _pending(vault)
    assert [x['candidate']['content'] for x in pending] == [PROPOSAL]
    assert pending[0]['candidate']['commitment'] == 'COMMITTED'
    assert len(pending[0]['candidate']['evidence_refs']) == 2


def test_approval_without_a_preceding_proposal_adds_nothing_new(runtime, tmp_path):  # noqa: F811
    vault, _ = runtime
    RuntimeConfig(vault).set_mode('SHADOW')
    path = _native_path(tmp_path, vault, 'claude', 'approve', [_turn('user', 'Merhaba.')])
    enqueue(vault, 'claude', {'cwd': str(vault), 'session_id': 'approve', 'transcript_path': str(path)})
    Worker(vault).once()
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(_turn('user', 'tamam')) + '\n')
    enqueue(vault, 'claude', {'cwd': str(vault), 'session_id': 'approve', 'transcript_path': str(path)})
    assert Worker(vault).once()['status'] == 'PROCESSED'
    assert all(len(x['candidate'].get('evidence_refs', [])) < 2 for x in _pending(vault))
