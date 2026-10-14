"""What happened recently, from session cards and newly written memories.

No model call and no transcript read: cards and canonical memories are
already derived, safety-checked records. Memories are what the system wrote
(after review or probation), not independently verified facts.
"""
from datetime import date, datetime, time, timedelta, timezone

from .session_cards import all_cards, render_card

MAX_DAYS = 366


def _parse(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def window(*, days=None, since=None, until=None, today=None):
    """(start, end) as aware datetimes. A bare date is the machine's local day; ``until`` covers its whole day."""
    if days is not None and (since or until):
        raise ValueError('--days cannot be combined with --since/--until')
    local = datetime.now().astimezone().tzinfo
    today = today or datetime.now(local).date()

    def bound(value, end):
        if value is None:
            return None
        if len(value) == 10:
            day = date.fromisoformat(value)
            return datetime.combine(day + timedelta(days=1) if end else day, time(), local)
        moment = _parse(value)
        if moment is None or 'T' not in value or not (value.endswith('Z') or '+' in value[10:] or '-' in value[10:]):
            raise ValueError('Use YYYY-MM-DD or a timestamp with Z or an offset')
        return moment

    if since or until:
        start = bound(since, False) or datetime.min.replace(tzinfo=timezone.utc)
        end = bound(until, True) or datetime.combine(today + timedelta(days=1), time(), local)
    else:
        days = 7 if days is None else days
        if not 1 <= days <= MAX_DAYS:
            raise ValueError(f'--days must be between 1 and {MAX_DAYS}')
        end = datetime.combine(today + timedelta(days=1), time(), local)
        start = end - timedelta(days=days)
    if start >= end:
        raise ValueError('The start of the range must be before its end')
    return start, end


def recap(vault, *, days=None, since=None, until=None, project=None, limit=50, today=None):
    from brain_eleven.memory import MemoryStore
    from brain_eleven.projects.registry import ProjectRegistry
    if not 1 <= limit <= 200:
        raise ValueError('--limit must be between 1 and 200')
    start, end = window(days=days, since=since, until=until, today=today)
    registry = ProjectRegistry(vault)
    labels = {item['project_id']: item.get('project_label') or item['project_id'] for item in registry.list_projects()}
    if project is not None:
        wanted = {pid for pid, label in labels.items() if project in {pid, label}}
        if not wanted:
            raise ValueError('Unknown project')
    else:
        wanted = None

    def inside(begin, finish):
        first, last = _parse(begin), _parse(finish)
        return first is not None and last is not None and first < end and last >= start

    sessions, memories, outcomes = {}, {}, {}
    from .receipts import all_receipts, render as render_receipt
    for item in all_receipts(vault):
        if (wanted is None or item['project_id'] in wanted) and inside(item['at'], item['at']):
            outcomes.setdefault(item['project_id'], []).append(item)
    for project_id, card in all_cards(vault):
        if (wanted is None or project_id in wanted) and inside(card.get('started_at'), card.get('updated_at')):
            sessions.setdefault(project_id, []).append(card)
    for item in MemoryStore(vault).load()['validated_memory']:
        if str(item.get('status') or 'active') != 'active':
            continue
        project_id = item.get('project_id') or ''
        if (wanted is None or project_id in wanted) and inside(item.get('timestamp'), item.get('timestamp')):
            memories.setdefault(project_id, []).append(item)
    lines = [f"# Son işler: {start.astimezone().strftime('%Y-%m-%d')} – {(end - timedelta(seconds=1)).astimezone().strftime('%Y-%m-%d')}"]
    shown = 0
    for project_id in sorted(set(sessions) | set(memories) | set(outcomes), key=lambda pid: labels.get(pid, pid or 'genel')):
        lines += ['', f"## {labels.get(project_id, project_id or 'Genel')}"]
        done = sorted(outcomes.get(project_id, []), key=lambda x: x['at'], reverse=True)
        if done:
            lines += ['', f'### İş sonuçları ({len(done)})', '']
            for item in done:
                if shown >= limit:
                    break
                lines.append(render_receipt(item))
                shown += 1
        cards = sorted(sessions.get(project_id, []), key=lambda c: c['updated_at'], reverse=True)
        if cards:
            lines += ['', f'### Oturumlar ({len(cards)})', '']
            for card in cards:
                if shown >= limit:
                    break
                lines.append(render_card(card).replace('### ', '#### ', 1))
                lines.append('')
                shown += 1
        items = sorted(memories.get(project_id, []), key=lambda m: m.get('timestamp', ''), reverse=True)
        if items:
            lines += [f'### Yeni hafızalar ({len(items)})', '']
            for item in items:
                if shown >= limit:
                    break
                lines.append(f"- [{item.get('type', 'not')}] {' '.join(str(item.get('content', '')).split())}")
                shown += 1
    if len(lines) == 1:
        lines += ['', 'Bu aralıkta kayıtlı oturum ya da yeni hafıza yok.']
    elif shown >= limit:
        lines += ['', f'(liste {limit} kayıtta kesildi; --limit ile artırılabilir)']
    return {'text': '\n'.join(lines).rstrip() + '\n', 'receipts': sum(map(len, outcomes.values())),
            'sessions': sum(map(len, sessions.values())),
            'memories': sum(map(len, memories.values()))}
