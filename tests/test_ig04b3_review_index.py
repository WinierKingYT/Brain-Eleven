"""Content-free review metadata index for the IG04-B3 SessionStart nudge."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import brain_eleven.runtime.review as review_module
from brain_eleven.runtime.review import ReviewStore
from brain_eleven.runtime.storage import read_json, runtime_file_lock, write_json


@pytest.fixture
def review_store(tmp_path):
    vault = tmp_path / 'vault'
    vault.mkdir()
    return vault, ReviewStore(vault)


def _candidate(project_id, candidate_id, content, evidence):
    return {
        'candidate_id': candidate_id,
        'candidate_type': 'NEW_MEMORY',
        'project_id': project_id,
        'scope': 'project',
        'memory_type': 'decision',
        'commitment': 'COMMITTED',
        'confidence': 0.8,
        'evidence_refs': [evidence],
        'content': content,
    }


def _add(store, project_id, candidate_id, content, evidence):
    return store.add(
        _candidate(project_id, candidate_id, content, evidence),
        'HUMAN_APPROVAL_REQUIRED',
        {'client': 'claude', 'evidence_id': evidence, 'role': 'user'},
    )


def test_pending_count_matches_project_scoped_b2_visible_groups(review_store):
    _, store = review_store
    _add(store, 'project-a', 'cand-a1', 'Same content', 'evd-a1')
    _add(store, 'project-a', 'cand-a2', 'Same content', 'evd-a2')
    _add(store, 'project-a', 'cand-a3', 'Different content', 'evd-a3')
    _add(store, 'project-b', 'cand-b1', 'Same content', 'evd-b1')

    assert store.pending_visible_count('project-a') == 2
    assert store.pending_visible_count('project-b') == 1
    assert store.pending_visible_count('project-c') == 0


def test_pending_count_never_opens_review_records_or_calls_mutating_paths(review_store, monkeypatch):
    _, store = review_store
    _add(store, 'project-a', 'cand-a1', 'Candidate text stays private', 'evd-a1')
    original_read_json = review_module.read_json

    def read_index_only(path, default=None):
        assert not Path(path).name.startswith('rev_')
        return original_read_json(path, default)

    monkeypatch.setattr(review_module, 'read_json', read_index_only)
    monkeypatch.setattr(store, 'list', lambda: pytest.fail('pending count must not list candidates'))
    monkeypatch.setattr(store, 'expire', lambda: pytest.fail('pending count must not expire candidates'))

    assert store.pending_visible_count('project-a') == 1


def test_missing_review_directory_is_known_empty_without_creating_it(tmp_path):
    vault = tmp_path / 'vault'
    vault.mkdir()
    runtime_root = vault / '.brain-eleven' / 'runtime'
    runtime_root.mkdir(parents=True)
    store = ReviewStore(vault)

    assert store.pending_visible_count('project-a') == 0
    assert not store.root.exists()


def test_index_with_unapproved_fields_is_unknown(review_store):
    _, store = review_store
    _add(store, 'project-a', 'cand-a1', 'Private candidate text', 'evd-a1')
    index = read_json(store.pending_index_path)
    entry = index['entries'][next(iter(index['entries']))]
    entry['candidate_text'] = 'Private candidate text'
    write_json(store.pending_index_path, index)

    assert store.pending_visible_count('project-a') is None


def test_expiry_is_applied_per_record_and_reflected_in_metadata_index(review_store):
    _, store = review_store
    review_id = _add(store, 'project-a', 'cand-a1', 'Expiring content', 'evd-a1')
    assert store.pending_visible_count(
        'project-a', at=datetime.now(timezone.utc) + timedelta(days=8)
    ) == 0
    record = read_json(store.path(review_id))
    record['expires_at'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    write_json(store.path(review_id), record)
    store.expire()

    assert read_json(store.path(review_id))['status'] == 'EXPIRED'
    assert store.pending_visible_count('project-a') == 0


def test_group_terminalization_updates_visible_count(review_store):
    _, store = review_store
    first = _add(store, 'project-a', 'cand-a1', 'Same content', 'evd-a1')
    _add(store, 'project-a', 'cand-a2', 'Same content', 'evd-a2')
    item = read_json(store.path(first))

    with runtime_file_lock(store.root / 'index'):
        store.finish(item, 'REJECTED')

    assert store.pending_visible_count('project-a') == 0


def test_interrupted_add_fails_closed_until_review_path_rebuilds_index(review_store, monkeypatch):
    _, store = review_store
    _add(store, 'project-a', 'cand-a1', 'Existing content', 'evd-a1')
    original_write_json = review_module.write_json

    def fail_index_publication(path, value):
        if Path(path) == store.pending_index_path:
            raise OSError('simulated crash before index publication')
        return original_write_json(path, value)

    monkeypatch.setattr(review_module, 'write_json', fail_index_publication)
    with pytest.raises(OSError, match='simulated crash'):
        _add(store, 'project-a', 'cand-a2', 'New content', 'evd-a2')

    assert store.index_intent_path.exists()
    intent = read_json(store.index_intent_path)
    assert intent['operation'] == 'ADD'
    assert intent['target_index']['generation'] == read_json(store.pending_index_path)['generation'] + 1
    assert len(intent['target_index']['entries']) == 2
    original_read_json = review_module.read_json

    def count_without_candidate_access(path, default=None):
        assert not Path(path).name.startswith('rev_')
        return original_read_json(path, default)

    monkeypatch.setattr(review_module, 'read_json', count_without_candidate_access)
    assert store.pending_visible_count('project-a') is None

    monkeypatch.setattr(review_module, 'write_json', original_write_json)
    monkeypatch.setattr(review_module, 'read_json', original_read_json)
    visible = [item for item in store.list() if item['status'] == 'PENDING']
    assert len(visible) == 2
    assert not store.index_intent_path.exists()
    assert store.pending_visible_count('project-a') == 2


def test_interrupted_record_write_leaves_no_phantom_count_and_recovers(review_store, monkeypatch):
    _, store = review_store
    _add(store, 'project-a', 'cand-a1', 'Existing content', 'evd-a1')
    original_write_json = review_module.write_json

    def fail_record_write(path, value):
        if Path(path).name.startswith('rev_'):
            raise OSError('simulated crash before queue record write')
        return original_write_json(path, value)

    monkeypatch.setattr(review_module, 'write_json', fail_record_write)
    with pytest.raises(OSError, match='before queue record'):
        _add(store, 'project-a', 'cand-a2', 'Unwritten content', 'evd-a2')

    assert store.index_intent_path.exists()
    assert store.pending_visible_count('project-a') is None
    monkeypatch.setattr(review_module, 'write_json', original_write_json)

    visible = [item for item in store.list() if item['status'] == 'PENDING']
    assert len(visible) == 1
    assert not store.index_intent_path.exists()
    assert store.pending_visible_count('project-a') == 1


def test_interrupted_after_index_publication_recovery_is_generation_idempotent(review_store, monkeypatch):
    _, store = review_store
    original_unlink = Path.unlink
    fail_once = {'armed': True}

    def fail_intent_unlink(path, *args, **kwargs):
        if path == store.index_intent_path and fail_once['armed']:
            fail_once['armed'] = False
            raise OSError('simulated crash before intent removal')
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'unlink', fail_intent_unlink)
    with pytest.raises(OSError, match='before intent removal'):
        _add(store, 'project-a', 'cand-a1', 'Published content', 'evd-a1')

    assert store.index_intent_path.exists()
    assert store.pending_visible_count('project-a') is None
    published_generation = read_json(store.pending_index_path)['generation']

    monkeypatch.setattr(Path, 'unlink', original_unlink)
    store.list()
    assert not store.index_intent_path.exists()
    assert read_json(store.pending_index_path)['generation'] == published_generation
    assert store.pending_visible_count('project-a') == 1


def test_interrupted_group_transition_rebuilds_index_from_surviving_records(review_store, monkeypatch):
    _, store = review_store
    first = _add(store, 'project-a', 'cand-a1', 'Same content', 'evd-a1')
    second = _add(store, 'project-a', 'cand-a2', 'Same content', 'evd-a2')
    item = read_json(store.path(first))
    original_write_json = review_module.write_json

    def fail_second_record(path, value):
        if Path(path) == store.path(second):
            raise OSError('simulated crash midway through grouped transition')
        return original_write_json(path, value)

    monkeypatch.setattr(review_module, 'write_json', fail_second_record)
    with runtime_file_lock(store.root / 'index'), pytest.raises(OSError, match='midway'):
        store.finish(item, 'REJECTED')

    assert store.pending_visible_count('project-a') is None
    monkeypatch.setattr(review_module, 'write_json', original_write_json)
    visible = store.list()
    assert not store.index_intent_path.exists()
    statuses = {
        read_json(store.path(first))['status'],
        read_json(store.path(second))['status'],
    }
    assert statuses == {'REJECTED', 'PENDING'}
    assert store.pending_visible_count('project-a') == 1
    assert sum(record['status'] == 'PENDING' for record in visible) == 1


def test_legacy_queue_is_reindexed_only_by_review_list_not_by_count(review_store):
    _, store = review_store
    _add(store, 'project-a', 'cand-a1', 'Legacy content', 'evd-a1')
    store.pending_index_path.unlink()

    assert store.pending_visible_count('project-a') is None
    assert not store.pending_index_path.exists()

    _add(store, 'project-a', 'cand-a2', 'New content after migration', 'evd-a2')
    store.expire()
    assert not store.pending_index_path.exists()
    assert store.pending_visible_count('project-a') is None

    store.list()
    assert store.pending_index_path.exists()
    assert store.pending_visible_count('project-a') == 2


def test_index_and_intent_contain_no_candidate_text_or_paths(review_store):
    vault, store = review_store
    text = 'Private candidate content 3c69166b'
    _add(store, 'project-a', 'cand-a1', text, 'evd-a1')

    index_text = store.pending_index_path.read_text(encoding='utf-8')
    assert text not in index_text
    assert str(vault) not in index_text

    # Exercise a durable pending intent without changing any candidate bytes.
    index = json.loads(index_text)
    entry = index['entries'][next(iter(index['entries']))]
    write_json(store.index_intent_path, {
        'schema_version': 1,
        'operation': 'TEST',
        'base_generation': index['generation'],
        'target_generation': index['generation'] + 1,
        'changes': {'rev_' + 'a' * 64: entry},
    })
    intent_text = store.index_intent_path.read_text(encoding='utf-8')
    assert text not in intent_text
    assert str(vault) not in intent_text


def test_path_like_project_id_is_rejected_before_index_or_candidate_write(review_store):
    vault, store = review_store
    path_id = str(vault / "private-project-root")

    result = store.add(
        _candidate(path_id, "path-id-candidate", "Safe candidate text", "path-id-evidence"),
        "HUMAN_APPROVAL_REQUIRED",
        {"client": "claude", "evidence_id": "path-id-evidence", "role": "user"},
    )

    assert result is None
    assert not list(store.root.glob("rev_*.json"))
    assert store.pending_index_path.exists()
    index_text = store.pending_index_path.read_text(encoding="utf-8")
    assert path_id not in index_text
    assert store._valid_index({
        "schema_version": 1,
        "ready": True,
        "generation": 0,
        "entries": {
            "rev_" + "a" * 64: {
                "project_id": path_id,
                "status": "PENDING",
                "expires_at": "2026-09-24T00:00:00+00:00",
                "content_fingerprint": "fp_" + "b" * 64,
            },
        },
    }) is False
