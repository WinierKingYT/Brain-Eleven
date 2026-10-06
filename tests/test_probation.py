"""Probation for memories written without a person (owner decision 2026-10-02)."""

from datetime import datetime, timezone

import pytest

from brain_eleven.__main__ import main
from brain_eleven.memory import MemoryStore
from brain_eleven.runtime.probation import flagged_ids, on_probation, review, rule_reason
from brain_eleven.runtime.storage import RuntimeConfig
from brain_eleven.runtime.value import owner_check
from tests.test_memclaim01_claim_key import _accept, _review_item, _runtime

SOON = datetime(2026, 9, 25, tzinfo=timezone.utc)   # two days after NEW_TIME
LATE = datetime(2026, 10, 20, tzinfo=timezone.utc)  # past the 14-day probation
MODEL_NOTE = 'Model onayı (qwen2.5:7b): MODEL_VERIFIED'
GOOD = 'We decided to use SQLite because the app is fully local.'
JUNK = "c.memories=[{'memory_id':'bad','status':'active'}] is the fixture we decided on."


def _memory(tmp_path, vault, name, text, **payload):
    from tests.test_memclaim01_claim_key import NEW_TIME
    _accept(vault, _review_item(tmp_path, vault, name, text, NEW_TIME), **payload)
    return next(m['memory_id'] for m in MemoryStore(vault).load()['validated_memory'] if m['content'] == text)


def _status(vault, memory_id):
    return next(m for m in MemoryStore(vault).load()['validated_memory'] if m['memory_id'] == memory_id)


def _chat(decision):
    return lambda prompt: {'decision': decision}


def test_rule_hit_is_retired_but_a_model_drop_only_flags(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    junk = _memory(tmp_path, vault, 'junk', JUNK, note=MODEL_NOTE)
    good = _memory(tmp_path, vault, 'good', GOOD, note=MODEL_NOTE)

    report = review(vault, apply=True, now=SOON, chat=_chat('DROP'))

    assert report['retired'] == [{'memory_id': junk, 'reason': 'MACHINE_CONTENT'}]
    assert _status(vault, junk)['status'] != 'active' and _status(vault, junk)['resolved_by'] == 'probation'
    # Measured 2026-10-06: the local model's DROP is not evidence; it flags only.
    assert report['flagged'] == [good] and _status(vault, good)['status'] == 'active'
    assert flagged_ids(vault) == [good]
    # Checked memories are not asked again.
    assert review(vault, apply=True, now=SOON, chat=_chat('DROP'))['flagged'] == []


def test_dry_run_changes_nothing(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    junk = _memory(tmp_path, vault, 'junk', JUNK, note=MODEL_NOTE)
    report = review(vault, apply=False, now=SOON, chat=_chat('KEEP'))
    assert report['retired'][0]['memory_id'] == junk
    assert _status(vault, junk)['status'] == 'active'
    assert not (RuntimeConfig(vault).root / 'probation.json').exists()


def test_person_accepted_and_old_memories_are_not_on_probation(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    by_person = _memory(tmp_path, vault, 'person', JUNK)
    by_model = _memory(tmp_path, vault, 'model', GOOD, note=MODEL_NOTE)
    from brain_eleven.runtime.probation import human_accepted_ids
    memories = MemoryStore(vault).load()['validated_memory']
    human = human_accepted_ids(vault)
    assert by_person in human and by_model not in human
    assert [m['memory_id'] for m in on_probation(memories, human, SOON)] == [by_model]
    assert on_probation(memories, human, LATE) == []


def test_unavailable_model_is_retried_and_guard_protects_recall_answers(tmp_path, monkeypatch):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    junk = _memory(tmp_path, vault, 'junk', JUNK, note=MODEL_NOTE)
    good = _memory(tmp_path, vault, 'good', GOOD, note=MODEL_NOTE)
    monkeypatch.setattr('brain_eleven.runtime.memory_audit._recall_questions',
                        lambda vault_arg: [{'id': 1, 'groups': [['c.memories']]}])

    report = review(vault, apply=True, now=SOON, chat=lambda prompt: None)

    assert report['protected'] == [junk] and _status(vault, junk)['status'] == 'active'
    assert report['unavailable'] == 1
    assert review(vault, apply=True, now=SOON, chat=_chat('KEEP'))['kept'] == 1
    assert _status(vault, good)['status'] == 'active'


def test_rule_reason_catches_pasted_documents_but_not_decisions():
    document = chr(10).join(['## Bölüm %d' % n + chr(10) + 'Plan metni burada uzun uzun anlatılıyor. ' * 6
                             for n in range(6)])
    assert rule_reason(document) == 'PASTED_DOCUMENT'
    assert rule_reason(GOOD) == ''
    # Length alone never retires: a long lesson can be valid.
    assert rule_reason('We learned that ' + 'the cache must be warmed before prompts, ' * 20) == ''


def test_owner_check_lists_flags_first_then_a_stable_weekly_sample(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    ids = [_memory(tmp_path, vault, f'm{n}', f'We decided the module {n} keeps its own cache layer.',
                   note=MODEL_NOTE) for n in range(7)]
    review(vault, apply=True, now=SOON, chat=lambda prompt, seen=[]: {'decision': 'DROP' if not seen.append(1) and len(seen) == 1 else 'KEEP'})
    memories = MemoryStore(vault).load()['validated_memory']

    first = owner_check(vault, memories, now=SOON)
    assert first[0] == {'memory_id': ids[0], 'why': 'FLAGGED', 'text': first[0]['text']}
    samples = [x['memory_id'] for x in first if x['why'] == 'SAMPLE']
    assert len(samples) == 5 and ids[0] not in samples
    assert [x['memory_id'] for x in owner_check(vault, memories, now=SOON)] == [x['memory_id'] for x in first]


def test_flag_and_cli(tmp_path, capsys):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    config = RuntimeConfig(vault)
    assert config.load()['probation_review'] is False
    config.set_probation_review(True)
    assert config.load()['probation_review'] is True
    with pytest.raises(ValueError):
        config.set_probation_review('yes')

    good = _memory(tmp_path, vault, 'good', GOOD, note=MODEL_NOTE)
    # Review 2026-10-06: a failed id must show in the exit code.
    assert main(['--vault', str(vault), 'retire', good, 'mem_missing']) == 1
    assert _status(vault, good)['resolved_by'] == 'owner'
    assert main(['--vault', str(vault), 'probation', 'OFF']) == 0
    assert config.load()['probation_review'] is False


def test_a_stopped_model_is_asked_once_per_run_and_progress_is_saved(tmp_path):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    for n in range(3):
        _memory(tmp_path, vault, f'm{n}', f'We decided the module {n} keeps its own cache layer.', note=MODEL_NOTE)
    calls = []

    def down(prompt):
        calls.append(prompt)
        return None

    report = review(vault, apply=True, now=SOON, chat=down)
    assert len(calls) == 1 and report['unavailable'] == 3

    answers = iter([{'decision': 'KEEP'}, RuntimeError('crash')])

    def flaky(prompt):
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    with pytest.raises(RuntimeError):
        review(vault, apply=True, now=SOON, chat=flaky)
    from brain_eleven.runtime.storage import read_json
    assert len(read_json(RuntimeConfig(vault).root / 'probation.json')['checked']) == 1


def test_service_cycle_keeps_triage_result_when_probation_fails(tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from brain_eleven.runtime import service
    from brain_eleven.runtime.storage import read_json
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    config = RuntimeConfig(vault)
    config.set_queue_triage(True)
    config.set_probation_review(True)
    monkeypatch.setattr('brain_eleven.runtime.queue_triage.triage', lambda vault_arg, **kw: {'rule_reject': 2})

    def boom(vault_arg, **kw):
        raise RuntimeError('probation broke')
    monkeypatch.setattr('brain_eleven.runtime.probation.review', boom)
    app = SimpleNamespace(state=SimpleNamespace(vault=vault, queue_triage_running=False, queue_triage_at=-1e9))

    async def cycle():
        await service.maybe_queue_triage(app)
        while app.state.queue_triage_running:
            await asyncio.sleep(0.01)
    asyncio.run(cycle())

    saved = read_json(config.root / 'last-queue-triage.json')
    assert saved['rule_reject'] == 2 and saved['probation'] == {'status': 'FAILED'}
