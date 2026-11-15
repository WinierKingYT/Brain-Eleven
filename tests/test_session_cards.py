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
    assert context.startswith(session_cards.CONTEXT_HEADING) and context.endswith('- bir şey')
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


def test_compact_summary_keeps_where_it_stopped_done_and_pending(runtime, tmp_path):  # noqa: F811
    vault, project_id = runtime
    project = _project(vault, project_id)
    summary = ('Summary:\n1. Primary Request and Intent:\n   - Temizlik.\n'
               '5. Problem Solving:\n   - Kuyruk ayıklandı, 16 aday kabul edildi.\n     - alt satır\n'
               '   - Eski sorular yenilendi.\n   - Üçüncü madde karta girmez.\n'
               '7. Pending Tasks:\n   - anahtar AKIAIOSFODNN7EXAMPLE ile bağlan\n   - Eski kurulum betiğini silmek.\n'
               '8. Current Work:\n   Dört dersi temiz haliyle yeniden kaydediyordum.\n'
               '9. Optional Next Step:\n   Kapanış mesajını yazmak.\n')
    session_cards.update(vault, project, capture_session_key('claude', 's'), _messages(
        vault, project_id, tmp_path, 's', [_user(summary, isCompactSummary=True)]))
    note = _note(vault, project)
    assert '- Sıkıştırmada kalınan yer: Dört dersi temiz haliyle yeniden kaydediyordum.' in note
    assert '- Yapılan: Kuyruk ayıklandı, 16 aday kabul edildi. · Eski sorular yenilendi.' in note
    assert '- Yarım kalan: Eski kurulum betiğini silmek.' in note
    assert '- Sıradaki: Kapanış mesajını yazmak.' in note
    assert 'AKIA' not in note and 'Üçüncü' not in note


def test_after_compaction_the_session_gets_its_own_card_first(runtime, tmp_path):  # noqa: F811
    from brain_eleven.runtime.context import compile_context
    vault, project_id = runtime
    project = _project(vault, project_id)
    for session, text in (('current', 'Kart işini bitirelim.'), ('other', 'Başka oturumun isteği.')):
        session_cards.update(vault, project, capture_session_key('claude', session), _messages(
            vault, project_id, tmp_path, session, [_user(text)]))
    fresh = compile_context(vault, vault, '', client='claude', session='current', turn='bootstrap', event='SessionStart')
    assert 'Kart işini bitirelim.' not in fresh['context']
    after = compile_context(vault, vault, '', client='claude', session='current', turn='compact:1', event='SessionStart')
    assert 'Bu oturum (sıkıştırmadan önce)' in after['context']
    assert after['context'].index('Kart işini bitirelim.') < after['context'].index('Başka oturumun isteği.')


def test_session_start_shows_state_without_stale_or_cut_lines(runtime, tmp_path):  # noqa: F811
    from brain_eleven.runtime import receipts
    vault, project_id = runtime
    project = _project(vault, project_id)
    summary = ('Summary:\n5. Problem Solving:\n   - Kuyruk ayıklandı, 16 aday kabul edildi.\n'
               '8. Current Work:\n   Dört dersi yeniden kaydediyordum.\n9. Optional Next Step:\n   Kapanış mesajını yazmak.\n')
    key = capture_session_key('claude', 'old')
    session_cards.update(vault, project, key, _messages(vault, project_id, tmp_path, 'old', [_user(summary, isCompactSummary=True)]))
    assert '- Sıradaki: Kapanış mesajını yazmak.' in _note(vault, project)
    # The owner asked for more after that summary: where it stopped is no longer true.
    session_cards.update(vault, project, key, _messages(vault, project_id, tmp_path, 'old2', [_user('Şimdi PR açalım.')]))
    note = _note(vault, project)
    assert 'Kapanış mesajını yazmak.' not in note and 'Dört dersi yeniden' not in note
    assert '- Yapılan: Kuyruk ayıklandı, 16 aday kabul edildi.' in note

    receipts.submit(vault, vault, 'Birinci iş bitti.', next_step='İkinci işe başla')
    receipts.submit(vault, vault, 'İkinci iş bitti.', next_step='Üçüncü işe başla')
    context = session_cards.context(vault, project_id)
    assert 'Üçüncü işe başla' in context and 'İkinci işe başla' not in context
    assert 'İkinci işe başla' in _note(vault, project)  # the note keeps every receipt whole

    session_cards.update(vault, project, capture_session_key('claude', 'big'), _messages(
        vault, project_id, tmp_path, 'big', [_user('Uzun istek ' + 'kelime ' * 20), _assistant('yanıt ' * 60)]))
    short = session_cards.context(vault, project_id, limit=500)
    assert short.endswith(')') or short.splitlines()[-1].startswith('- ')  # ends at a whole block
    assert '### ' not in short or 'son güncelleme' in short.splitlines()[-1]


def test_model_report_card_reaches_every_session_start(tmp_path):
    from brain_eleven.memory import MemoryStore
    from brain_eleven.runtime.context import compile_context
    from brain_eleven.runtime.memory_notes import set_topic
    from tests.test_memclaim01_claim_key import NEW_TIME, _accept, _review_item
    from tests.test_memclaim01_claim_key import _runtime as shadow_runtime
    vault, _ = shadow_runtime(tmp_path, shadow_accept=True)
    _accept(vault, _review_item(tmp_path, vault, 'k1', 'We decided that reviewers rerun the suite because the model claims tests passed without running them.', NEW_TIME))
    _accept(vault, _review_item(tmp_path, vault, 'k2', 'We decided the dashboard stays read-only.', NEW_TIME))
    ids = {('tests passed' in m['content']): m['memory_id'] for m in MemoryStore(vault).load()['validated_memory']}
    set_topic(vault, [ids[True]], 'Model karnesi - Opus 5.5')
    set_topic(vault, [ids[False]], 'Arayüz')

    def start(turn):
        return compile_context(vault, vault, '', client='claude', session='s', turn=turn, event='SessionStart')['context']
    for context in (start('bootstrap'), start('subagent_x')):
        block = context.split('## MODEL KARNESİ', 1)[1].split('\n\n##', 1)[0]
        assert '### Opus 5.5' in block and 'claims tests passed without running them' in block
        assert 'dashboard' not in block


def test_opening_a_skill_brings_its_why_notes(tmp_path):
    from brain_eleven.memory import MemoryStore
    from brain_eleven.runtime import launcher
    from brain_eleven.runtime.install import CLIENT_EVENTS, install
    from brain_eleven.runtime.memory_notes import set_topic
    from tests.test_memclaim01_claim_key import NEW_TIME, _accept, _review_item
    from tests.test_memclaim01_claim_key import _runtime as shadow_runtime
    vault, _ = shadow_runtime(tmp_path, shadow_accept=True)
    _accept(vault, _review_item(tmp_path, vault, 'k1', 'We decided that armor textures stay 64x32 because the server pack rejects larger sheets.', NEW_TIME))
    _accept(vault, _review_item(tmp_path, vault, 'k2', 'We decided the dashboard stays read-only.', NEW_TIME))
    ids = {('armor' in m['content']): m['memory_id'] for m in MemoryStore(vault).load()['validated_memory']}
    set_topic(vault, [ids[True]], 'Skill - minecraft-armor')
    set_topic(vault, [ids[False]], 'Skill - baska')
    base = {'session_id': 's', 'cwd': str(vault)}

    def note(event, **fields):
        output = launcher.hook(vault, 'claude', event, {**base, **fields})
        return output.get('hookSpecificOutput', {}) if output else {}
    by_tool = note('PostToolUse', tool_name='Skill', tool_input={'skill': 'plugin:minecraft-armor'})
    typed = note('UserPromptExpansion', expansion_type='slash_command', command_name='minecraft-armor', prompt='/minecraft-armor')
    assert by_tool['hookEventName'] == 'PostToolUse' and typed['hookEventName'] == 'UserPromptExpansion'
    for text in (by_tool['additionalContext'], typed['additionalContext']):
        assert 'server pack rejects larger sheets' in text and 'dashboard' not in text
    assert note('PostToolUse', tool_name='Skill', tool_input={'skill': 'notsuz'}) == {}
    assert note('PostToolUse', tool_name='Bash', tool_input={'command': 'ls'}) == {}
    assert {'PostToolUse', 'UserPromptExpansion'} <= set(CLIENT_EVENTS['claude'])
    assert not {'PostToolUse', 'UserPromptExpansion'} & set(CLIENT_EVENTS['codex'])
    home = tmp_path / 'home'
    install(vault, home=home, clients=('claude',))
    hooks = json.loads((home / '.claude' / 'settings.json').read_text(encoding='utf-8'))['hooks']
    assert [entry.get('matcher') for entry in hooks['PostToolUse']] == ['Skill']
