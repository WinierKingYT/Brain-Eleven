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
