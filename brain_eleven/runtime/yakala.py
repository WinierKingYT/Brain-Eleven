"""Yakala: drop a link, a file or a piece of text into the vault inbox.

Items land in ``📥 Gelen/`` as small Markdown notes (status ``bekliyor``);
the ``beyin-yakala`` skill later reads them, writes knowledge notes under
``🧠 Bilgi/`` and marks each item ``işlendi``. Nothing here fetches a URL or
calls a model. Inspired by avenoxbeyin's Yakala (MIT); the Windows hotkey is
a Start Menu shortcut with a native shortcut key, so no listener runs.
"""
from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

INBOX = Path('📥 Gelen')
ATTACHMENTS = INBOX / 'Ekler'
KNOWLEDGE = Path('🧠 Bilgi')
TEXT_LIMIT = 100_000
FILE_LIMIT = 50 * 1024 * 1024
PENDING, DONE = 'bekliyor', 'işlendi'
HOTKEY = 'CTRL+ALT+B'
SHORTCUT_NAME = 'Beyne at.lnk'
_URL = re.compile(r'^https?://\S+$')
_FIELD = re.compile(r'^([^:\n]+): ?(.*)$')


def _slug(text, limit=50):
    text = re.sub(r'https?://(www\.)?', '', text)
    text = re.sub(r'[\\/:*?"<>|#^\[\]\x00-\x1f]+', ' ', text)
    return ' '.join(text.split())[:limit].strip(' .') or 'yakalanan'


def _frontmatter(fields):
    return '---\n' + ''.join(f'{key}: {value}\n' for key, value in fields.items()) + '---\n'


def _read(path):
    text = path.read_text(encoding='utf-8')
    fields, body = {}, text
    if text.startswith('---\n') and '\n---\n' in text[4:]:
        head, body = text[4:].split('\n---\n', 1)
        for line in head.splitlines():
            match = _FIELD.match(line)
            if match:
                fields[match.group(1).strip()] = match.group(2).strip()
    return fields, body


def _write_item(vault, kind, source, body):
    now = datetime.now().astimezone()
    root = Path(vault) / INBOX
    root.mkdir(parents=True, exist_ok=True)
    stem = f"{now.strftime('%Y-%m-%d %H%M%S')} {_slug(source)}"
    path, counter = root / (stem + '.md'), 2
    while path.exists():
        path, counter = root / f'{stem} ({counter}).md', counter + 1
    fields = {'tür': kind, 'kaynak': source.replace('\n', ' ')[:300], 'yakalandı': now.isoformat(timespec='seconds'),
              'durum': PENDING}
    path.write_text(_frontmatter(fields) + '\n' + body.rstrip() + '\n', encoding='utf-8')
    return path


def add(vault, value):
    """Capture a URL, an existing file path, or plain text."""
    from context_compiler_v2.safety import contains_secret
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Nothing to capture')
    value = value.strip()
    candidate = Path(value).expanduser()
    if '\n' not in value and len(value) < 1000 and candidate.is_file():
        if candidate.stat().st_size > FILE_LIMIT:
            raise ValueError('File is larger than 50 MB')
        target_dir = Path(vault) / ATTACHMENTS
        target_dir.mkdir(parents=True, exist_ok=True)
        target, counter = target_dir / candidate.name, 2
        while target.exists():
            target, counter = target_dir / f'{candidate.stem} ({counter}){candidate.suffix}', counter + 1
        shutil.copy2(candidate, target)
        path = _write_item(vault, 'dosya', candidate.name, f'![[{target.name}]]')
    else:
        if len(value) > TEXT_LIMIT:
            raise ValueError('Text is longer than 100,000 characters')
        if contains_secret(value):
            raise ValueError('The text looks like it contains a secret; not captured')
        kind = 'bağlantı' if _URL.match(value) else 'metin'
        path = _write_item(vault, kind, value if kind == 'bağlantı' else value.split('\n', 1)[0], value)
    return {'status': 'CAPTURED', 'item': path.name}


def items(vault, *, status=PENDING):
    root = Path(vault) / INBOX
    found = []
    for path in sorted(root.glob('*.md')) if root.is_dir() else ():
        fields, _ = _read(path)
        if status is None or fields.get('durum') == status:
            found.append({'item': path.name, 'tür': fields.get('tür'), 'kaynak': fields.get('kaynak'),
                          'yakalandı': fields.get('yakalandı'), 'durum': fields.get('durum')})
    return {'items': found, 'count': len(found)}


def done(vault, item, note=None):
    """Mark an inbox item processed, optionally linking the knowledge note it became."""
    root = (Path(vault) / INBOX).resolve()
    path = (root / item).resolve()
    if path.parent != root or path.suffix != '.md' or not path.is_file():
        raise ValueError('Unknown inbox item')
    fields, body = _read(path)
    fields['durum'] = DONE
    fields['işlendi'] = datetime.now().astimezone().isoformat(timespec='seconds')
    if note:
        fields['not'] = f'[[{Path(note).stem}]]'
    path.write_text(_frontmatter(fields) + body, encoding='utf-8')
    return {'status': 'DONE', 'item': path.name}


def _windows_clipboard():
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    if not user32.OpenClipboard(None):
        raise OSError('Clipboard is busy')
    try:
        handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
        if not handle:
            return ''
        pointer = kernel32.GlobalLock(handle)
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def read_clipboard():
    if os.name == 'nt':
        return _windows_clipboard()
    for command in (['pbpaste'], ['wl-paste', '--no-newline'], ['xclip', '-selection', 'clipboard', '-o']):
        if shutil.which(command[0]):
            return subprocess.run(command, capture_output=True, text=True, timeout=5, check=False).stdout
    raise OSError('No clipboard tool found')


def clipboard(vault):
    """What the hotkey runs: capture whatever text or link is on the clipboard."""
    result = add(vault, read_clipboard())
    _log(vault, result)
    return result


def _log(vault, result):
    from .storage import RuntimeConfig, now, write_json
    try:
        write_json(RuntimeConfig(vault).root / 'last-yakala.json', {'at': now(), **result})
    except OSError:
        pass


def shortcut_script(vault, python=None, root=None):
    """PowerShell that creates the Start Menu shortcut with Ctrl+Alt+B."""
    python = Path(python or sys.executable)
    if python.name.lower() == 'python.exe' and python.with_name('pythonw.exe').is_file():
        python = python.with_name('pythonw.exe')
    root = Path(root or Path(__file__).resolve().parents[2])

    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"
    arguments = f'-m brain_eleven --vault "{Path(vault).resolve()}" yakala pano'
    return '\n'.join([
        "$shell = New-Object -ComObject WScript.Shell",
        f"$path = Join-Path ([Environment]::GetFolderPath('Programs')) {quote(SHORTCUT_NAME)}",
        "$link = $shell.CreateShortcut($path)",
        f"$link.TargetPath = {quote(python)}",
        f"$link.Arguments = {quote(arguments)}",
        f"$link.WorkingDirectory = {quote(root)}",
        f"$link.Hotkey = {quote(HOTKEY)}",
        "$link.Description = 'Panodaki bağlantıyı ya da metni Brain-Eleven gelen kutusuna at'",
        "$link.Save()",
        "Write-Output $path",
    ])


def install_shortcut(vault):
    """Windows: Start Menu shortcut with Ctrl+Alt+B. Elsewhere: the command to bind yourself."""
    command = f'{sys.executable} -m brain_eleven --vault "{Path(vault).resolve()}" yakala pano'
    if os.name != 'nt':
        return {'status': 'MANUAL', 'command': command,
                'note': 'Bu komutu masaüstünün kısayol ayarında Ctrl+Alt+B tuşuna bağla.'}
    completed = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', shortcut_script(vault)],
                               capture_output=True, text=True, timeout=30, check=False,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if completed.returncode != 0:
        raise OSError('Shortcut could not be created: ' + completed.stderr.strip()[:200])
    return {'status': 'INSTALLED', 'hotkey': 'Ctrl+Alt+B', 'shortcut': completed.stdout.strip()}
