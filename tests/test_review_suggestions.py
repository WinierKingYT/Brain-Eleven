"""Model verdicts: ACCEPT is applied with an audit note, REJECT only hides (reversible)."""

from fastapi.testclient import TestClient

from brain_eleven.memory import MemoryStore
from brain_eleven.runtime.review import ReviewStore
from brain_eleven.runtime.service import create_app
from brain_eleven.runtime.storage import RuntimeConfig, write_json
from brain_eleven.runtime.value import apply_suggestions, load_suggestions
from tests.test_memclaim01_claim_key import NEW_TIME, _review_item, _runtime


def _write(vault, suggestions):
    write_json(RuntimeConfig(vault).root / 'review-suggestions.json',
               {'by': 'gpt-luna', 'suggestions': suggestions})


def test_load_keeps_only_known_verdicts_and_ids(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    good = 'rev_' + 'a' * 64
    _write(vault, {good: {'suggestion': 'ACCEPT', 'reason': 'DURABLE_DECISION', 'text': 'leak'},
                   'bad-id': {'suggestion': 'ACCEPT'},
                   'rev_' + 'b' * 64: {'suggestion': 'DELETE_EVERYTHING'},
                   'rev_' + 'c' * 64: {'suggestion': 'DUPLICATE_OF:' + good, 'reason': 'lower case!'}})
    loaded = load_suggestions(vault)
    assert set(loaded) == {good, 'rev_' + 'c' * 64}
    assert 'leak' not in str(loaded) and loaded['rev_' + 'c' * 64]['reason'] == ''
    assert loaded['rev_' + 'c' * 64] == {'suggestion': 'DUPLICATE', 'reason': '', 'duplicate_of': good, 'by': 'gpt-luna'}


def test_apply_accepts_with_note_and_only_hides_rejects(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    keep = _review_item(tmp_path, vault, "keep", "We decided the dashboard stays read-only.", NEW_TIME)
    drop = _review_item(tmp_path, vault, "drop", "We decided to keep SQLite for storage.", NEW_TIME)
    _write(vault, {keep['id']: {'suggestion': 'ACCEPT', 'reason': 'DURABLE_DECISION'},
                   drop['id']: {'suggestion': 'REJECT', 'reason': 'TRANSIENT'}})

    dry = apply_suggestions(vault)
    assert (dry['dry_run'], dry['accepted'], dry['hidden']) == (True, 1, 1)
    assert all(x['status'] == 'PENDING' for x in ReviewStore(vault)._items())

    done = apply_suggestions(vault, apply=True)
    assert (done['accepted'], done['hidden'], done['failed']) == (1, 1, 0)
    by_id = {x['id']: x for x in ReviewStore(vault)._items()}
    assert by_id[keep['id']]['status'] == 'ACCEPTED'
    assert by_id[keep['id']]['decision_note'] == 'Model onayı (gpt-luna): DURABLE_DECISION'
    assert by_id[drop['id']]['status'] == 'PENDING'  # reversible: not rejected, just hidden
    assert 'We decided the dashboard stays read-only.' in {m['content'] for m in MemoryStore(vault).load()['validated_memory']}

    client = TestClient(create_app(vault, token='t', background=False), base_url='http://127.0.0.1')
    listed = {x['id']: x for x in client.get('/api/review/candidates', headers={'Authorization': 'Bearer t'}).json()['candidates']}
    assert listed[drop['id']]['suggestion']['suggestion'] == 'REJECT'
