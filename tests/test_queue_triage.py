"""Automatic review-queue pre-evaluation (owner decision 2026-09-30)."""

import json

import pytest

from brain_eleven.runtime.queue_triage import rule_verdict, triage
from brain_eleven.runtime.storage import RuntimeConfig, read_json
from brain_eleven.runtime.value import load_suggestions
from tests.test_memclaim01_claim_key import NEW_TIME, _review_item, _runtime


def _memory(content, **extra):
    return {'candidate_type': 'NEW_MEMORY', 'commitment': 'COMMITTED', 'memory_type': 'decision',
            'content': content, **extra}


@pytest.mark.parametrize(('candidate', 'reason'), [
    (_memory('[15] tool exec result: Script completed\nWall time 1.3 seconds'), 'PASTED_OUTPUT'),
    (_memory('Use the system daily.\n+\n+### Simplification'), 'MARKUP'),
    (_memory('You can use markdown.\\n - Tools are executed'), 'MARKUP'),
    (_memory('Return JSON {"candidates":[]} for every call.'), 'MARKUP'),
    (_memory('**Fix**: design decision to use small ranges only.'), 'MARKUP'),
    (_memory('Tamam, geçelim.'), 'TOO_SHORT'),
    (_memory('Yani projemizde nasıl ilerleyeceğiz, ne dersin?', commitment='QUESTION'), 'QUESTION'),
    ({'candidate_type': 'STATE_MUTATION', 'commitment': 'OBSERVED', 'text': 'The nightly build is failing again.'},
     'STATE_NOT_COMMITTED'),
])
def test_rules_reject_clear_noise(candidate, reason):
    assert rule_verdict(candidate) == ('REJECT', reason)


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


def test_model_accept_is_recorded_when_allowed_and_unavailable_is_retried(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    keep = _review_item(tmp_path, vault, 'keep', 'We decided to use SQLite because the app is local.', NEW_TIME)

    triage(vault, model_fn=lambda candidate: ('REVIEW', 'MODEL_UNAVAILABLE'))
    assert keep['id'] not in load_suggestions(vault)

    triage(vault, model_fn=lambda candidate: ('ACCEPT', 'SELF_CONTAINED_DECISION'), accept_model=True)
    entry = load_suggestions(vault)[keep['id']]
    assert (entry['suggestion'], entry['by']) == ('ACCEPT', 'qwen2.5:7b')


def test_queue_triage_flag_is_off_by_default_and_owner_can_turn_it_on(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    config = RuntimeConfig(vault)
    assert config.load()['queue_triage'] is False
    config.set_queue_triage(True)
    assert read_json(config.path)['queue_triage'] is True
    with pytest.raises(ValueError):
        config.set_queue_triage('yes')
