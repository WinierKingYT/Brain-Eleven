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
