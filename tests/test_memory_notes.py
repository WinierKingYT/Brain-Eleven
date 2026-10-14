"""Readable memory notes derived from canonical memory (2026-10-14)."""

import asyncio
from types import SimpleNamespace

from brain_eleven.__main__ import main
from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime import memory_notes, service
from tests.test_pre13_runtime import runtime  # noqa: F401  (fixture)


def _memory(memory_id, content, kind, project_id, *, scope='project', status='active', approved=True):
    return {'memory_id': memory_id, 'content': content, 'type': kind, 'project_id': project_id, 'scope': scope,
            'status': status, 'timestamp': '2026-10-13T10:00:00Z', 'is_approved': approved}


def _document(project_id, revision=7):
    return {'revision': revision, 'validated_memory': [
        _memory('mem_a', 'SQLite yerel kalır.', 'decision', project_id),
        _memory('mem_b', 'Windows hook pythonw ile çalışır.', 'lesson', project_id, approved=False),
        _memory('mem_c', 'Eski, iptal edilmiş karar.', 'decision', project_id, status='resolved'),
        _memory('mem_d', 'Anahtar AKIAIOSFODNN7EXAMPLE ile bağlan.', 'fact', project_id),
        _memory('mem_e', 'Yanıtlar Türkçe olsun.', 'preference', '', scope='global'),
    ]}


def _note(vault, title):
    return (vault / memory_notes.NOTES_DIR / (title + '.md')).read_text(encoding='utf-8')


def test_project_note_lists_active_memories_by_type(runtime, monkeypatch):  # noqa: F811
    vault, project_id = runtime
    monkeypatch.setattr(MemoryStore, 'load', lambda self: _document(project_id))
    names = memory_notes.render(vault, _document(project_id))
    title = ProjectRegistry(vault).get(project_id).get('project_label') or project_id
    note = _note(vault, memory_notes._name(title))
    assert note.index('## Kararlar') < note.index('## Dersler')
    assert '- SQLite yerel kalır. <small>`mem_a` · 2026-10-13</small>' in note
    assert '`mem_b` · 2026-10-13 · onaysız' in note
    assert 'iptal edilmiş' not in note and 'AKIA' not in note
    assert '2 aktif kayıt.' in note
    assert 'Yanıtlar Türkçe olsun.' in _note(vault, memory_notes.GLOBAL_NOTE)
    assert memory_notes.GLOBAL_NOTE in names


def test_refresh_renders_only_when_revision_changes(runtime, monkeypatch):  # noqa: F811
    vault, project_id = runtime
    revision = {'value': 7}
    monkeypatch.setattr(MemoryStore, 'load', lambda self: _document(project_id, revision['value']))
    assert memory_notes.refresh(vault)['status'] == 'RENDERED'
    assert memory_notes.refresh(vault)['status'] == 'CURRENT'
    revision['value'] = 8
    assert memory_notes.refresh(vault)['status'] == 'RENDERED'
    assert memory_notes.refresh(vault, force=True)['status'] == 'RENDERED'


def test_service_refresh_is_throttled(runtime, monkeypatch):  # noqa: F811
    vault, _ = runtime
    calls = []
    monkeypatch.setattr(memory_notes, 'refresh', lambda v: calls.append(v))
    app = SimpleNamespace(state=SimpleNamespace(vault=vault))
    asyncio.run(service.maybe_memory_notes(app))
    asyncio.run(service.maybe_memory_notes(app))
    assert len(calls) == 1


def test_notes_cli_forces_a_render(runtime, capsys):  # noqa: F811
    vault, _ = runtime
    assert main(['--vault', str(vault), 'notes']) == 0
    assert '"RENDERED"' in capsys.readouterr().out
    assert (vault / memory_notes.NOTES_DIR).is_dir()
