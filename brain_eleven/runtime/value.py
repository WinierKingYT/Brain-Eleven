"""Value score for review candidates (layer 2 of review triage).

After the layer-1 noise filter, candidates still outnumber what a person
reviews in a day. The review screen shows the most valuable ones first and,
by default, only the top ``DAILY_LIMIT``. The score is transparent and uses
only signals already on the candidate:

- commitment: a committed statement outranks an observation
- type: decision > lesson > open loop > observation
- novelty: a near-duplicate of an existing memory ranks low
- length: a sentence-sized statement beats a fragment or a wall of text
- recall: a candidate that carries a recall-test answer ranks first

The score never accepts, rejects or hides anything for good: the rest stay
pending (and expire on their own) and "show all" lists them.
"""

from __future__ import annotations

DAILY_LIMIT = 10
NOTICE_MAX_AGE_SECONDS = 24 * 3600

_COMMITMENT = {'COMMITTED': 1.0, 'OBSERVED': 0.55, 'UNCERTAIN': 0.3, 'PROPOSED': 0.3,
               'HYPOTHETICAL': 0.15, 'QUESTION': 0.1, 'NEGATED': 0.2, 'QUOTED': 0.05}
_TYPE = {'decision': 1.0, 'lesson': 0.8, 'open_loop': 0.7, 'observation': 0.5, 'preference': 0.7}


def _length(text):
    n = len(text or '')
    if n < 40:
        return 0.4
    if n <= 280:
        return 1.0
    return 0.6


def value_score(item):
    """0..1 score (recall-test answers get +1 so they sort first)."""
    candidate = item.get('candidate') if isinstance(item.get('candidate'), dict) else {}
    text = candidate.get('text') if candidate.get('candidate_type') == 'STATE_MUTATION' else candidate.get('content')
    top = max((s.get('similarity', 0) for s in item.get('similar') or []), default=0)
    novelty = 0.1 if top >= 0.6 else 1.0 - top
    score = (0.40 * _COMMITMENT.get(candidate.get('commitment'), 0.3)
             + 0.25 * _TYPE.get(candidate.get('memory_type'), 0.5)
             + 0.20 * novelty
             + 0.15 * _length(text))
    if item.get('recall_questions'):
        score += 1.0
    return round(score, 4)


def _audit_suggestions(vault, project_id=None):
    from brain_eleven.memory import MemoryStore
    from .storage import RuntimeConfig, read_json
    report = read_json(RuntimeConfig(vault).root / 'memory-audit.json', {}) or {}
    active = {m.get('memory_id'): m for m in MemoryStore(vault).load()['validated_memory']
              if str(m.get('status') or 'active') == 'active'}
    return [{**s, 'project_id': active[s['memory_id']].get('project_id')}
            for s in report.get('suggestions') or []
            if isinstance(s, dict) and s.get('memory_id') in active
            and (project_id is None or active[s['memory_id']].get('project_id') == project_id)]


def _model_accept(entry):
    """The model suggested acceptance: left for a person (MODEL_ACCEPT) or allowed (ACCEPT)."""
    entry = entry or {}
    return entry.get('reason') in ('MODEL_ACCEPT', 'MODEL_VERIFIED') or entry.get('suggestion') == 'ACCEPT'


def _safe_text(text, limit=160):
    """Memory text for display, withheld when it fails the capture safety check."""
    from context_compiler_v2.safety import contains_secret
    from .capture_safety import evaluate_capture
    text = str(text or '')
    return text[:limit] if not contains_secret(text) and evaluate_capture(text).accepted else '[withheld]'


def refresh_owner_counts(vault):
    """Count what waits for the owner, per project, into runtime/owner-notice.json.

    This scans the whole review store (~1.5 s on 4,500 files), so it runs
    off the prompt path: after queue triage, after the memory audit and on
    ``digest``. SessionStart only reads the small result file.
    """
    from .review import ReviewStore
    from .storage import RuntimeConfig, now, write_json
    suggestions = load_suggestions(vault)
    projects = {}
    for item in ReviewStore(vault).list():
        if item.get('status') != 'PENDING':
            continue
        entry = suggestions.get(item.get('id')) or {}
        verdict = entry.get('suggestion')
        if verdict in ('REJECT', 'DUPLICATE'):
            continue
        counts = projects.setdefault(str((item.get('candidate') or {}).get('project_id') or ''),
                                     {'waiting': 0, 'model_accept': 0, 'not_evaluated': 0, 'audit': 0})
        counts['waiting'] += 1
        counts['model_accept'] += _model_accept(entry)
        counts['not_evaluated'] += not verdict
    for suggestion in _audit_suggestions(vault):
        project = str(suggestion.get('project_id') or '')
        projects.setdefault(project, {'waiting': 0, 'model_accept': 0, 'not_evaluated': 0, 'audit': 0})
        projects[project]['audit'] += 1
    document = {'at': now(), 'projects': projects}
    write_json(RuntimeConfig(vault).root / 'owner-notice.json', document)
    return document


def owner_notice(vault, project_id=None):
    """One line for SessionStart from the precomputed counts, else ''."""
    from .storage import RuntimeConfig, read_json
    from datetime import datetime, timezone
    document = read_json(RuntimeConfig(vault).root / 'owner-notice.json', {}) or {}
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(str(document.get('at')))
    except (TypeError, ValueError):
        return ''
    if age.total_seconds() > NOTICE_MAX_AGE_SECONDS:
        return ''  # stale counts would mislead; queue triage refreshes them every 30 min
    projects = document.get('projects') if isinstance(document.get('projects'), dict) else {}
    rows = [projects.get(project_id) or {}] if project_id else list(projects.values())
    total = {key: sum(int(row.get(key) or 0) for row in rows if isinstance(row, dict))
             for key in ('waiting', 'model_accept', 'not_evaluated', 'audit')}
    if not total['waiting'] and not total['audit']:
        return ''
    parts = []
    if total['waiting']:
        parts.append(f"{total['waiting']} review candidates wait for the owner "
                     f"({total['model_accept']} suggested for acceptance by the model, "
                     f"{total['not_evaluated']} not evaluated yet)")
    if total['audit']:
        parts.append(f"memory audit has {total['audit']} suggestion(s)")
    return '- ' + '; '.join(parts) + '. Details: `python -m brain_eleven digest`.'


def digest(vault, *, limit=DAILY_LIMIT):
    """The day's most valuable pending candidates, for a quick look without the browser.

    Items the queue triage hid (REJECT/DUPLICATE) are skipped; the local
    model's accept suggestions come first, and memory-audit suggestions are
    listed separately.
    """
    from brain_eleven.memory import MemoryStore
    from .review import ReviewStore, rank_similar
    from .triage import summary
    memories = [m for m in MemoryStore(vault).load()['validated_memory'] if str(m.get('status') or 'active') == 'active']
    suggestions = load_suggestions(vault)
    pending = [x for x in ReviewStore(vault).list() if x.get('status') == 'PENDING'
               and (suggestions.get(x.get('id')) or {}).get('suggestion') not in ('REJECT', 'DUPLICATE')]
    for item in pending:
        candidate = item.get('candidate') or {}
        same_project = [m for m in memories if m.get('project_id') == candidate.get('project_id')]
        item['similar'] = [{'similarity': score} for score, _ in rank_similar(candidate.get('content', ''), same_project)[:1]]
    def order(item):
        model_accept = _model_accept(suggestions.get(item.get('id')))
        return (model_accept, value_score(item))
    ranked = sorted(pending, key=order, reverse=True)[:limit]
    refresh_owner_counts(vault)
    return {'pending': len(pending), 'auto_filtered_total': summary(vault).get('total', 0),
            'top': [{'id': x['id'], 'score': value_score(x),
                     'commitment': (x.get('candidate') or {}).get('commitment'),
                     'type': (x.get('candidate') or {}).get('memory_type'),
                     'model_accept': _model_accept(suggestions.get(x['id'])),
                     'text': ((x.get('candidate') or {}).get('content') or (x.get('candidate') or {}).get('text') or '')[:160]}
                    for x in ranked],
            'memory_audit': [{**s, 'text': _safe_text(next((m.get('content') for m in memories
                                                            if m.get('memory_id') == s['memory_id']), ''))}
                             for s in _audit_suggestions(vault)],
            'check': owner_check(vault, memories)}


SAMPLE_SIZE = 5
SAMPLE_DAYS = 7


def owner_check(vault, memories, *, now=None):
    """Memories for the owner to glance at: the model's probation flags, then a weekly sample.

    The sample is drawn from memories written without a person in the last
    SAMPLE_DAYS and is stable within an ISO week, so repeated digests show the
    same items. A wrong one is retired with ``python -m brain_eleven retire <id>``.
    """
    import random
    from datetime import datetime, timezone
    from .memory_audit import _age_days
    from .probation import flagged_ids, human_accepted_ids
    now = now or datetime.now(timezone.utc)
    active = {m.get('memory_id'): m for m in memories if m.get('memory_id')}
    shown = [{'memory_id': i, 'why': 'FLAGGED', 'text': _safe_text(active[i].get('content'))}
             for i in flagged_ids(vault) if i in active]
    seen = {x['memory_id'] for x in shown}
    try:
        human = human_accepted_ids(vault)
    except Exception:
        human = set()
    recent = sorted(i for i, m in active.items()
                    if i not in seen and i not in human and m.get('source') == 'worker'
                    and (_age_days(m, now) or SAMPLE_DAYS) < SAMPLE_DAYS)
    year, week, _ = now.isocalendar()
    for memory_id in random.Random(f'{year}-{week}').sample(recent, min(SAMPLE_SIZE, len(recent))):
        shown.append({'memory_id': memory_id, 'why': 'SAMPLE', 'text': _safe_text(active[memory_id].get('content'))})
    return shown


_SUGGESTIONS = {'ACCEPT', 'REJECT', 'REVIEW'}
_REASON = __import__('re').compile(r'[A-Z_]{1,40}')
_REVIEW_ID = __import__('re').compile(r'rev_[a-f0-9]{64}')
_MEMORY_ID = __import__('re').compile(r'mem_[A-Za-z0-9_-]{1,80}')


def _active_memory_ids(vault):
    from brain_eleven.memory import MemoryStore
    try:
        memories = MemoryStore(vault).load().get('validated_memory', [])
    except Exception:
        return set()
    return {m.get('memory_id') for m in memories
            if isinstance(m, dict) and str(m.get('status') or 'active').lower() not in ('superseded', 'retired')}


def load_suggestions(vault):
    """Advisory model suggestions from runtime/review-suggestions.json (local, never committed).

    Only a known verdict, a short reason code and, for DUPLICATE_OF, a review id
    or a canonical memory id (``mem_...``) are kept; anything else in the file is ignored. Suggestions never act on
    their own: the person still accepts or rejects.
    """
    from .storage import RuntimeConfig, read_json
    try:
        document = read_json(RuntimeConfig(vault).root / 'review-suggestions.json', {}) or {}
    except (OSError, ValueError):
        return {}
    raw = document.get('suggestions') if isinstance(document, dict) else None
    clean, active = {}, None
    for review_id, entry in (raw or {}).items() if isinstance(raw, dict) else ():
        if not isinstance(review_id, str) or not _REVIEW_ID.fullmatch(review_id) or not isinstance(entry, dict):
            continue
        verdict = str(entry.get('suggestion') or '')
        duplicate_of = None
        if verdict.startswith('DUPLICATE_OF:'):
            duplicate_of = verdict.split(':', 1)[1]
            if not (_REVIEW_ID.fullmatch(duplicate_of) or _MEMORY_ID.fullmatch(duplicate_of)):
                continue
            verdict = 'DUPLICATE'
            if duplicate_of.startswith('mem_'):
                # Hide only behind a memory that is still active; otherwise the
                # candidate may be the only copy left, so a person looks at it.
                if active is None:
                    active = _active_memory_ids(vault)
                if duplicate_of not in active:
                    verdict, duplicate_of = 'REVIEW', None
        elif verdict not in _SUGGESTIONS:
            continue
        reason = str(entry.get('reason') or '')
        clean[review_id] = {'suggestion': verdict, 'reason': reason if _REASON.fullmatch(reason) else '',
                            'duplicate_of': duplicate_of,
                            'by': str(entry.get('by') or document.get('by') or 'model')[:40]}
    return clean


def apply_suggestions(vault, *, apply=False):
    """Owner decision 2026-09-27: the model's ACCEPT verdicts are applied without a click.

    Each ACCEPT goes through the normal ``review_action`` path (safety, CAS,
    audit) with a note naming the model and its reason; a wrong record can be
    retired later. REJECT/DUPLICATE verdicts are not written as rejections
    (that would delete the text for good): the review screen hides them and
    they expire on their own within 7 days, so a wrong verdict stays reversible.
    Dry run by default.
    """
    from brain_eleven.memory import MemoryStore
    from brain_eleven.state import StateStore
    from .review import ReviewStore
    from .service import review_action
    from .storage import read_json

    suggestions = load_suggestions(vault)
    store = ReviewStore(vault)
    summary = {'dry_run': not apply, 'accepted': 0, 'hidden': 0, 'left_for_person': 0, 'skipped': 0, 'failed': 0}
    for review_id, entry in suggestions.items():
        item = read_json(store.path(review_id)) or {}
        if item.get('status') != 'PENDING':
            summary['skipped'] += 1
            continue
        verdict = entry['suggestion']
        if verdict in ('REJECT', 'DUPLICATE'):
            summary['hidden'] += 1
            continue
        if verdict != 'ACCEPT':
            summary['left_for_person'] += 1
            continue
        if not apply:
            summary['accepted'] += 1
            continue
        candidate = item.get('candidate') or {}
        try:
            if candidate.get('candidate_type') == 'STATE_MUTATION':
                revision = StateStore(vault).project_revision(candidate.get('project_id'))
            else:
                revision = MemoryStore(vault).load()['revision']
            note = f"Model onayı ({entry['by']}): {entry['reason'] or 'ACCEPT'}"[:280]
            result = review_action(vault, review_id, 'accept', {'expected_revision': revision, 'note': note})
            summary['accepted' if isinstance(result, dict) and result.get('status') == 'ACCEPTED' else 'failed'] += 1
        except ValueError:
            summary['failed'] += 1
    return summary
