"""Work outcome receipts (2026-10-14)."""

from datetime import date
import json

import pytest

from brain_eleven.__main__ import main
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime import receipts, session_cards
from brain_eleven.runtime.recap import recap
from tests.test_pre13_runtime import runtime  # noqa: F401  (fixture)


def test_receipt_is_recorded_once_and_shown_in_the_project_note(runtime):  # noqa: F811
    vault, project_id = runtime
    first = receipts.submit(vault, vault, 'PR #75 açıldı: sahip notları her oturumda.', next_step='CI sonucunu kontrol et.',
                            sources=['brain_eleven/runtime/companion.py', '#75', 'abc1234'], client='claude')
    again = receipts.submit(vault, vault, 'PR #75 açıldı: sahip notları her oturumda.',
                            sources=['brain_eleven/runtime/companion.py', '#75', 'abc1234'])
    assert first['status'] == 'RECORDED' and again['status'] == 'DUPLICATE'
    assert again['receipt_id'] == first['receipt_id'] and again['client'] == 'claude'
    project = ProjectRegistry(vault).get(project_id)
    note = session_cards._note_path(vault, project).read_text(encoding='utf-8')
    assert session_cards.RECEIPTS_HEADING in note
    assert 'PR #75 açıldı: sahip notları her oturumda. → sıradaki: CI sonucunu kontrol et.' in note
    assert '`#75`' in note


@pytest.mark.parametrize('source', ['/home/me/secret/file.py', 'C:/Users/me/x.py', '~/x', '../outside.md', 'a b'])
def test_absolute_or_escaping_sources_are_refused(runtime, source):  # noqa: F811
    vault, _ = runtime
    with pytest.raises(ValueError):
        receipts.submit(vault, vault, 'Bir iş bitti ve kaydediliyor.', sources=[source])


def test_unsafe_or_oversized_summaries_are_refused(runtime, tmp_path):  # noqa: F811
    vault, _ = runtime
    with pytest.raises(ValueError):
        receipts.submit(vault, vault, 'anahtar AKIAIOSFODNN7EXAMPLE eklendi')
    with pytest.raises(ValueError):
        receipts.submit(vault, vault, 'x' * (receipts.SUMMARY_LIMIT + 1))
    elsewhere = tmp_path / 'not-enrolled'
    elsewhere.mkdir()
    with pytest.raises(ValueError):
        receipts.submit(vault, elsewhere, 'Kayıtsız klasörde iş bitti.')


def test_receipts_open_the_session_start_cards_and_recap(runtime):  # noqa: F811
    vault, project_id = runtime
    receipts.submit(vault, vault, 'Recap komutu eklendi ve test edildi.')
    context = session_cards.context(vault, project_id)
    assert context.startswith(session_cards.CONTEXT_HEADING) and 'Recap komutu eklendi' in context
    result = recap(vault, today=date.today())
    assert result['receipts'] == 1 and '### İş sonuçları (1)' in result['text']


def test_receipt_cli(runtime, capsys):  # noqa: F811
    vault, _ = runtime
    assert main(['--vault', str(vault), 'receipt', 'CLI ile bir iş sonucu kaydedildi.', '--project-root', str(vault),
                 '--source', 'README.md']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'RECORDED'
