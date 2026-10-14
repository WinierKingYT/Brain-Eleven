"""A readable Markdown view of canonical memory, one note per project.

``🔮 Companion/Hafıza/<proje>.md`` lists the active memories by type; global
memories go to ``Genel.md``. The notes are derived: MemoryStore stays the only
place memory is written, and an edit made in a note is overwritten on the next
refresh. The service refreshes them when the memory revision changes.
"""
from pathlib import Path
import re

from .storage import RuntimeConfig, read_json, write_json, now

NOTES_DIR = Path('🔮 Companion') / 'Hafıza'
GLOBAL_NOTE = 'Genel'
_TYPE_TITLES = {'decision': 'Kararlar', 'lesson': 'Dersler', 'preference': 'Tercihler', 'fact': 'Gerçekler',
                'constraint': 'Kısıtlar', 'observation': 'Gözlemler'}
_HEADER = ('<!-- Brain-Eleven bu notu hafızadan üretir; buradaki değişiklik hafızaya yazılmaz ve bir sonraki '
           'yenilemede silinir. Bir kaydı iptal etmek için: python -m brain_eleven retire <id> -->')


def _name(text):
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', '-', str(text)).strip(' .') or 'proje'


def _line(item):
    from context_compiler_v2.safety import contains_secret
    content = ' '.join(str(item.get('content', '')).split())
    if not content or contains_secret(content):
        return None
    day = str(item.get('timestamp') or '')[:10]
    flags = '' if item.get('is_approved', True) is True else ' · onaysız'
    return f"- {content} <small>`{item.get('memory_id', '?')}` · {day}{flags}</small>"


def render(vault, document):
    """Write one note per project (and Genel) from a MemoryStore document; return the note names."""
    from brain_eleven.projects.registry import ProjectRegistry
    labels = {p['project_id']: p.get('project_label') or p['project_id'] for p in ProjectRegistry(vault).list_projects()}
    groups = {}
    for item in document.get('validated_memory', []):
        if not isinstance(item, dict) or str(item.get('status') or 'active') != 'active':
            continue
        project_id = item.get('project_id') if item.get('scope') == 'project' else ''
        groups.setdefault(project_id or '', []).append(item)
    root = Path(vault) / NOTES_DIR
    root.mkdir(parents=True, exist_ok=True)
    written = []
    for project_id in sorted(set(groups) | set(labels)):
        title = labels.get(project_id, project_id) if project_id else GLOBAL_NOTE
        items = sorted(groups.get(project_id, []), key=lambda m: str(m.get('timestamp') or ''), reverse=True)
        by_type = {}
        for item in items:
            line = _line(item)
            if line:
                by_type.setdefault(str(item.get('type') or 'observation'), []).append(line)
        lines = [f'# {title} — hafıza', '', _HEADER, '', f'{sum(map(len, by_type.values()))} aktif kayıt.']
        order = list(_TYPE_TITLES) + sorted(set(by_type) - set(_TYPE_TITLES))
        for kind in order:
            if by_type.get(kind):
                lines += ['', f'## {_TYPE_TITLES.get(kind, kind.capitalize())}', '', *by_type[kind]]
        path = root / (_name(title) + '.md')
        temporary = path.with_name(path.name + '.tmp')
        temporary.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        temporary.replace(path)
        written.append(path.stem)
    return written


def refresh(vault, *, force=False):
    """Re-render the notes when the canonical memory revision changed since the last render."""
    from brain_eleven.memory import MemoryStore
    marker = RuntimeConfig(vault).root / 'memory-notes.json'
    document = MemoryStore(vault).load()
    revision = document.get('revision')
    if not force and read_json(marker, {}).get('revision') == revision:
        return {'status': 'CURRENT', 'revision': revision}
    notes = render(vault, document)
    write_json(marker, {'revision': revision, 'at': now(), 'notes': len(notes)})
    return {'status': 'RENDERED', 'revision': revision, 'notes': notes}
