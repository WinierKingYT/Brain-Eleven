"""Yakala inbox (2026-10-14)."""

import json
import os
import types
from pathlib import Path

import pytest

from brain_eleven.__main__ import main
from brain_eleven.runtime import yakala


def _item(vault, name):
    return (vault / yakala.INBOX / name).read_text(encoding='utf-8')


def test_link_text_and_file_land_in_the_inbox(tmp_path):
    vault = tmp_path / 'vault'
    link = yakala.add(vault, 'https://www.youtube.com/watch?v=abc123')
    text = yakala.add(vault, 'Bir fikir: oturum kartlarını haftalık özetle birleştir.\nİkinci satır.')
    source = tmp_path / 'rapor.pdf'
    source.write_bytes(b'%PDF-1.4 test')
    attached = yakala.add(vault, str(source))
    assert 'tür: bağlantı' in _item(vault, link['item']) and 'youtube.com watch' in link['item']
    assert 'tür: metin' in _item(vault, text['item']) and 'İkinci satır.' in _item(vault, text['item'])
    assert '![[rapor.pdf]]' in _item(vault, attached['item'])
    assert (vault / yakala.ATTACHMENTS / 'rapor.pdf').read_bytes() == b'%PDF-1.4 test'
    assert yakala.items(vault)['count'] == 3


def test_secrets_empty_and_oversized_text_are_refused(tmp_path):
    with pytest.raises(ValueError):
        yakala.add(tmp_path, 'anahtarım AKIAIOSFODNN7EXAMPLE')
    with pytest.raises(ValueError):
        yakala.add(tmp_path, '   ')
    with pytest.raises(ValueError):
        yakala.add(tmp_path, 'x' * (yakala.TEXT_LIMIT + 1))
    assert not (tmp_path / yakala.INBOX).exists()


def test_file_with_a_secret_is_not_copied(tmp_path):
    key = tmp_path / '.env'
    key.write_text('AWS_KEY=AKIAIOSFODNN7EXAMPLE', encoding='utf-8')
    with pytest.raises(ValueError):
        yakala.add(tmp_path / 'vault', str(key))
    assert not (tmp_path / 'vault' / yakala.ATTACHMENTS).exists()


def test_same_second_captures_do_not_overwrite(tmp_path):
    first = yakala.add(tmp_path, 'https://example.com/a')
    second = yakala.add(tmp_path, 'https://example.com/a')
    assert first['item'] != second['item']


def test_done_marks_and_links_and_rejects_paths_outside_the_inbox(tmp_path):
    item = yakala.add(tmp_path, 'https://example.com/makale')['item']
    yakala.done(tmp_path, item, '🧠 Bilgi/Bellek tasarımı.md')
    content = _item(tmp_path, item)
    assert 'durum: işlendi' in content and 'not: [[Bellek tasarımı]]' in content
    assert 'https://example.com/makale' in content.split('---\n', 2)[2]
    assert yakala.items(tmp_path)['count'] == 0 and yakala.items(tmp_path, status=None)['count'] == 1
    with pytest.raises(ValueError):
        yakala.done(tmp_path, '../../etc/passwd')


def test_clipboard_capture_uses_the_clipboard(tmp_path, monkeypatch):
    monkeypatch.setattr(yakala, 'read_clipboard', lambda: 'https://example.com/pano')
    assert yakala.clipboard(tmp_path)['status'] == 'CAPTURED'
    assert yakala.items(tmp_path)['items'][0]['kaynak'] == 'https://example.com/pano'


def test_windows_shortcut_script_targets_pythonw_with_the_hotkey(tmp_path):
    python = tmp_path / 'python.exe'
    python.write_text('')
    (tmp_path / 'pythonw.exe').write_text('')
    script = yakala.shortcut_script(tmp_path / "Eleven's vault", python=python, root=tmp_path / 'repo')
    assert "pythonw.exe'" in script and "$link.Hotkey = 'CTRL+ALT+B'" in script
    assert "Eleven''s vault" in script and 'yakala pano' in script
    assert yakala.SHORTCUT_NAME in script


def test_non_windows_install_returns_the_command(tmp_path, monkeypatch):
    # Patch only the module's os: changing os.name globally breaks pathlib on Windows.
    monkeypatch.setattr(yakala, 'os', types.SimpleNamespace(name='posix'))
    result = yakala.install_shortcut(tmp_path)
    assert result['status'] == 'MANUAL' and 'yakala pano' in result['command']


def test_cli_add_and_list(tmp_path, capsys):
    vault = tmp_path / 'vault'
    assert main(['--vault', str(vault), 'yakala', 'ekle', 'https://example.com/x']) == 0
    capsys.readouterr()
    assert main(['--vault', str(vault), 'yakala', 'liste']) == 0
    assert json.loads(capsys.readouterr().out)['count'] == 1


def test_web_clipper_template_writes_into_the_inbox():
    template = json.loads(Path('templates/obsidian/beyne-at.json').read_text(encoding='utf-8'))
    assert template['path'] == str(yakala.INBOX)
    assert {p['name']: p['value'] for p in template['properties']}['durum'] == yakala.PENDING


@pytest.mark.skipif(os.name != 'nt', reason='Windows clipboard API')
def test_windows_clipboard_declares_64_bit_handle_for_unlock():
    import ctypes
    from ctypes import wintypes

    assert isinstance(yakala._windows_clipboard(), str)
    assert ctypes.windll.kernel32.GlobalUnlock.argtypes == [wintypes.HGLOBAL]


SECRET_TEXT = 'anahtarım AKIAIOSFODNN7EXAMPLE'


def _last(vault):
    from brain_eleven.runtime.storage import RuntimeConfig, read_json
    return read_json(RuntimeConfig(vault).root / 'last-yakala.json')


@pytest.mark.parametrize('text, code', [('   ', 'EMPTY'), (SECRET_TEXT, 'SECRET'),
                                        ('x' * (yakala.TEXT_LIMIT + 1), 'TOO_LONG')],
                         ids=['empty', 'secret', 'too-long'])
def test_clipboard_failure_is_logged_with_a_code_and_reraised(tmp_path, monkeypatch, text, code):
    monkeypatch.setattr(yakala, 'read_clipboard', lambda: text)
    with pytest.raises(ValueError):
        yakala.clipboard(tmp_path)
    record = _last(tmp_path)
    assert (record['status'], record['error']) == ('FAILED', code)
    assert 'AKIA' not in json.dumps(record) and 'anahtar' not in json.dumps(record)


def test_clipboard_unexpected_error_logs_only_the_class_name(tmp_path, monkeypatch):
    def busy():
        raise OSError('Clipboard is busy: C:/secret/path')
    monkeypatch.setattr(yakala, 'read_clipboard', busy)
    with pytest.raises(OSError):
        yakala.clipboard(tmp_path)
    record = _last(tmp_path)
    assert record['error'] == 'OSError' and 'secret' not in json.dumps(record)


def test_liste_shows_last_attempt_and_tolerates_a_missing_or_corrupt_file(tmp_path, monkeypatch, capsys):
    from brain_eleven.runtime.storage import RuntimeConfig
    assert main(['--vault', str(tmp_path), 'yakala', 'liste']) == 0
    assert 'son_deneme' not in json.loads(capsys.readouterr().out)
    monkeypatch.setattr(yakala, 'read_clipboard', lambda: 'https://example.com/ok')
    yakala.clipboard(tmp_path)
    assert yakala.last_attempt(tmp_path)['status'] == 'CAPTURED'
    monkeypatch.setattr(yakala, 'read_clipboard', lambda: '  ')
    with pytest.raises(ValueError):
        yakala.clipboard(tmp_path)
    main(['--vault', str(tmp_path), 'yakala', 'liste'])
    assert json.loads(capsys.readouterr().out)['son_deneme']['error'] == 'EMPTY'
    (RuntimeConfig(tmp_path).root / 'last-yakala.json').write_text('{bozuk', encoding='utf-8')
    assert yakala.last_attempt(tmp_path) is None
    assert main(['--vault', str(tmp_path), 'yakala', 'liste']) == 0
