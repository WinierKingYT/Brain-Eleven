"""Weekly memory audit (owner decision 2026-09-30)."""

import json
from datetime import datetime, timedelta, timezone

from brain_eleven.memory import MemoryStore
from brain_eleven.runtime.memory_audit import _jaccard, audit, protected_ids
from brain_eleven.runtime.memory_usage import record_delivery
from brain_eleven.runtime.storage import RuntimeConfig
from tests.test_memclaim01_claim_key import NEW_TIME, _accept, _review_item, _runtime

LATER = datetime(2027, 1, 1, tzinfo=timezone.utc)


def _memory(tmp_path, vault, name, text):
    _accept(vault, _review_item(tmp_path, vault, name, text, NEW_TIME))
    return next(m['memory_id'] for m in MemoryStore(vault).load()['validated_memory'] if m['content'] == text)


def _active(vault):
    return {m['memory_id'] for m in MemoryStore(vault).load()['validated_memory']
            if str(m.get('status') or 'active') == 'active'}


def _exact(first_id, second_id, score=0.99):
    """Similarity stub: the named pair scores ``score``, everything else 0."""
    def similarity(a, b):
        return score if {a['memory_id'], b['memory_id']} == {first_id, second_id} else 0.0
    return 'stub', None, similarity


def test_exact_duplicate_is_retired_keeping_the_used_copy(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    kept = _memory(tmp_path, vault, 'a', 'We decided the dashboard stays read-only for now.')
    dropped = _memory(tmp_path, vault, 'b', 'We decided the dashboard remains read-only for now.')
    record_delivery(vault, [kept], session_key='k', event='UserPromptSubmit', at=NEW_TIME)

    report = audit(vault, apply=True, use_model=False, now=LATER, similarity_fn=_exact(kept, dropped))

    assert [r['memory_id'] for r in report['retired']] == [dropped]
    assert kept in _active(vault) and dropped not in _active(vault)


def test_dry_run_changes_nothing(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    first = _memory(tmp_path, vault, 'a', 'We decided the dashboard stays read-only for now.')
    second = _memory(tmp_path, vault, 'b', 'We decided the dashboard remains read-only for now.')
    report = audit(vault, apply=False, use_model=False, now=LATER, similarity_fn=_exact(first, second))
    assert len(report['retired']) == 1 and {first, second} <= _active(vault)


def test_the_only_recall_answer_is_never_retired(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    answer = _memory(tmp_path, vault, 'a', 'We decided the alpha gate stays red on purpose.')
    other = _memory(tmp_path, vault, 'b', 'We decided the alpha gate stays closed on purpose.')
    (RuntimeConfig(vault).root / 'questions-test.json').write_text(json.dumps(
        {'questions': [{'id': 1, 'question': 'alpha gate?', 'groups': [['alpha'], ['red']]}]}), encoding='utf-8')
    # The unused copy would normally be dropped; here it is the only answer.
    record_delivery(vault, [other], session_key='k', event='UserPromptSubmit', at=NEW_TIME)

    report = audit(vault, apply=True, use_model=False, now=LATER, similarity_fn=_exact(answer, other))

    assert answer in report['protected']
    assert [r['memory_id'] for r in report['retired']] == [other]
    assert answer in _active(vault)


def test_model_same_and_conflict_become_suggestions_only(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    first = _memory(tmp_path, vault, 'a', 'We decided to use SQLite for the local store.')
    second = _memory(tmp_path, vault, 'b', 'We decided to use Postgres for the local store.')
    for relation, kind in (('SAME', 'NEAR_DUPLICATE'), ('CONFLICT', 'CONTRADICTION')):
        report = audit(vault, apply=True, now=LATER, similarity_fn=_exact(first, second, 0.75),
                       model_fn=lambda older, newer, relation=relation: relation)
        assert [s['kind'] for s in report['suggestions']] == [kind]
        assert report['retired'] == [] and {first, second} <= _active(vault)


def test_never_delivered_is_suggested_after_four_weeks_of_tracking(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    idle = _memory(tmp_path, vault, 'a', 'We decided the importer stays manual for the whole quarter.')
    record_delivery(vault, ['mem_other'], session_key='k', event='UserPromptSubmit', at=NEW_TIME)
    report = audit(vault, use_model=False, now=LATER, similarity_fn=_jaccard())
    assert ('NEVER_DELIVERED', idle) in {(s['kind'], s['memory_id']) for s in report['suggestions']}


def test_status_note_pattern_matches_status_words_only():
    from brain_eleven.runtime.memory_audit import _STATUS_NOTE
    assert _STATUS_NOTE.search('The nightly build is currently failing on Windows.')
    assert _STATUS_NOTE.search('Testler hâlâ kırmızı.')
    assert not _STATUS_NOTE.search('We decided to use SQLite for the local store.')


def test_never_delivered_waits_for_four_weeks_of_tracking(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    _memory(tmp_path, vault, 'a', 'We decided the dashboard stays read-only for now.')
    record_delivery(vault, ['mem_other'], session_key='k', event='UserPromptSubmit', at=LATER.isoformat())
    report = audit(vault, use_model=False, now=LATER + timedelta(days=3), similarity_fn=_jaccard())
    assert not [s for s in report['suggestions'] if s['kind'] == 'NEVER_DELIVERED']


def test_protected_ids_counts_whole_answers_only():
    memories = [{'memory_id': 'm1', 'content': 'alpha red'}, {'memory_id': 'm2', 'content': 'alpha only'}]
    assert protected_ids(memories, [{'groups': [['alpha'], ['red']]}]) == {'m1'}
    both = memories + [{'memory_id': 'm3', 'content': 'alpha is red'}]
    assert protected_ids(both, [{'groups': [['alpha'], ['red']]}]) == set()


def test_memory_audit_flag_is_off_by_default(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    config = RuntimeConfig(vault)
    assert config.load()['memory_audit'] is False
    config.set_memory_audit(True)
    assert config.load()['memory_audit'] is True


def test_guard_keeps_the_last_carrier_when_retiring_one_by_one(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    first = _memory(tmp_path, vault, 'a', 'We decided the alpha gate stays red on purpose.')
    second = _memory(tmp_path, vault, 'b', 'We decided the alpha gate remains red on purpose.')
    hub = _memory(tmp_path, vault, 'c', 'We decided the alpha gate stays shut on purpose.')
    (RuntimeConfig(vault).root / 'questions-test.json').write_text(json.dumps(
        {'questions': [{'id': 1, 'question': 'alpha gate?', 'groups': [['alpha'], ['red']]}]}), encoding='utf-8')
    record_delivery(vault, [hub, hub], session_key='k', event='UserPromptSubmit', at=NEW_TIME)

    def similarity(a, b):
        return 0.99 if hub in {a['memory_id'], b['memory_id']} else 0.0

    report = audit(vault, apply=True, use_model=False, now=LATER, similarity_fn=('stub', None, similarity))

    # One carrier and the hub go; the last carrier of the answer always stays.
    assert len({first, second} & _active(vault)) == 1
    assert {r['memory_id'] for r in report['retired']} == ({first, second} - _active(vault)) | {hub}


def test_guard_is_per_project(tmp_path):
    from brain_eleven.runtime.memory_audit import protected_ids as guard
    memories = [{'memory_id': 'a', 'project_id': 'P', 'content': 'alpha red'},
                {'memory_id': 'x', 'project_id': 'Q', 'content': 'alpha red too'}]
    assert guard(memories, [{'groups': [['alpha'], ['red']]}]) == {'a', 'x'}


def test_missing_official_questions_blocks_every_retirement(tmp_path, monkeypatch):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    first = _memory(tmp_path, vault, 'a', 'We decided the dashboard stays read-only for now.')
    second = _memory(tmp_path, vault, 'b', 'We decided the dashboard remains read-only for now.')

    def unreadable(path=None):
        raise OSError('questions.json missing')

    monkeypatch.setattr('brain_eleven.runtime.recall_probe.load_questions', unreadable)
    report = audit(vault, apply=True, use_model=False, now=LATER, similarity_fn=_exact(first, second))

    assert report['retired'] == [] and report['warning'] == 'RECALL_QUESTIONS_UNAVAILABLE'
    assert [s['kind'] for s in report['suggestions']] == ['EXACT_DUPLICATE']
    assert {first, second} <= _active(vault)


def test_automatic_retirement_is_attributed_to_the_audit(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    kept = _memory(tmp_path, vault, 'a', 'We decided the dashboard stays read-only for now.')
    dropped = _memory(tmp_path, vault, 'b', 'We decided the dashboard remains read-only for now.')
    record_delivery(vault, [kept], session_key='k', event='UserPromptSubmit', at=NEW_TIME)
    audit(vault, apply=True, use_model=False, now=LATER, similarity_fn=_exact(kept, dropped))
    memory = next(m for m in MemoryStore(vault).load()['validated_memory'] if m['memory_id'] == dropped)
    assert memory.get('resolved_by') == 'memory-audit'


def test_interrupted_audit_still_reports_what_it_retired(tmp_path, monkeypatch):
    import pytest
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    kept = _memory(tmp_path, vault, 'a', 'We decided the dashboard stays read-only for now.')
    dropped = _memory(tmp_path, vault, 'b', 'We decided the dashboard remains read-only for now.')
    record_delivery(vault, [kept], session_key='k', event='UserPromptSubmit', at=NEW_TIME)

    def explode(*args, **kwargs):
        raise RuntimeError('crash after the first retirement')

    monkeypatch.setattr('brain_eleven.runtime.memory_audit._age_days', explode)
    with pytest.raises(RuntimeError):
        audit(vault, apply=True, use_model=False, now=LATER, similarity_fn=_exact(kept, dropped))
    saved = json.loads((RuntimeConfig(vault).root / 'memory-audit.json').read_text(encoding='utf-8'))
    assert [r['memory_id'] for r in saved['retired']] == [dropped] and saved['status'] == 'RUNNING'


def test_queue_triage_launch_does_not_clear_the_audit_running_flag(tmp_path, monkeypatch):
    import asyncio
    from brain_eleven.runtime import service
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    RuntimeConfig(vault).set_queue_triage(True)
    app = service.create_app(vault, token='t', background=False)
    app.state.memory_audit_running = True
    monkeypatch.setattr('brain_eleven.runtime.queue_triage.triage', lambda vault_arg: {})

    async def launch():
        await service.maybe_queue_triage(app)
        await asyncio.sleep(0.05)

    asyncio.run(launch())
    assert app.state.memory_audit_running is True


def test_audit_schedule_retries_a_failed_run_within_hours():
    from datetime import datetime, timedelta, timezone
    from brain_eleven.runtime.service import memory_audit_due
    current = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    at = lambda hours: (current - timedelta(hours=hours)).isoformat()
    assert memory_audit_due({}, current) is True
    assert memory_audit_due({'at': 'garbled'}, current) is True
    assert memory_audit_due({'at': at(24), 'status': 'OK'}, current) is False
    assert memory_audit_due({'at': at(24 * 7), 'status': 'OK'}, current) is True
    assert memory_audit_due({'at': at(1), 'status': 'FAILED'}, current) is False
    assert memory_audit_due({'at': at(7), 'status': 'FAILED'}, current) is True
