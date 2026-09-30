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


def _chat(keep=True, project=None):
    def chat(prompt):
        if 'Which software project' in prompt:
            return {'project': project or 'UNKNOWN'}
        return {'decision': 'KEEP' if keep else 'DROP'}
    return chat


def test_verifier_outcomes():
    from brain_eleven.runtime.queue_triage import verify_candidate
    labels = {'p1': 'brain-eleven', 'p2': 'whale-tracker'}
    fact = {'candidate_type': 'NEW_MEMORY', 'project_id': 'p1',
            'content': 'Bandit gate failure was fixed per the repo nosec convention, gate untouched.'}
    assert verify_candidate(fact, labels, chat=_chat()) == ('VERIFIED', 'MODEL_VERIFIED')
    assert verify_candidate(fact, labels, chat=_chat(keep=False)) == ('DROP', 'VERIFY_DROP')
    assert verify_candidate(fact, labels, chat=_chat(project='whale-tracker')) == ('WRONG_PROJECT', 'WRONG_PROJECT')
    assert verify_candidate(fact, labels, chat=_chat(project='brain-eleven'))[0] == 'VERIFIED'
    assert verify_candidate(fact, labels, chat=lambda prompt: None)[0] == 'UNAVAILABLE'
    for fragment in ('Ancak bundan sonra V2 kararını vermek gerekiyor artık.', 'the JUNK list can still delete real work.'):
        assert verify_candidate({**fact, 'content': fragment}, labels, chat=_chat())[0] == 'FRAGMENT'


def test_verified_candidates_wait_for_the_owner_unless_auto_accept(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    keep = _review_item(tmp_path, vault, 'keep', 'We decided to use SQLite because the app is local.', NEW_TIME)
    triage(vault, chat=_chat())
    assert load_suggestions(vault)[keep['id']]['suggestion'] == 'REVIEW'

    (tmp_path / 'second').mkdir()
    vault2, _ = _runtime(tmp_path / 'second', shadow_accept=True)
    keep2 = _review_item(tmp_path / 'second', vault2, 'keep', 'We decided to use SQLite because the app is local.',
                         NEW_TIME)
    triage(vault2, chat=_chat(), accept_verified=True)
    entry = load_suggestions(vault2)[keep2['id']]
    assert (entry['suggestion'], entry['reason']) == ('ACCEPT', 'MODEL_VERIFIED')


def test_auto_accept_verified_flag_is_off_by_default(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    config = RuntimeConfig(vault)
    assert config.load()['auto_accept_verified'] is False
    config.set_auto_accept_verified(True)
    assert config.load()['auto_accept_verified'] is True


def test_nonsense_model_answer_is_retried_not_hidden():
    from brain_eleven.runtime.queue_triage import verify_candidate
    fact = {'candidate_type': 'NEW_MEMORY', 'project_id': 'p1',
            'content': 'Bandit gate failure was fixed per the repo nosec convention, gate untouched.'}
    for answer in ({}, {'decision': 'MAYBE'}):
        assert verify_candidate(fact, {'p1': 'brain-eleven'}, chat=lambda prompt, a=answer: a) == (
            'UNAVAILABLE', 'MODEL_INVALID')


def test_wrong_project_is_left_for_the_owner(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    keep = _review_item(tmp_path, vault, 'keep', 'We decided to use SQLite because the app is local.', NEW_TIME)
    import brain_eleven.runtime.queue_triage as queue_triage
    labels = {keep['project_id']: 'brain-eleven', 'other': 'whale-tracker'}
    original = queue_triage._project_labels
    queue_triage._project_labels = lambda vault_arg: labels
    try:
        triage(vault, chat=_chat(project='whale-tracker'))
    finally:
        queue_triage._project_labels = original
    entry = load_suggestions(vault)[keep['id']]
    assert (entry['suggestion'], entry['reason']) == ('REVIEW', 'WRONG_PROJECT')


def test_turning_auto_accept_on_promotes_items_verified_earlier(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    keep = _review_item(tmp_path, vault, 'keep', 'We decided to use SQLite because the app is local.', NEW_TIME)
    triage(vault, chat=_chat())
    assert load_suggestions(vault)[keep['id']]['suggestion'] == 'REVIEW'
    triage(vault, chat=_chat(), accept_verified=True)
    assert load_suggestions(vault)[keep['id']]['suggestion'] == 'ACCEPT'


def test_fragment_rule_keeps_identifiers_and_brackets():
    from brain_eleven.runtime.queue_triage import _FRAGMENT
    for ok in ('qwen2.5:7b is the default local model for triage.', 'npm ci installs the locked tree.',
               '[Brain-Eleven] decision: summaries are the main source.', 'İstem-zamanı hafıza çalışıyor.'):
        assert not _FRAGMENT.match(ok), ok
    for fragment in ('the JUNK list can still delete real work.', 'Ancak bundan sonra V2 kararını vermek.',
                     've sonra testleri çalıştırdık.'):
        assert _FRAGMENT.match(fragment), fragment
