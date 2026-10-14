"""Owner notes Core.md / Kurallar.md in every session (2026-10-14)."""

from brain_eleven.runtime import companion, session_cards
from brain_eleven.runtime.context import _add_companion, _add_session_cards, _asks_continuity
from brain_eleven.runtime.worker import capture_session_key
from brain_eleven.projects.registry import ProjectRegistry
from tests.test_pre13_runtime import runtime  # noqa: F401  (fixture)
from tests.test_session_cards import _messages, _user


def _write(vault, name, text):
    path = vault / companion.COMPANION_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def test_starters_are_created_once_and_never_overwritten(tmp_path):
    assert sorted(companion.ensure_starters(tmp_path)) == [companion.CORE, companion.RULES]
    path = tmp_path / companion.COMPANION_DIR / companion.CORE
    path.write_text('# Core\n- Adım Eleven.\n', encoding='utf-8')
    assert companion.ensure_starters(tmp_path) == []
    assert 'Eleven' in path.read_text(encoding='utf-8')


def test_untouched_starters_give_only_the_growth_hint(tmp_path):
    companion.ensure_starters(tmp_path)
    assert companion.section(tmp_path) == ''
    hinted = companion.section(tmp_path, hints=True)
    assert companion.EMPTY_HINT in hinted and companion.RULE_HINT in hinted


def test_rules_come_first_secrets_are_dropped_and_long_notes_are_cut(tmp_path):
    _write(tmp_path, companion.CORE, '---\ntitle: x\n---\n# Core\n- Adım Eleven, Türkçe konuşurum.\n'
           + '- uzun satır burada duruyor.\n' * 200)
    _write(tmp_path, companion.RULES, '# Kurallar\n<!-- yorum -->\n- **kural:** Kısa cevap ver. **neden:** zaman.\n'
           '- token ghp_abcdefghijklmnopqrstuvwxyz0123456789 kullan\n')
    text = companion.section(tmp_path)
    assert text.startswith(companion.HEADING)
    assert text.index('Kısa cevap ver') < text.index('Adım Eleven')
    assert 'ghp_' not in text and 'yorum' not in text and 'title: x' not in text
    assert 'kısaltıldı' in text and len(text) < 3200


def test_continuity_questions_are_recognised():
    for prompt in ('Nerede kalmıştık?', 'nerede kalmistik', 'Beni tanıyor musun', 'son durum ne',
                   'tatilden döndüm, ne yapıyorduk', 'where were we', 'Geçen sefer ne yaptık'):
        assert companion.returning(prompt), prompt
        assert _asks_continuity(prompt)
    for prompt in ('Kargo nerede kaldı?', 'Bu fonksiyonu düzelt', ''):
        assert not companion.returning(prompt), prompt


def test_owner_notes_open_the_context_before_cards_and_memory(runtime, tmp_path):  # noqa: F811
    vault, project_id = runtime
    _write(vault, companion.RULES, '# Kurallar\n- **kural:** Önce sonucu söyle. **neden:** hız.\n')
    project = ProjectRegistry(vault).get(project_id)
    session_cards.update(vault, project, capture_session_key('claude', 'old'), _messages(
        vault, project_id, tmp_path, 'old', [_user('Eski oturum isteği.')]))
    result = {'status': 'SUCCESS', 'context': '## Hafıza\n- bir şey', 'project_id': project_id, 'selected_ids': ['m']}
    _add_session_cards(vault, result, client='claude', session='new')
    _add_companion(vault, result, client='claude', hints=True)
    context = result['context']
    assert context.startswith(companion.HEADING)
    assert context.index('Önce sonucu söyle') < context.index(session_cards.CONTEXT_HEADING) < context.index('## Hafıza')
    assert result['delivered'] is True


def test_nothing_is_added_outside_native_clients_or_disabled_scope(runtime):  # noqa: F811
    vault, project_id = runtime
    _write(vault, companion.RULES, '# Kurallar\n- **kural:** X. **neden:** Y.\n')
    manual = {'status': 'SUCCESS', 'context': '', 'project_id': project_id}
    _add_companion(vault, manual, client='manual')
    off = {'status': 'SCOPE_DISABLED', 'context': '', 'project_id': project_id}
    _add_companion(vault, off, client='claude')
    assert manual['context'] == '' and off['context'] == ''
