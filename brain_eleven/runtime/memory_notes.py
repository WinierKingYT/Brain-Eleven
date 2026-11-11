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
    from brain_eleven.runtime.secret_check import contains_secret
    content = ' '.join(str(item.get('content', '')).split())
    if not content or contains_secret(content):
        return None
    day = str(item.get('timestamp') or '')[:10]
    flags = '' if item.get('is_approved', True) is True else ' · onaysız'
    return f"- {content} <small>`{item.get('memory_id', '?')}` · {day}{flags}</small>"


def agent_readable(item, approved_only):
    """The SessionStart gates (approval, secret, capture safety).

    Only such records go into a topic note: the ``map`` profile points the
    agent at those notes, so they must not carry what bootstrap would withhold.
    """
    from brain_eleven.runtime.capture_safety import evaluate_capture
    from brain_eleven.runtime.secret_check import contains_secret
    content = str(item.get('content', ''))
    return ((not approved_only or item.get('is_approved', True) is True)
            and not contains_secret(content) and evaluate_capture(content).accepted)


def render(vault, document):
    """Write one note per project (and Genel), plus one per topic, from a MemoryStore document; return the project note names."""
    from brain_eleven.projects.registry import ProjectRegistry
    labels = {p['project_id']: p.get('project_label') or p['project_id'] for p in ProjectRegistry(vault).list_projects()}
    approved_only = RuntimeConfig(vault).load().get('b1_human_approval', False)
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
        by_type, by_topic = {}, {}
        for item in items:
            line = _line(item)
            if not line:
                continue
            if item.get('topic') and agent_readable(item, approved_only):
                by_topic.setdefault(_name(item['topic']), []).append(line)
            else:
                by_type.setdefault(str(item.get('type') or 'observation'), []).append(line)
        total = sum(map(len, by_type.values())) + sum(map(len, by_topic.values()))
        lines = [f'# {title} — hafıza', '', _HEADER, '', f'{total} aktif kayıt.']
        folder = root / _name(title)
        if by_topic:
            # The project note is the map: a topic's records live only in its own short note.
            lines += ['', '## Konular', '', *(f'- [[{_name(title)}/{topic}|{topic}]] — {len(found)} kayıt'
                                              for topic, found in sorted(by_topic.items()))]
        for topic, found in by_topic.items():
            _write(folder / (topic + '.md'), [f'# {topic}', '', _HEADER, '',
                                              f'[[{_name(title)}]] · {len(found)} aktif kayıt.', '', *found])
        # No note is deleted: a topic that lost its last record keeps its file and says so.
        for stale in (folder.glob('*.md') if folder.is_dir() else ()):
            if stale.stem not in by_topic and _HEADER in stale.read_text(encoding='utf-8'):
                _write(stale, [f'# {stale.stem}', '', _HEADER, '', f'[[{_name(title)}]] · Bu konuda aktif kayıt kalmadı.'])
        order = list(_TYPE_TITLES) + sorted(set(by_type) - set(_TYPE_TITLES))
        for kind in order:
            if by_type.get(kind):
                lines += ['', f'## {_TYPE_TITLES.get(kind, kind.capitalize())}', '', *by_type[kind]]
        path = root / (_name(title) + '.md')
        _write(path, lines)
        written.append(path.stem)
    return written


def _write(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    temporary.replace(path)


def refresh(vault, *, force=False):
    """Re-render the notes when the memory revision or the approval gate changed since the last render."""
    from brain_eleven.memory import MemoryStore
    config = RuntimeConfig(vault)
    marker = config.root / 'memory-notes.json'
    document = MemoryStore(vault).load()
    # The approval gate decides what a topic note may hold, so turning it on must not leave old notes behind.
    state = {'revision': document.get('revision'), 'approved_only': bool(config.load().get('b1_human_approval', False))}
    previous = read_json(marker, {}) or {}
    if not force and all(previous.get(key) == value for key, value in state.items()):
        return {'status': 'CURRENT', 'revision': state['revision']}
    notes = render(vault, document)
    write_json(marker, {**state, 'at': now(), 'notes': len(notes)})
    return {'status': 'RENDERED', 'revision': state['revision'], 'notes': notes}


TOPIC_MAX = 40


def set_topic(vault, memory_ids, topic):
    """Name the topic of active memories (owner decision 2026-11-11); '' clears it.

    The topic only groups records into notes: content, status and approval
    are untouched, and the write goes through MemoryStore like every other.
    """
    from brain_eleven.memory import MemoryStore
    from brain_eleven.memory.store import no_change
    from brain_eleven.runtime.secret_check import contains_secret
    topic = ' '.join(str(topic or '').split())
    if (topic and topic != _name(topic)) or len(topic) > TOPIC_MAX or contains_secret(topic):
        raise ValueError(f'Topic must be at most {TOPIC_MAX} characters that are safe in a file name')
    wanted = set(memory_ids)

    def mutate(document):
        changed = [m for m in document['validated_memory'] if m.get('memory_id') in wanted
                   and str(m.get('status') or 'active') == 'active' and m.get('topic', '') != topic]
        for memory in changed:
            memory['topic'] = topic
        found = {m.get('memory_id') for m in document['validated_memory']
                 if m.get('memory_id') in wanted and str(m.get('status') or 'active') == 'active'}
        result = {'topic': topic, 'updated': sorted(m['memory_id'] for m in changed),
                  'not_found': sorted(wanted - found)}
        return result if changed else no_change(result)

    return MemoryStore(vault).transact(mutate)[0]


def topics(vault, project_id):
    """Topic names with counts, and the active records of the project that have none yet."""
    from brain_eleven.memory import MemoryStore
    from brain_eleven.runtime.secret_check import contains_secret
    counts, untopiced = {}, []
    for memory in MemoryStore(vault).load()['validated_memory']:
        if str(memory.get('status') or 'active') != 'active' or (memory.get('project_id') or '') != (project_id or ''):
            continue
        if memory.get('topic'):
            counts[memory['topic']] = counts.get(memory['topic'], 0) + 1
        elif not contains_secret(str(memory.get('content', ''))):
            untopiced.append({'id': memory.get('memory_id'), 'type': memory.get('type'),
                              'text': ' '.join(str(memory.get('content', '')).split())[:160]})
    return {'topics': dict(sorted(counts.items())), 'untopiced': untopiced}
