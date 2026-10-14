"""Yakala inbox (2026-10-14)."""

import json
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
    monkeypatch.setattr(yakala.os, 'name', 'posix')
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
