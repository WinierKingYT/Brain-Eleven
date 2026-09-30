"""Owner notice and digest (owner decision 2026-09-30, step 6)."""

from brain_eleven.runtime.storage import RuntimeConfig, write_json
from brain_eleven.runtime.value import digest, owner_notice
from tests.test_memclaim01_claim_key import NEW_TIME, _review_item, _runtime


def _suggest(vault, entries):
    write_json(RuntimeConfig(vault).root / 'review-suggestions.json', {'by': 'test', 'suggestions': entries})


def test_notice_counts_items_left_for_the_owner_and_skips_hidden_ones(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    keep = _review_item(tmp_path, vault, 'keep', 'We decided to use SQLite because the app is local.', NEW_TIME)
    hidden = _review_item(tmp_path, vault, 'hidden', 'We decided the dashboard stays read-only for now.', NEW_TIME)
    assert owner_notice(vault) == ''

    _suggest(vault, {keep['id']: {'suggestion': 'REVIEW', 'reason': 'MODEL_ACCEPT'},
                     hidden['id']: {'suggestion': 'REJECT', 'reason': 'TRANSIENT'}})

    notice = owner_notice(vault)
    assert '1 review candidates wait' in notice and '(1 suggested by the local model)' in notice
    listed = digest(vault)
    assert [x['id'] for x in listed['top']] == [keep['id']] and listed['top'][0]['model_accept'] is True


def test_bootstrap_carries_the_notice(tmp_path):
    from brain_eleven.runtime.context import compile_bootstrap
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    keep = _review_item(tmp_path, vault, 'keep', 'We decided to use SQLite because the app is local.', NEW_TIME)
    _suggest(vault, {keep['id']: {'suggestion': 'REVIEW', 'reason': 'MODEL_ACCEPT'}})

    context = compile_bootstrap(vault, vault)['context']

    assert '## Owner action' in context and 'python -m brain_eleven digest' in context
