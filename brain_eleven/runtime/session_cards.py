"""Per-project session cards and open threads, kept as a readable Markdown note.

Each captured session keeps one short card (first and last request, last
answer, next step from a compact summary). Cards live per project in
``🔮 Companion/Oturumlar/<project>.md`` with the project's open state items
on top. The card section is size-capped: the oldest cards move verbatim to a
monthly file under ``🔮 Companion/Arşiv/``; nothing is deleted or summarised,
and no model is called. SessionStart shows the latest cards so a new session
knows where the last ones stopped.
"""
from datetime import datetime, timezone
import os
from pathlib import Path
import re

from .storage import RuntimeConfig, identity, now, read_json, write_json

CARDS_DIR = Path('🔮 Companion') / 'Oturumlar'
ARCHIVE_DIR = Path('🔮 Companion') / 'Arşiv'
CARD_SECTION_LIMIT = 3000
CONTEXT_CARDS = 2
CONTEXT_LIMIT = 1500
HEADING = '## Son oturumlar'
CONTEXT_HEADING = '## Son oturumlar (bu projede nerede kalındı)'
_FIELD_LIMITS = {'first': 120, 'last': 200, 'answer': 300, 'next': 200}
_NEXT_SECTION = re.compile(r'^\s*(?:#{1,6}\s*)?(?:\*\*)?\s*\d+\.\s*(?:\*\*)?\s*'
                           r'(optional next step|next step|pending tasks|sıradaki adım|bekleyen işler)\b',
                           re.IGNORECASE | re.MULTILINE)
_BULLET = re.compile(r'^\s*[-*•]\s+(.+)$', re.MULTILINE)
_OPEN = {'blockers': ('Engel', {'ACTIVE', 'OPEN'}),
         'requirements': ('Gereksinim', {'ACTIVE', 'OPEN'}),
         'work_items': ('İş', {'TODO', 'ACTIVE', 'BLOCKED', 'IN_PROGRESS', 'PLANNED'})}


def _safe(text, limit):
    """One bounded line, or None when the text must not be written to a note."""
    from context_compiler_v2.safety import contains_secret
    from .capture_safety import evaluate_capture
    if not isinstance(text, str):
        return None
    line = ' '.join(text.split())
    if not line or contains_secret(line):
        return None
    line = line[:limit] + ('…' if len(line) > limit else '')
    return line if evaluate_capture(line).accepted else None


def _next_step(summary):
    match = _NEXT_SECTION.search(summary or '')
    if not match:
        return None
    bullet = _BULLET.search(summary, match.end())
    return bullet.group(1) if bullet else None


def _stamp(message):
    occurred = getattr(message.record, 'occurred_at', None)
    value = getattr(occurred, 'value', None) if occurred is not None else None
    return value if isinstance(value, str) else None


def _state_path(vault, project_id):
    return RuntimeConfig(vault).root / 'session-cards' / (identity('cards_', project_id) + '.json')


def _local(timestamp):
    try:
        moment = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    except (AttributeError, ValueError):
        return '?'
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone().strftime('%Y-%m-%d %H:%M')


def render_card(card):
    title = card.get('first') or 'Oturum'
    lines = [f"### {_local(card['started_at'])} · {card['client']} · {title[:60]}"]
    for key, label in (('first', 'İlk istek'), ('last', 'Son istek'), ('answer', 'Son yanıt'), ('next', 'Sıradaki')):
        if key == 'first' and len(card.get('first') or '') <= 60:
            continue  # already the title
        if card.get(key) and not (key == 'last' and card.get('last') == card.get('first')):
            lines.append(f'- {label}: {card[key]}')
    lines.append(f"- {card.get('prompts', 0)} istem · son güncelleme {_local(card['updated_at'])}")
    return '\n'.join(lines)


def _threads(vault, project_id):
    from brain_eleven.state import StateStore
    try:
        project = StateStore(vault).get_project(project_id) or {}
    except Exception:  # A damaged state store must not stop the note.
        return []
    lines = []
    current = project.get('current') or {}
    for key, label in (('objective', 'Hedef'), ('milestone', 'Kilometre taşı')):
        value = current.get(key)
        text = _safe(value.get('text') if isinstance(value, dict) else value, 200)
        if text:
            lines.append(f'- {label}: {text}')
    for bucket, (label, statuses) in _OPEN.items():
        for item in project.get(bucket, []):
            if isinstance(item, dict) and item.get('status') in statuses:
                text = _safe(item.get('text'), 200)
                if text:
                    lines.append(f'- {label}: {text}')
    return lines


def _note_path(vault, project):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '-', str(project.get('project_label') or project['project_id'])).strip(' .')
    return Path(vault) / CARDS_DIR / ((name or project['project_id']) + '.md')


def _write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    os.replace(temporary, path)


def _archive(vault, project, cards):
    """Append cards verbatim to the project's monthly archive file."""
    month = _local(cards[0]['started_at'])[:7] if cards[0].get('started_at') else now()[:7]
    path = Path(vault) / ARCHIVE_DIR / f"{_note_path(vault, project).stem} - {month}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding='utf-8') if path.exists() else '<!-- Brain-Eleven oturum arşivi; silinmez. -->\n'
    _write_text(path, existing.rstrip('\n') + '\n\n' + '\n\n'.join(render_card(c) for c in cards) + '\n')


def render(vault, project, state):
    """Write the project note; move cards past the size cap to the archive."""
    cards = sorted(state['cards'].values(), key=lambda c: c['updated_at'], reverse=True)
    kept, size = [], 0
    for card in cards:
        size += len(render_card(card)) + 2
        if kept and size > CARD_SECTION_LIMIT:
            break
        kept.append(card)
    moved = cards[len(kept):]
    if moved:
        _archive(vault, project, list(reversed(moved)))
        state['cards'] = {key: card for key, card in state['cards'].items() if card in kept}
    threads = _threads(vault, project['project_id'])
    label = project.get('project_label') or project['project_id']
    text = '\n'.join([
        f'# {label}',
        '',
        '<!-- Brain-Eleven her oturumdan sonra bu notu yeniden yazar; eski kartlar Arşiv/ altına taşınır. -->',
        '',
        '## Açık konular',
        '',
        *(threads or ['- (kayıtlı açık konu yok)']),
        '',
        RECEIPTS_HEADING,
        '',
        *(_receipt_lines(vault, project['project_id'], NOTE_RECEIPTS) or ['- (henüz iş sonucu yok)']),
        '',
        HEADING,
        '',
        '\n\n'.join(render_card(c) for c in kept) if kept else '(henüz kart yok)',
        '',
    ])
    _write_text(_note_path(vault, project), text)
    return state


def update(vault, project, session, messages):
    """Fold one capture increment into the session's card and rewrite the note."""
    from .context import is_automated_prompt
    path = _state_path(vault, project['project_id'])
    state = read_json(path, {'schema_version': 1, 'cards': {}})
    state['project_id'] = project['project_id']
    key = identity('card_', session)
    card = state['cards'].get(key) or {'client': session.split(':')[0], 'prompts': 0, 'started_at': None, 'updated_at': None}
    changed = False
    for message in messages:
        role, content = message.record.role, message.content
        stamp = _stamp(message)
        if role == 'user' and not is_automated_prompt(content):
            text = _safe(content, _FIELD_LIMITS['last'])
            card['prompts'] += 1
            if text:
                card['first'] = card.get('first') or _safe(content, _FIELD_LIMITS['first'])
                card['last'] = text
        elif role == 'assistant':
            text = _safe(content, _FIELD_LIMITS['answer'])
            if text:
                card['answer'] = text
        elif role == 'summary':
            text = _safe(_next_step(content), _FIELD_LIMITS['next'])
            if text:
                card['next'] = text
        else:
            continue
        changed = True
        if stamp:
            card['started_at'] = min(filter(None, [card['started_at'], stamp]))
            card['updated_at'] = max(filter(None, [card['updated_at'], stamp]))
    if not changed:
        return None
    card['started_at'] = card['started_at'] or now()
    card['updated_at'] = card['updated_at'] or now()
    state['cards'][key] = card
    state = render(vault, project, state)
    write_json(path, state)
    return card


def all_cards(vault):
    """Every kept card of every project as (project_id, card); archived cards are not included."""
    root = RuntimeConfig(vault).root / 'session-cards'
    for path in sorted(root.glob('cards_*.json')) if root.is_dir() else ():
        state = read_json(path, {})
        project_id = state.get('project_id')
        if isinstance(project_id, str) and isinstance(state.get('cards'), dict):
            for card in state['cards'].values():
                yield project_id, card


RECEIPTS_HEADING = '## Son iş sonuçları'
NOTE_RECEIPTS, CONTEXT_RECEIPTS = 5, 3


def _receipt_lines(vault, project_id, limit):
    try:
        from .receipts import latest, render as render_receipt
        return [render_receipt(item) for item in latest(vault, project_id, limit)]
    except Exception:  # Receipts are advisory; a bad file never breaks the note.
        return []


def context(vault, project_id, *, exclude_session=None, limit=CONTEXT_LIMIT):
    """Latest work outcomes and cards of this project for a starting session, newest first."""
    state = read_json(_state_path(vault, project_id), {'cards': {}})
    skip = identity('card_', exclude_session) if exclude_session else None
    cards = sorted((c for k, c in state.get('cards', {}).items() if k != skip),
                   key=lambda c: c['updated_at'], reverse=True)[:CONTEXT_CARDS]
    receipts = _receipt_lines(vault, project_id, CONTEXT_RECEIPTS)
    if not cards and not receipts:
        return ''
    parts = [CONTEXT_HEADING]
    if receipts:
        parts.append('İş sonuçları (ajanın kaydı):\n' + '\n'.join(receipts))
    parts += [render_card(c) for c in cards]
    return '\n\n'.join(parts)[:limit]
