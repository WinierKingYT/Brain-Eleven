"""Subagent support (2026-10-13).

A subagent starts without the parent's SessionStart context and what it learns
was lost: its report reached the parent transcript as a tool result (dropped)
or a meta record (quarantined as a proposal). SubagentStart now gives it the
project memory and asks for a findings section; that section is captured from
the parent transcript, always for the owner's review.
"""

import json
import re

from brain_eleven.memory import MemoryStore
from brain_eleven.runtime import launcher
from brain_eleven.runtime.evidence import SUBAGENT_FINDINGS_HEADING, read_increment
from brain_eleven.runtime.extraction import DeterministicExtractor, NewMemoryCandidate
from brain_eleven.runtime.install import CLIENT_EVENTS, merge_hooks
from brain_eleven.runtime.review import ReviewStore
from brain_eleven.runtime.storage import RuntimeConfig, write_json
from brain_eleven.runtime.worker import Worker, enqueue
from tests.test_pre13_runtime import _native_path, runtime  # noqa: F401  (fixture)

FINDING_1 = 'Windows hook komutları pythonw.exe ile çalışmalı, yoksa her yakalamada konsol penceresi açılıyor.'
FINDING_2 = 'Kuyruk işleyicisi transcript dosyası henüz yazılmadıysa işi QUEUED bırakıp yeniden deniyor.'
REPORT = '\n'.join([
    'İnceleme tamam. Üç dosyaya baktım, hook kurulumu doğru görünüyor.',
    '',
    SUBAGENT_FINDINGS_HEADING,
    '- ' + FINDING_1,
    '- ' + FINDING_2,
    '  Bu davranış bilinçli; ayrıntı satırı maddeye eklenir.',
    '- kısa',
])


def _tool_result(text, session='s'):
    return {'type': 'user', 'sessionId': session, 'message': {'role': 'user', 'content': [
        {'type': 'tool_result', 'tool_use_id': 'toolu_1', 'content': [{'type': 'text', 'text': text}]}]}}


def _facts(batch):
    return [c.content for c in DeterministicExtractor().extract(batch).candidates if isinstance(c, NewMemoryCandidate)]


def test_constants_match_between_hook_and_reader():
    assert launcher.SUBAGENT_FINDINGS_HEADING == SUBAGENT_FINDINGS_HEADING
    assert SUBAGENT_FINDINGS_HEADING in launcher.SUBAGENT_INSTRUCTION


def test_foreground_report_findings_become_candidates(runtime, tmp_path):  # noqa: F811
    vault, project = runtime
    path = _native_path(tmp_path, vault, 'claude', 's', [_tool_result(REPORT)])
    batch, _ = read_increment(vault, path, 'claude', 's', project, '2026-10-13T00:00:00Z')

    assert [m.record.role for m in batch.messages] == ['subagent']
    assert _facts(batch) == [FINDING_1, FINDING_2 + ' Bu davranış bilinçli; ayrıntı satırı maddeye eklenir.']


def test_background_hand_back_is_a_subagent_report(runtime, tmp_path):  # noqa: F811
    vault, project = runtime
    record = {'type': 'user', 'isMeta': True, 'sessionId': 's', 'message': {'role': 'user', 'content': REPORT}}
    path = _native_path(tmp_path, vault, 'claude', 's', [record])
    batch, _ = read_increment(vault, path, 'claude', 's', project, '2026-10-13T00:00:00Z')

    assert [m.record.role for m in batch.messages] == ['subagent']
    assert FINDING_1 in _facts(batch)


def test_other_tool_results_and_reports_without_findings_stay_out(runtime, tmp_path):  # noqa: F811
    vault, project = runtime
    path = _native_path(tmp_path, vault, 'claude', 's', [
        _tool_result('total 4\n-rw-r--r-- 1 user user 12 file.txt'),
        _tool_result('Rapor: kalıcı bir şey bulunamadı.'),
    ])
    batch, _ = read_increment(vault, path, 'claude', 's', project, '2026-10-13T00:00:00Z')
    assert batch.messages == () or list(batch.messages) == []


def test_compact_summary_keeps_its_own_role(runtime, tmp_path):  # noqa: F811
    vault, project = runtime
    record = {'type': 'user', 'isCompactSummary': True, 'sessionId': 's',
              'message': {'role': 'user', 'content': 'Summary:\n' + REPORT}}
    path = _native_path(tmp_path, vault, 'claude', 's', [record])
    batch, _ = read_increment(vault, path, 'claude', 's', project, '2026-10-13T00:00:00Z')
    assert [m.record.role for m in batch.messages] == ['summary']


def test_findings_section_ends_at_the_next_heading():
    from brain_eleven.runtime.extraction import _legacy
    text = REPORT + '\n## Sonraki adımlar\n- Bu satır bir bulgu değildir ama yeterince uzun bir maddedir.'
    assert _legacy.subagent_facts(text)[-1].startswith(FINDING_2)
    assert _legacy.subagent_facts('Bulgu yok.') == []


def test_subagent_findings_always_wait_for_review(tmp_path):
    trusted = tmp_path / 'trusted'
    trusted.mkdir()
    vault = tmp_path / 'vault'
    vault.mkdir()
    from brain_eleven.projects.registry import ProjectRegistry
    from brain_eleven.runtime.migration import migrate
    from brain_eleven.state import StateService
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    StateService(vault).init_project(project['project_id'], source={'type': 'user', 'reference': 'subagents'})
    migrate(vault)
    # ACTIVE without owner approval: a user decision would be written directly.
    write_json(RuntimeConfig(vault).path, {'schema_version': 1, 'mode': 'ACTIVE', 'project_ids': [project['project_id']],
                                          'local_model': None, 'transcript_roots': {'claude': [str(trusted)], 'codex': [str(trusted)]}})
    directory = trusted / re.sub(r'[^A-Za-z0-9]', '-', str(vault.resolve()))
    directory.mkdir()
    transcript = directory / 'orchestrator.jsonl'
    transcript.write_text(json.dumps(_tool_result(REPORT, session='orchestrator')) + '\n', encoding='utf-8')

    assert enqueue(vault, 'claude', {'session_id': 'orchestrator', 'cwd': str(vault),
                                     'transcript_path': str(transcript)})['status'] == 'QUEUED'
    assert Worker(vault).once()['status'] == 'PROCESSED'

    assert MemoryStore(vault).load()['validated_memory'] == []
    pending = [item for item in ReviewStore(vault).list() if item.get('status', 'PENDING') == 'PENDING']
    texts = {json.dumps(item, ensure_ascii=False) for item in pending}
    assert any(FINDING_1 in text for text in texts)


def test_subagent_start_is_installed_for_claude_only():
    assert 'SubagentStart' in CLIENT_EVENTS['claude']
    assert 'SubagentStart' not in CLIENT_EVENTS['codex']
    additions = {'SubagentStart': {'hooks': [{'type': 'command', 'command': 'x'}]}}
    merged = merge_hooks({}, additions)
    assert merged['hooks']['SubagentStart'] == [additions['SubagentStart']]
    assert merge_hooks(merged, {}, additions) == {'hooks': {}}


def test_subagent_start_gives_memory_and_instruction(runtime, monkeypatch):  # noqa: F811
    vault, _ = runtime
    monkeypatch.setattr(launcher, 'ensure_service', lambda *a, **k: True)
    monkeypatch.setattr(launcher, 'request_service', lambda *a, **k: {
        'delivery_approved': True, 'delivered': True, 'provider': 'V1', 'context': '## Proje hafızası\n- SQLite kullanılıyor.'})
    output = launcher.hook(vault, 'claude', 'SubagentStart',
                           {'session_id': 's', 'agent_id': 'a1', 'agent_type': 'Explore', 'cwd': str(vault)})
    context = output['hookSpecificOutput']['additionalContext']
    assert output['hookSpecificOutput']['hookEventName'] == 'SubagentStart'
    assert context.startswith('## Proje hafızası')
    assert context.endswith(launcher.SUBAGENT_INSTRUCTION)


def test_subagent_start_without_service_still_asks_for_findings(runtime, monkeypatch):  # noqa: F811
    vault, _ = runtime
    monkeypatch.setattr(launcher, 'ensure_service', lambda *a, **k: False)
    output = launcher.hook(vault, 'claude', 'SubagentStart', {'session_id': 's', 'agent_id': 'a1', 'cwd': str(vault)})
    assert output['hookSpecificOutput']['additionalContext'] == launcher.SUBAGENT_INSTRUCTION


def test_subagent_start_outside_registered_projects_is_silent(runtime, tmp_path):  # noqa: F811
    vault, _ = runtime
    elsewhere = tmp_path / 'not-registered'
    elsewhere.mkdir()
    assert launcher.hook(vault, 'claude', 'SubagentStart', {'session_id': 's', 'agent_id': 'a1', 'cwd': str(elsewhere)}) == {}


def test_subagent_start_is_off_when_runtime_is_off(runtime):  # noqa: F811
    vault, _ = runtime
    config = RuntimeConfig(vault).load()
    config['mode'] = 'OFF'
    write_json(RuntimeConfig(vault).path, config)
    assert launcher.hook(vault, 'claude', 'SubagentStart', {'session_id': 's', 'agent_id': 'a1', 'cwd': str(vault)}) == {}
