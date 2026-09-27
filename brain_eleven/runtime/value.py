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


def digest(vault, *, limit=DAILY_LIMIT):
    """The day's most valuable pending candidates, for a quick look without the browser."""
    from brain_eleven.memory import MemoryStore
    from .review import ReviewStore, rank_similar
    from .triage import summary
    memories = [m for m in MemoryStore(vault).load()['validated_memory'] if str(m.get('status') or 'active') == 'active']
    pending = [x for x in ReviewStore(vault).list() if x.get('status') == 'PENDING']
    for item in pending:
        candidate = item.get('candidate') or {}
        same_project = [m for m in memories if m.get('project_id') == candidate.get('project_id')]
        item['similar'] = [{'similarity': score} for score, _ in rank_similar(candidate.get('content', ''), same_project)[:1]]
    ranked = sorted(pending, key=value_score, reverse=True)[:limit]
    return {'pending': len(pending), 'auto_filtered_total': summary(vault).get('total', 0),
            'top': [{'id': x['id'], 'score': value_score(x),
                     'commitment': (x.get('candidate') or {}).get('commitment'),
                     'type': (x.get('candidate') or {}).get('memory_type'),
                     'text': ((x.get('candidate') or {}).get('content') or (x.get('candidate') or {}).get('text') or '')[:160]}
                    for x in ranked]}


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
                            'duplicate_of': duplicate_of, 'by': str(document.get('by') or 'model')[:40]}
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
