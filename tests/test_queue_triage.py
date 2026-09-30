"""Automatic review-queue pre-evaluation (owner decision 2026-09-30)."""

import pytest

from brain_eleven.runtime.queue_triage import rule_verdict, triage
from brain_eleven.runtime.storage import RuntimeConfig, read_json, write_json
from brain_eleven.runtime.value import load_suggestions
from tests.test_memclaim01_claim_key import NEW_TIME, _review_item, _runtime

NL = "\n"
BACKSLASH = "\\"


def _memory(content, **extra):
    return {'candidate_type': 'NEW_MEMORY', 'commitment': 'COMMITTED', 'memory_type': 'decision',
            'content': content, **extra}


@pytest.mark.parametrize(('candidate', 'reason'), [
    (_memory('[15] tool exec result: Script completed' + NL + 'Wall time 1.3 seconds'), 'PASTED_OUTPUT'),
    (_memory('Use the system daily.' + NL + '+' + NL + '+### Simplification'), 'MACHINE_CONTENT'),
    (_memory('You can use markdown.' + BACKSLASH + 'n - Tools are' + BACKSLASH + 'n executed'), 'MACHINE_CONTENT'),
    (_memory('Return {"candidates": []} for every call.'), 'MACHINE_CONTENT'),
    (_memory('```python' + NL + 'print(1)' + NL + '``` was the snippet we used.'), 'MACHINE_CONTENT'),
    (_memory('Tamam, geçelim.'), 'TOO_SHORT'),
    (_memory('Yani projemizde nasıl ilerleyeceğiz, ne dersin?', commitment='QUESTION'), 'QUESTION'),
    ({'candidate_type': 'STATE_MUTATION', 'commitment': 'OBSERVED', 'text': 'The nightly build is failing again.'},
     'STATE_NOT_COMMITTED'),
])
def test_rules_reject_clear_noise(candidate, reason):
    assert rule_verdict(candidate) == ('REJECT', reason)


@pytest.mark.parametrize('text', [
    '**Karar:** SQLite kullanacağız çünkü uygulama lokal.',
    '- We will use Postgres for the reporting service.',
    '## Karar' + NL + 'Bundan sonra her PR bağımsız incelemeden geçecek.',
    'Config dosyası D:' + BACKSLASH + 'nas altında kalacak, taşımayacağız.',
])
def test_user_formatting_goes_to_the_model_not_rejected(text):
    # Review 2026-09-30 (MEDIUM): markdown the owner types must not hide a decision.
    assert rule_verdict(_memory(text)) == (None, '')


def test_rules_never_accept_and_catch_duplicates():
    decision = _memory('SQLite kullanacağız çünkü uygulama tamamen lokal.')
    assert rule_verdict(decision) == (None, '')
    assert rule_verdict(decision, similarity=0.8) == ('REJECT', 'DUPLICATE')


def test_model_accept_is_left_for_a_person_unless_allowed(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    keep = _review_item(tmp_path, vault, 'keep', 'We decided to use SQLite because the app is local.', NEW_TIME)
    noise = _review_item(tmp_path, vault, 'noise', 'We decided: [3] tool exec result: Script completed', NEW_TIME)
    asked = []

    def model(candidate):
        asked.append(candidate['content'])
        return 'ACCEPT', 'SELF_CONTAINED_DECISION'

    counts = triage(vault, model_fn=model)
    suggestions = load_suggestions(vault)

    assert asked == ['We decided to use SQLite because the app is local.']
    assert suggestions[keep['id']]['suggestion'] == 'REVIEW'
    assert suggestions[noise['id']]['suggestion'] == 'REJECT'
    assert suggestions[noise['id']]['by'] == 'rules'
    assert counts['rule_reject'] == 1 and counts['model_review'] == 1
    # A second run asks nothing: every pending item already has a suggestion.
    assert triage(vault, model_fn=model)['pending_without_suggestion'] == 0


def test_model_accept_is_recorded_when_allowed_and_failures_are_retried(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    keep = _review_item(tmp_path, vault, 'keep', 'We decided to use SQLite because the app is local.', NEW_TIME)

    triage(vault, model_fn=lambda candidate: ('REVIEW', 'MODEL_UNAVAILABLE'))
    assert keep['id'] not in load_suggestions(vault)
    triage(vault, model_fn=lambda candidate: ('REVIEW', 'MODEL_INVALID'))
    assert keep['id'] not in load_suggestions(vault)

    triage(vault, model_fn=lambda candidate: ('ACCEPT', 'SELF_CONTAINED_DECISION'), accept_model=True)
    entry = load_suggestions(vault)[keep['id']]
    assert (entry['suggestion'], entry['by']) == ('ACCEPT', 'qwen2.5:7b')


def test_triage_merges_with_suggestions_written_meanwhile(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    first = _review_item(tmp_path, vault, 'first', 'We decided to use SQLite because the app is local.', NEW_TIME)
    second = _review_item(tmp_path, vault, 'second', 'We decided the dashboard stays read-only for now.', NEW_TIME)
    path = RuntimeConfig(vault).root / 'review-suggestions.json'
    write_json(path, {'by': 'codex', 'suggestions': {first['id']: {'suggestion': 'REJECT', 'reason': 'TRANSIENT'}}})
    other = 'rev_' + 'a' * 64

    def model(candidate):
        # Another writer lands while the model is thinking.
        document = read_json(path)
        document['suggestions'][other] = {'suggestion': 'REJECT', 'reason': 'X', 'by': 'other'}
        write_json(path, document)
        return 'REVIEW', 'UNSURE'

    triage(vault, model_fn=model)
    saved = read_json(path)['suggestions']
    assert saved[first['id']] == {'suggestion': 'REJECT', 'reason': 'TRANSIENT', 'by': 'codex'}
    assert saved[other]['by'] == 'other'
    assert saved[second['id']]['suggestion'] == 'REVIEW'


def test_queue_triage_flag_is_off_by_default_and_owner_can_turn_it_on(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    config = RuntimeConfig(vault)
    assert config.load()['queue_triage'] is False
    config.set_queue_triage(True)
    assert read_json(config.path)['queue_triage'] is True
    with pytest.raises(ValueError):
        config.set_queue_triage('yes')
