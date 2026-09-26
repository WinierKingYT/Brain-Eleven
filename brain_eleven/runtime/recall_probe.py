"""Automated version of the owner's five-question recall test (TEST-LOG.md).

For each question it answers one thing without asking a model: is the
information the key answer needs in the context SessionStart would deliver
to a fresh session right now, and if not, is it in canonical memory at all?

- IN_CONTEXT: every term group of the key answer is in the bootstrap context.
- IN_MEMORY_NOT_DELIVERED: an active memory holds it, the bootstrap did not
  select it (a selection problem; the memory ids are listed).
- IN_REVIEW_QUEUE: no active memory holds it, but a pending review candidate
  does; accepting that candidate is the fix (review ids are listed).
- NOT_IN_MEMORY: neither memory nor the pending queue holds it: the session
  was not captured, or its candidate expired / was rejected (their text is
  deleted by design), so the fact has to be recorded again.

It is a proxy, not the full test: a present fact can still be answered
badly. The questions are the owner's existing five, read from
evals/recall_probe/questions.json; nothing here is a new evaluation set.
"""

from __future__ import annotations

import json
from pathlib import Path

_QUESTIONS = Path(__file__).resolve().parents[2] / 'evals' / 'recall_probe' / 'questions.json'
_TR_UPPER = str.maketrans({'I': 'ı', 'İ': 'i'})


def _fold(text):
    return (text or '').translate(_TR_UPPER).lower()


def covers(text, groups):
    folded = _fold(text)
    return all(any(_fold(term) in folded for term in group) for group in groups)


def load_questions(path=None):
    return json.loads(Path(path or _QUESTIONS).read_text(encoding='utf-8'))['questions']


def pending_candidate_texts(vault, project_id=None):
    """(review id, candidate text) for pending review candidates of the project."""
    from .review import ReviewStore
    found = []
    for item in ReviewStore(vault)._items():
        if not isinstance(item, dict) or item.get('status') != 'PENDING':
            continue
        if project_id and item.get('project_id') not in (project_id, '', None):
            continue
        candidate = item.get('candidate') if isinstance(item.get('candidate'), dict) else {}
        text = candidate.get('text') if candidate.get('candidate_type') == 'STATE_MUTATION' else candidate.get('content')
        if isinstance(text, str) and text:
            found.append((item.get('id'), text))
    return found


def recall_questions_for(text, questions=None):
    """Ids of recall questions whose key answer this text carries."""
    questions = load_questions() if questions is None else questions
    return [q['id'] for q in questions if covers(text, q['groups'])]


def probe(vault, project_root=None, *, questions_path=None):
    from brain_eleven.memory import MemoryStore
    from .context import compile_bootstrap, explain_bootstrap

    project_root = project_root or vault
    bootstrap = compile_bootstrap(vault, project_root)
    context = bootstrap.get('context', '') or ''
    project_id = bootstrap.get('project_id')
    memories = [m for m in MemoryStore(vault).load()['validated_memory']
                if str(m.get('status') or 'active') == 'active'
                and (not project_id or m.get('project_id') in (project_id, '', None))]
    try:
        why = explain_bootstrap(vault, project_root).get('memories', {})
    except Exception:
        why = {}
    pending = pending_candidate_texts(vault, project_id)
    results = []
    for question in load_questions(questions_path):
        groups = question['groups']
        if covers(context, groups):
            status, holders = 'IN_CONTEXT', []
        else:
            holders = [m.get('memory_id') for m in memories if covers(m.get('content', ''), groups)]
            if not holders:
                # A key answer may be split across memories: every group held by some memory.
                if all(any(covers(m.get('content', ''), [g]) for m in memories) for g in groups):
                    holders = sorted({m.get('memory_id') for g in groups for m in memories
                                      if covers(m.get('content', ''), [g])})
            status = 'IN_MEMORY_NOT_DELIVERED' if holders else 'NOT_IN_MEMORY'
        review_ids = []
        if status == 'NOT_IN_MEMORY':
            review_ids = [rid for rid, text in pending if covers(text, groups)]
            if review_ids:
                status = 'IN_REVIEW_QUEUE'
        entry = {'id': question['id'], 'question': question['question'], 'status': status, 'memory_ids': holders}
        if review_ids:
            entry['review_ids'] = review_ids
        if status == 'IN_MEMORY_NOT_DELIVERED':
            entry['why_not_delivered'] = {mid: (why.get(mid) or {}).get('reason', 'NOT_RANKED') for mid in holders}
        results.append(entry)
    return {'bootstrap_status': bootstrap.get('status'), 'delivered_memories': len(bootstrap.get('selected_ids', [])),
            'score': sum(r['status'] == 'IN_CONTEXT' for r in results), 'of': len(results),
            'in_memory_not_delivered': sum(r['status'] == 'IN_MEMORY_NOT_DELIVERED' for r in results),
            'in_review_queue': sum(r['status'] == 'IN_REVIEW_QUEUE' for r in results),
            'results': results}
