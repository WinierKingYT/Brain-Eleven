"""recap: recent sessions and new memories without a model call (2026-10-14)."""

from datetime import date, datetime, timedelta

import pytest

from brain_eleven.__main__ import main
from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime import session_cards
from brain_eleven.runtime.recap import recap, window
from brain_eleven.runtime.worker import capture_session_key
from tests.test_pre13_runtime import runtime  # noqa: F401  (fixture)
from tests.test_session_cards import _messages, _user

TODAY = date(2026, 10, 14)


def _memory(content, timestamp, project_id, status='active'):
    return {'memory_id': 'mem_' + str(abs(hash(content)))[:12], 'id': -1, 'type': 'decision', 'content': content,
            'timestamp': timestamp, 'status': status, 'project_id': project_id, 'scope': 'project'}




def test_window_defaults_to_last_seven_local_days():
    start, end = window(today=TODAY)
    assert end - start == timedelta(days=7)
    assert end.date() == TODAY + timedelta(days=1)


def test_window_bounds_and_errors():
    start, end = window(since='2026-09-24', until='2026-09-24', today=TODAY)
    assert end - start == timedelta(days=1)
    with pytest.raises(ValueError):
        window(days=3, since='2026-09-24', today=TODAY)
    with pytest.raises(ValueError):
        window(days=0, today=TODAY)
    with pytest.raises(ValueError):
        window(since='2026-09-24T18:30:00', today=TODAY)
    with pytest.raises(ValueError):
        window(since='2026-10-02', until='2026-10-01', today=TODAY)
    start, _ = window(since='2026-09-24T18:30:00+03:00', today=TODAY)
    assert start == datetime.fromisoformat('2026-09-24T18:30:00+03:00')


def test_recap_lists_recent_sessions_and_memories_only(runtime, tmp_path, monkeypatch):  # noqa: F811
    vault, project_id = runtime
    project = ProjectRegistry(vault).get(project_id)
    session_cards.update(vault, project, capture_session_key('claude', 'recent'), _messages(
        vault, project_id, tmp_path, 'recent', [_user('recent oturumunun isteği.', at='2026-10-13T10:00:00Z')]))
    session_cards.update(vault, project, capture_session_key('claude', 'old'), _messages(
        vault, project_id, tmp_path, 'old', [_user('old oturumunun isteği.', at='2026-09-01T10:00:00Z')]))
    memories = [
        _memory('Kartlar 3000 karakterde arşive taşınır.', '2026-10-12T09:00:00Z', project_id),
        _memory('Eski karar.', '2026-08-01T09:00:00Z', project_id),
        _memory('Emekli edilmiş karar.', '2026-10-12T09:00:00Z', project_id, status='resolved'),
    ]
    monkeypatch.setattr(MemoryStore, 'load', lambda self: {'validated_memory': memories})

    result = recap(vault, today=TODAY)
    assert (result['sessions'], result['memories']) == (1, 1)
    assert 'recent oturumunun isteği.' in result['text'] and 'old oturumunun' not in result['text']
    assert '- [decision] Kartlar 3000 karakterde arşive taşınır.' in result['text']
    assert 'Eski karar' not in result['text'] and 'Emekli' not in result['text']

    september = recap(vault, since='2026-09-01', until='2026-09-01', today=TODAY)
    assert september['sessions'] == 1 and 'old oturumunun isteği.' in september['text']
    assert 'yok' in recap(vault, since='2026-07-01', until='2026-07-02', today=TODAY)['text']
    with pytest.raises(ValueError):
        recap(vault, project='bilinmeyen', today=TODAY)


def test_recap_cli_prints_text(runtime, capsys):  # noqa: F811
    vault, _ = runtime
    assert main(['--vault', str(vault), 'recap', '--days', '3']) == 0
    assert capsys.readouterr().out.startswith('# Son işler:')
