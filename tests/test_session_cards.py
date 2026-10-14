"""Session cards and open threads (2026-10-13)."""

import json

from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime import session_cards
from brain_eleven.runtime.context import _add_session_cards
from brain_eleven.runtime.evidence import read_increment
from brain_eleven.runtime.worker import capture_session_key
from brain_eleven.state import StateService, StateStore
from tests.test_pre13_runtime import _native_path, runtime  # noqa: F401  (fixture)


def _user(text, at='2026-10-13T19:00:00Z', **extra):
    return {'type': 'user', 'timestamp': at, 'message': {'role': 'user', 'content': text}, **extra}


def _assistant(text, at='2026-10-13T19:01:00Z'):
    return {'type': 'assistant', 'timestamp': at, 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': text}]}}


def _messages(vault, project_id, tmp_path, session, documents):
    path = _native_path(tmp_path, vault, 'claude', session, documents)
    batch, _ = read_increment(vault, path, 'claude', session, project_id, '2026-10-13T19:05:00Z')
    return batch.messages


def _project(vault, project_id):
    return ProjectRegistry(vault).get(project_id)


def _note(vault, project):
    return session_cards._note_path(vault, project).read_text(encoding='utf-8')


def test_card_records_first_and_last_request_and_last_answer(runtime, tmp_path):  # noqa: F811
    vault, project_id = runtime
    project = _project(vault, project_id)
    key = capture_session_key('claude', 's1')
    session_cards.update(vault, project, key, _messages(vault, project_id, tmp_path, 's1', [
        _user('Alt ajan desteğini ekleyelim, SubagentStart hook kullanalım.'),
        _assistant('Hook eklendi ve testler geçti.'),
    ]))
    session_cards.update(vault, project, key, _messages(vault, project_id, tmp_path, 's1b', [
        _user('Şimdi PR açalım.', at='2026-10-13T20:00:00Z'),
        _assistant('PR #69 açıldı.', at='2026-10-13T20:01:00Z'),
    ]))
    note = _note(vault, project)
    assert note.count('### ') == 1
    assert '· claude · Alt ajan desteğini ekleyelim, SubagentStart hook kullanalım.' in note
    assert '- Son istek: Şimdi PR açalım.' in note
    assert '- Son yanıt: PR #69 açıldı.' in note
    assert '- 2 istem' in note


def test_summary_next_step_becomes_the_next_line(runtime, tmp_path):  # noqa: F811
    vault, project_id = runtime
    project = _project(vault, project_id)
    summary = 'Summary:\n1. Primary Request:\n   - Temizlik.\n9. Optional Next Step:\n   - Last-Session kartlarını eklemek.\n'
    session_cards.update(vault, project, capture_session_key('claude', 's'), _messages(
        vault, project_id, tmp_path, 's', [_user(summary, isCompactSummary=True)]))
    assert '- Sıradaki: Last-Session kartlarını eklemek.' in _note(vault, project)


def test_secrets_and_harness_turns_never_reach_the_note(runtime, tmp_path):  # noqa: F811
    vault, project_id = runtime
    project = _project(vault, project_id)
    session_cards.update(vault, project, capture_session_key('claude', 's'), _messages(vault, project_id, tmp_path, 's', [
        _user('anahtar AKIAIOSFODNN7EXAMPLE ile bağlan'),
        _user('<task-notification>arka plan işi bitti</task-notification>'),
        _assistant('Tamam.'),
    ]))
    note = _note(vault, project)
    assert 'AKIA' not in note and 'task-notification' not in note
    assert '- 1 istem' in note


def test_overflow_moves_oldest_cards_verbatim_to_the_archive(runtime, tmp_path):  # noqa: F811
    vault, project_id = runtime
    project = _project(vault, project_id)
    for index in range(30):
        at = f'2026-10-{index % 28 + 1:02d}T10:00:00Z'
        session_cards.update(vault, project, capture_session_key('claude', f's{index}'), _messages(
            vault, project_id, tmp_path, f's{index}', [_user(f'Oturum {index} için uzunca bir istek metni yazıyoruz burada.', at=at)]))
    note = _note(vault, project)
    cards_section = note.split(session_cards.HEADING, 1)[1]
    assert len(cards_section) <= session_cards.CARD_SECTION_LIMIT + 200
    archive = list((vault / session_cards.ARCHIVE_DIR).glob('*.md'))
    archived = '\n'.join(path.read_text(encoding='utf-8') for path in archive)
    for index in range(30):
        text = f'Oturum {index} için'
        assert (text in note) != (text in archived)


def test_open_state_items_are_listed_as_threads(runtime, tmp_path):  # noqa: F811
    vault, project_id = runtime
    project = _project(vault, project_id)
    revision = StateStore(vault).project_revision(project_id)
    StateService(vault).add_work_item(project_id, text='Recap komutunu eklemek.', expected_revision=revision,
                                      source={'type': 'user', 'reference': 'test'})
    session_cards.update(vault, project, capture_session_key('claude', 's'), _messages(
        vault, project_id, tmp_path, 's', [_user('Devam edelim.')]))
    assert '- İş: Recap komutunu eklemek.' in _note(vault, project)


def test_session_start_gets_the_latest_cards_except_its_own(runtime, tmp_path):  # noqa: F811
    vault, project_id = runtime
    project = _project(vault, project_id)
    for index, session in enumerate(['old', 'mid', 'new', 'current']):
        session_cards.update(vault, project, capture_session_key('claude', session), _messages(
            vault, project_id, tmp_path, session, [_user(f'İstek {session} metni.', at=f'2026-10-1{index}T10:00:00Z')]))
    result = {'status': 'SUCCESS', 'context': '## Hafıza\n- bir şey', 'project_id': project_id,
              'delivered': True, 'delivery_approved': True, 'selected_ids': ['mem_1']}
    _add_session_cards(vault, result, client='claude', session='current')
    context = result['context']
    assert context.startswith('## Hafıza')
    assert 'İstek new metni.' in context and 'İstek mid metni.' in context
    assert 'İstek old metni.' not in context and 'İstek current metni.' not in context
    assert context.index('İstek new') < context.index('İstek mid')


def test_cards_alone_are_delivered_when_there_is_no_memory(runtime, tmp_path):  # noqa: F811
    vault, project_id = runtime
    project = _project(vault, project_id)
    session_cards.update(vault, project, capture_session_key('claude', 'a'), _messages(
        vault, project_id, tmp_path, 'a', [_user('Bir önceki iş.')]))
    result = {'status': 'SUCCESS', 'context': '', 'project_id': project_id, 'delivered': False,
              'delivery_approved': False, 'selected_ids': []}
    _add_session_cards(vault, result, client='claude', session='b')
    assert result['delivered'] is True and result['context'].startswith(session_cards.CONTEXT_HEADING)
    off = {'status': 'SCOPE_DISABLED', 'context': '', 'project_id': project_id}
    _add_session_cards(vault, off, client='claude', session='b')
    assert off['context'] == ''


def test_card_state_is_json_in_the_runtime_root(runtime, tmp_path):  # noqa: F811
    vault, project_id = runtime
    project = _project(vault, project_id)
    session_cards.update(vault, project, capture_session_key('claude', 's'), _messages(
        vault, project_id, tmp_path, 's', [_user('Kayıt testi.')]))
    state = json.loads(session_cards._state_path(vault, project_id).read_text(encoding='utf-8'))
    assert len(state['cards']) == 1
