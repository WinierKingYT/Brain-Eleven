"""Owner notice and digest (owner decision 2026-09-30, step 6)."""

from brain_eleven.runtime.storage import RuntimeConfig, write_json
from brain_eleven.runtime.value import digest, owner_notice, refresh_owner_counts
from tests.test_memclaim01_claim_key import NEW_TIME, _accept, _review_item, _runtime


def _suggest(vault, entries):
    write_json(RuntimeConfig(vault).root / 'review-suggestions.json', {'by': 'test', 'suggestions': entries})


def test_notice_counts_items_left_for_the_owner_and_skips_hidden_ones(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    keep = _review_item(tmp_path, vault, 'keep', 'We decided to use SQLite because the app is local.', NEW_TIME)
    hidden = _review_item(tmp_path, vault, 'hidden', 'We decided the dashboard stays read-only for now.', NEW_TIME)
    fresh = _review_item(tmp_path, vault, 'fresh', 'We decided the importer stays manual this quarter.', NEW_TIME)
    assert owner_notice(vault) == ''  # nothing computed yet

    _suggest(vault, {keep['id']: {'suggestion': 'REVIEW', 'reason': 'MODEL_ACCEPT'},
                     hidden['id']: {'suggestion': 'REJECT', 'reason': 'TRANSIENT'}})
    refresh_owner_counts(vault)

    notice = owner_notice(vault)
    assert '2 review candidates wait' in notice
    assert '1 suggested for acceptance by the model, 1 not evaluated yet' in notice
    listed = digest(vault)
    assert [x['id'] for x in listed['top']][0] == keep['id'] and listed['top'][0]['model_accept'] is True
    assert hidden['id'] not in {x['id'] for x in listed['top']} and fresh['id'] in {x['id'] for x in listed['top']}


def test_bootstrap_carries_the_notice_without_scanning_the_review_store(tmp_path, monkeypatch):
    from brain_eleven.runtime.context import compile_bootstrap
    from brain_eleven.runtime.review import ReviewStore
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    _accept(vault, _review_item(tmp_path, vault, 'kept', 'We decided alpha is delivered at session start.', NEW_TIME))
    keep = _review_item(tmp_path, vault, 'keep', 'We decided to use SQLite because the app is local.', NEW_TIME)
    _suggest(vault, {keep['id']: {'suggestion': 'REVIEW', 'reason': 'MODEL_ACCEPT'}})
    refresh_owner_counts(vault)

    def no_scan(self):
        raise AssertionError('SessionStart must not list the review store')

    monkeypatch.setattr(ReviewStore, 'list', no_scan)
    result = compile_bootstrap(vault, vault)

    assert '## Owner action' in result['context'] and 'python -m brain_eleven digest' in result['context']


def test_no_notice_without_memories(tmp_path):
    from brain_eleven.runtime.context import compile_bootstrap
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    keep = _review_item(tmp_path, vault, 'keep', 'We decided to use SQLite because the app is local.', NEW_TIME)
    _suggest(vault, {keep['id']: {'suggestion': 'REVIEW', 'reason': 'MODEL_ACCEPT'}})
    refresh_owner_counts(vault)

    result = compile_bootstrap(vault, vault)

    # The state section alone may still be delivered (unchanged behavior);
    # the notice never rides on a bootstrap without memories.
    assert '## Owner action' not in result['context'] and result['selected_ids'] == []


def test_stale_counts_are_not_shown(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    write_json(RuntimeConfig(vault).root / 'owner-notice.json', {
        'at': '2026-01-01T00:00:00+00:00', 'projects': {'': {'waiting': 3, 'model_accept': 1,
                                                          'not_evaluated': 0, 'audit': 0}}})
    assert owner_notice(vault) == ''


def test_map_profile_lists_topic_notes_instead_of_record_text(tmp_path):
    from brain_eleven.memory import MemoryStore
    from brain_eleven.runtime.context import compile_bootstrap
    from brain_eleven.runtime.memory_notes import set_topic
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    _accept(vault, _review_item(tmp_path, vault, 'kept', 'We decided alpha is delivered at session start.', NEW_TIME))
    _accept(vault, _review_item(tmp_path, vault, 'other', 'We decided the importer stays manual this quarter.', NEW_TIME))
    RuntimeConfig(vault).set_context_profile('map')

    without_topics = compile_bootstrap(vault, vault)['context']
    assert 'alpha is delivered' in without_topics and 'TOPIC NOTES' not in without_topics  # nothing to map yet

    first = next(m['memory_id'] for m in MemoryStore(vault).load()['validated_memory'] if 'alpha' in m['content'])
    set_topic(vault, [first], 'Teslimat')
    result = compile_bootstrap(vault, vault)
    assert result['status'] == 'SUCCESS' and result['selected_ids'] == []
    assert '- Teslimat (1)' in result['context'] and '1 record(s) without a topic' in result['context']
    assert 'alpha is delivered' not in result['context'] and 'importer stays manual' not in result['context']

    RuntimeConfig(vault).set_context_profile('normal')
    assert 'alpha is delivered' in compile_bootstrap(vault, vault)['context']
