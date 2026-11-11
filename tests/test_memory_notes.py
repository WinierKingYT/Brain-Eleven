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


def test_topic_is_set_listed_and_cleared_only_on_active_memories(runtime, capsys):  # noqa: F811
    import pytest

    vault, project_id = runtime
    document = MemoryStore(vault).load()
    MemoryStore(vault).replace({**document, 'validated_memory': _document(project_id)['validated_memory']})

    result = memory_notes.set_topic(vault, ['mem_a', 'mem_c', 'mem_missing'], 'Depolama')
    assert (result['updated'], result['not_found']) == (['mem_a'], ['mem_c', 'mem_missing'])  # mem_c is resolved
    by_id = {m['memory_id']: m for m in MemoryStore(vault).load()['validated_memory']}
    assert by_id['mem_a']['topic'] == 'Depolama' and 'topic' not in by_id['mem_c']
    assert by_id['mem_a']['content'] == 'SQLite yerel kalır.'

    listing = memory_notes.topics(vault, project_id)
    assert listing['topics'] == {'Depolama': 1}
    assert [x['id'] for x in listing['untopiced']] == ['mem_b']  # mem_d holds a secret, mem_e is global

    revision = MemoryStore(vault).revision()
    memory_notes.set_topic(vault, ['mem_a'], 'Depolama')
    assert MemoryStore(vault).revision() == revision  # no change, no write
    for bad in ('a/b', 'x' * 41):
        with pytest.raises(ValueError):
            memory_notes.set_topic(vault, ['mem_a'], bad)

    assert main(['--vault', str(vault), 'topic', '', 'mem_a']) == 0
    assert memory_notes.topics(vault, project_id)['topics'] == {}
    capsys.readouterr()
    assert main(['--vault', str(vault), 'topic', '--project-root', str(vault)]) == 0
    assert '"untopiced"' in capsys.readouterr().out


def test_topic_records_move_to_their_own_linked_note_and_an_emptied_topic_note_stays(runtime, monkeypatch):  # noqa: F811
    vault, project_id = runtime
    title = memory_notes._name(ProjectRegistry(vault).get(project_id).get('project_label') or project_id)
    document = _document(project_id)
    document['validated_memory'][0]['topic'] = 'Depolama'
    memory_notes.render(vault, document)

    project_note = _note(vault, title)
    assert f'- [[{title}/Depolama|Depolama]] — 1 kayıt' in project_note
    assert 'SQLite yerel kalır.' not in project_note and 'Windows hook pythonw' in project_note
    assert '2 aktif kayıt.' in project_note
    topic_note = _note(vault, f'{title}/Depolama')
    assert 'SQLite yerel kalır.' in topic_note and f'[[{title}]] · 1 aktif kayıt.' in topic_note

    del document['validated_memory'][0]['topic']
    memory_notes.render(vault, document)
    assert 'Bu konuda aktif kayıt kalmadı.' in _note(vault, f'{title}/Depolama')
    assert 'SQLite yerel kalır.' in _note(vault, title)


def test_unapproved_record_stays_out_of_the_topic_note_when_approval_is_on(runtime):  # noqa: F811
    from brain_eleven.runtime.storage import RuntimeConfig, read_json, write_json
    vault, project_id = runtime
    cfg = RuntimeConfig(vault)
    write_json(cfg.path, {**read_json(cfg.path), 'b1_human_approval': True})
    title = memory_notes._name(ProjectRegistry(vault).get(project_id).get('project_label') or project_id)
    document = _document(project_id)
    document['validated_memory'][0]['topic'] = 'Depolama'   # approved
    document['validated_memory'][1]['topic'] = 'Depolama'   # mem_b: not approved
    memory_notes.render(vault, document)

    topic_note = _note(vault, f'{title}/Depolama')
    assert 'SQLite yerel kalır.' in topic_note and 'Windows hook pythonw' not in topic_note
    assert '`mem_b` · 2026-10-13 · onaysız' in _note(vault, title)  # still visible to the owner
