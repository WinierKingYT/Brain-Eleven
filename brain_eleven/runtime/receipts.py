"""Work outcome receipts: what an agent finished, written by the agent itself.

A receipt is a short, source-linked claim ("PR #75 opened: owner notes in
every session") that the agent records when meaningful work ends. Receipts are
immutable and idempotent: the same project, summary and sources give the same
id, and an existing receipt is never rewritten. They are the agent's claims,
not verified facts, and they are not canonical memory; recap, the project
session note and SessionStart show them. Adapted from avenoxbeyin's receipts
(MIT): one file per receipt so several sessions can write at once.
"""
import re

from .storage import RuntimeConfig, identity, now, read_json, write_json

SUMMARY_LIMIT = 400
NEXT_LIMIT = 200
MAX_SOURCES = 8
_SOURCE = re.compile(r'(?:https?://[^\s]{1,300}|[0-9a-f]{7,40}|#\d{1,7}|(?![A-Za-z]:)(?![/\\~])[^\s:*?"<>|]{1,200})')


def _root(vault, project_id):
    return RuntimeConfig(vault).root / 'receipts' / identity('receipts_', project_id)


def _clean_sources(sources):
    """Relative paths, URLs, commit ids or #PR numbers only; absolute paths are refused."""
    from context_compiler_v2.safety import contains_secret
    cleaned = []
    for source in sources or []:
        value = str(source).strip().replace('\\', '/')
        if not value:
            continue
        if not _SOURCE.fullmatch(value) or '..' in value.split('/'):
            raise ValueError('Sources must be relative paths, URLs, commit ids or #numbers (no absolute paths)')
        if contains_secret(value):
            raise ValueError('A source looks like it contains a secret')
        if value not in cleaned:
            cleaned.append(value)
    if len(cleaned) > MAX_SOURCES:
        raise ValueError(f'At most {MAX_SOURCES} sources')
    return cleaned


def submit(vault, project_root, summary, *, next_step=None, sources=(), client='manual'):
    """Record one receipt for the project at ``project_root``; repeating it is harmless."""
    from .session_cards import _safe
    from .worker import allowed
    project = allowed(vault, project_root)
    if not project:
        raise ValueError('Project folder is not enrolled (project add)')
    text = _safe(summary, SUMMARY_LIMIT)
    if not text or len(' '.join(str(summary).split())) > SUMMARY_LIMIT:
        raise ValueError(f'Summary must be safe, non-empty and at most {SUMMARY_LIMIT} characters')
    following = None
    if next_step:
        following = _safe(next_step, NEXT_LIMIT)
        if not following:
            raise ValueError('Next step was rejected by the safety check')
    cleaned = _clean_sources(sources)
    receipt_id = identity('rcpt_', project['project_id'], text, *cleaned)[:30]
    path = _root(vault, project['project_id']) / (receipt_id + '.json')
    existing = read_json(path, None)
    if existing:
        return {**existing, 'status': 'DUPLICATE'}
    record = {'schema_version': 1, 'receipt_id': receipt_id, 'project_id': project['project_id'],
              'at': now(), 'client': client if client in {'claude', 'codex', 'manual'} else 'manual',
              'summary': text, 'next': following, 'sources': cleaned}
    write_json(path, record)
    _refresh_note(vault, project)
    return {**record, 'status': 'RECORDED'}


def latest(vault, project_id, limit=5):
    root = _root(vault, project_id)
    items = [read_json(path, None) for path in root.glob('rcpt_*.json')] if root.is_dir() else []
    return sorted((x for x in items if isinstance(x, dict) and x.get('at')), key=lambda x: x['at'], reverse=True)[:limit]


def all_receipts(vault):
    root = RuntimeConfig(vault).root / 'receipts'
    for path in sorted(root.glob('receipts_*/rcpt_*.json')) if root.is_dir() else ():
        item = read_json(path, None)
        if isinstance(item, dict) and item.get('project_id') and item.get('at'):
            yield item


def render(receipt):
    from .session_cards import _local
    line = f"- {_local(receipt['at'])} · {receipt['summary']}"
    if receipt.get('next'):
        line += f" → sıradaki: {receipt['next']}"
    if receipt.get('sources'):
        line += ' (' + ', '.join(f'`{s}`' for s in receipt['sources']) + ')'
    return line


def _refresh_note(vault, project):
    """Re-render the project's session note so the new receipt shows at once."""
    from . import session_cards
    path = session_cards._state_path(vault, project['project_id'])
    state = read_json(path, {'schema_version': 1, 'cards': {}})
    state['project_id'] = project['project_id']
    write_json(path, session_cards.render(vault, project, state))
