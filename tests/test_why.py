"""`why`: a memory back to its source (2026-10-14)."""

import json
import re

import pytest

from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime.install import transcript_retention
from brain_eleven.runtime.migration import migrate
from brain_eleven.runtime.storage import RuntimeConfig, write_json
from brain_eleven.runtime.why import why
from brain_eleven.runtime.worker import Worker, enqueue
from brain_eleven.state import StateService

DECISION = 'Bundan sonra deploylari cuma günü yapmayacağız çünkü hafta sonu destek yok.'


@pytest.fixture
def captured(tmp_path):
    trusted = tmp_path / 'trusted'
    trusted.mkdir()
    vault = tmp_path / 'vault'
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    StateService(vault).init_project(project['project_id'], source={'type': 'user', 'reference': 'why'})
    migrate(vault)
    write_json(RuntimeConfig(vault).path, {'schema_version': 1, 'mode': 'ACTIVE', 'project_ids': [project['project_id']],
                                          'local_model': None, 'transcript_roots': {'claude': [str(trusted)], 'codex': [str(trusted)]}})
    directory = trusted / re.sub(r'[^A-Za-z0-9]', '-', str(vault.resolve()))
    directory.mkdir()
    transcript = directory / 'sess-why.jsonl'
    transcript.write_text(json.dumps({'type': 'user', 'sessionId': 'sess-why', 'timestamp': '2026-10-14T10:00:00Z',
                                      'message': {'role': 'user', 'content': DECISION}}) + '\n', encoding='utf-8')
    assert enqueue(vault, 'claude', {'session_id': 'sess-why', 'cwd': str(vault), 'transcript_path': str(transcript)})['status'] == 'QUEUED'
    assert Worker(vault).once()['status'] == 'PROCESSED'
    memory = MemoryStore(vault).load()['validated_memory'][0]
    return vault, transcript, memory['memory_id']


def test_why_shows_the_owner_message_the_memory_came_from(captured):
    vault, _, memory_id = captured
    result = why(vault, memory_id)
    assert result['content'] == DECISION and result['status'] == 'active'
    [source] = result['sources']
    assert source['status'] == 'FOUND' and source['role'] == 'user' and source['client'] == 'claude'
    assert source['quote'] == DECISION


def test_deleted_transcript_is_reported_not_guessed(captured):
    vault, transcript, memory_id = captured
    transcript.unlink()
    [source] = why(vault, memory_id)['sources']
    assert source['status'] == 'SOURCE_DELETED' and 'quote' not in source


def test_changed_transcript_is_never_quoted(captured):
    vault, transcript, memory_id = captured
    original = transcript.read_text(encoding='utf-8')
    transcript.write_text(original.replace('cuma', 'pazartesi'), encoding='utf-8')
    [source] = why(vault, memory_id)['sources']
    assert source['status'] == 'SOURCE_CHANGED' and 'quote' not in source


def test_unknown_memory_and_memory_without_evidence(captured, monkeypatch):
    vault, _, _ = captured
    with pytest.raises(ValueError):
        why(vault, 'mem_yok')
    monkeypatch.setattr(MemoryStore, 'load', lambda self: {'validated_memory': [
        {'memory_id': 'mem_manual', 'content': 'Elle yazılmış.', 'evidence_refs': []}]})
    result = why(vault, 'mem_manual')
    assert result['sources'] == [] and result['note']


def test_transcript_retention_advice(tmp_path):
    assert transcript_retention(tmp_path)['ok'] is False
    assert 'cleanupPeriodDays' in transcript_retention(tmp_path)['advice']
    write_json(tmp_path / '.claude' / 'settings.json', {'cleanupPeriodDays': 365})
    assert transcript_retention(tmp_path) == {'claude_days': 365, 'ok': True}
