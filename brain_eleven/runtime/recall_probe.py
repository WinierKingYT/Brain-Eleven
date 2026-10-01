"""Automated version of the owner's five-question recall test (TEST-LOG.md).

For each question it answers one thing without asking a model: is the
information the key answer needs in the context SessionStart would deliver
to a fresh session right now, and if not, is it in canonical memory at all?

- IN_CONTEXT: one record of the bootstrap context holds every term group of
  the key answer.
- IN_CONTEXT_SPLIT: the groups are only spread over several records; this can
  be a false positive (2026-09-27: probe said Q3 was delivered, a fresh
  session said "bilmiyorum"), so it is reported and not scored.
- IN_MEMORY_NOT_DELIVERED: an active memory holds it, the bootstrap did not
  select it (a selection problem; the memory ids are listed).
- IN_REVIEW_QUEUE: no active memory holds it, but pending review candidates
  do; accepting them is the fix (review ids are listed). When no single
  candidate holds every part of the answer, ``split`` is true and the ids are
  a small set that together does, the same rule memories already follow.
- NOT_IN_MEMORY: neither memory nor the pending queue holds it: the session
  was not captured, or its candidate expired / was rejected (their text is
  deleted by design), so the fact has to be recorded again.

It is a proxy, not the full test: a present fact can still be answered
badly. The questions are the owner's existing five, read from
evals/recall_probe/questions.json; nothing here is a new evaluation set.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_QUESTIONS = Path(__file__).resolve().parents[2] / 'evals' / 'recall_probe' / 'questions.json'
_TR_UPPER = str.maketrans({'I': 'ı', 'İ': 'i'})


def _fold(text):
    return (text or '').translate(_TR_UPPER).lower()


def covers(text, groups):
    # Turkish folding maps "I" to "ı", which breaks English words such as
    # "Intelligence"; a term counts when either folding matches.
    folded, plain = _fold(text), (text or '').lower()
    return all(any(_fold(term) in folded or term.lower() in plain for term in group) for group in groups)


def in_context(context, groups):
    """'WHOLE' when one context record holds every group, 'SPLIT' when only their union does.

    Context records are the blank-line separated blocks of the bootstrap text
    (one per memory). A SPLIT match can be a false positive (the words of an
    answer spread over unrelated records), so only WHOLE counts toward the score.
    """
    blocks = [b for b in re.split(r'\n\s*\n', context or '') if b.strip()]
    if any(covers(block, groups) for block in blocks):
        return 'WHOLE'
    if covers(context, groups):
        return 'SPLIT'
    return None


def load_questions(path=None):
    return json.loads(Path(path or _QUESTIONS).read_text(encoding='utf-8-sig'))['questions']


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


def split_cover(items, groups):
    """Greedy small set of (id, text) items that together hold every group, or []."""
    remaining = list(range(len(groups)))
    chosen = []
    while remaining:
        best, best_hits = None, []
        for item_id, text in items:
            hits = [i for i in remaining if covers(text, [groups[i]])]
            if len(hits) > len(best_hits):
                best, best_hits = item_id, hits
        if best is None:
            return []
        chosen.append(best)
        remaining = [i for i in remaining if i not in best_hits]
    return chosen


def review_ids_for(pending, groups):
    """(review ids, split) for one question's key answer in the pending queue."""
    whole = [rid for rid, text in pending if covers(text, groups)]
    if whole:
        return whole, False
    return split_cover(pending, groups), True


def review_tags(pending, questions=None):
    """review id -> recall question ids it helps answer (whole or as part of a split)."""
    questions = load_questions() if questions is None else questions
    tags = {}
    for question in questions:
        for rid in review_ids_for(pending, question['groups'])[0]:
            tags.setdefault(rid, []).append(question['id'])
    return tags


SERVICE_WARM_TIMEOUT_SECONDS = 90


def wait_for_service_warm(vault, *, timeout=SERVICE_WARM_TIMEOUT_SECONDS, sleep=None):
    """Seconds waited until the service reports prompt models ready, or None.

    None also when the service settled without real models (nothing to wait
    for; it answers in V1 order) or never became reachable.
    """
    import time
    from .launcher import ensure_service, request_service
    sleep = sleep or time.sleep
    start = time.monotonic()
    if not ensure_service(vault, wait=True, wait_timeout=2.2):
        return None
    while time.monotonic() - start < timeout:
        try:
            status = request_service(vault, '/api/runtime/status', None, timeout=2) or {}
            if status.get('prompt_providers_ready'):
                return round(time.monotonic() - start, 1)
            if status.get('prompt_providers_state') == 'unavailable':
                return None
        except (OSError, ValueError, KeyError, AttributeError):
            pass
        sleep(1)
    return None


def probe(vault, project_root=None, *, questions_path=None, mode='bootstrap'):
    from brain_eleven.memory import MemoryStore
    if mode not in {'bootstrap', 'prompt'}:
        raise ValueError("Recall probe mode must be 'bootstrap' or 'prompt'")

    project_root = project_root or vault
    bootstrap = None
    context = ''
    why = {}
    if mode == 'bootstrap':
        from .context import compile_bootstrap, explain_bootstrap
        bootstrap = compile_bootstrap(vault, project_root)
        context = bootstrap.get('context', '') or ''
        project_id = bootstrap.get('project_id')
        try:
            why = explain_bootstrap(vault, project_root).get('memories', {})
        except Exception:
            why = {}
    else:
        from brain_eleven.projects.registry import ProjectRegistry
        from .context import compile_bootstrap
        # A real fresh turn sees both surfaces: SessionStart remains in the
        # model context when UserPromptSubmit adds question-specific context.
        # Measure their union instead of treating the prompt addition as the
        # whole model-facing context.
        prompt_bootstrap = compile_bootstrap(vault, project_root)
        context = prompt_bootstrap.get('context', '') or ''
        project = ProjectRegistry(vault).resolve(project_root)
        project_id = project.get('project_id') if project else None
    memories = [m for m in MemoryStore(vault).load()['validated_memory']
                if str(m.get('status') or 'active') == 'active'
                and (not project_id or m.get('project_id') in (project_id, '', None))]
    pending = pending_candidate_texts(vault, project_id)
    results = []
    prompt_context_statuses = {}
    warm_wait = None
    if mode == 'prompt':
        # The prompt path is served by the background service; right after it
        # starts it answers in V1 order for ~25 s while models load. Wait for
        # it, so the probe measures what a normal prompt gets.
        warm_wait = wait_for_service_warm(vault)
    for question in load_questions(questions_path):
        groups = question['groups']
        prompt_context = None
        question_context = context
        if mode == 'prompt':
            from .launcher import ensure_service, request_service
            if ensure_service(vault, wait=True, wait_timeout=2.2):
                try:
                    prompt_context = request_service(vault, '/api/context', {
                        'project_root': str(project_root),
                        'request': question['question'],
                        'client': 'codex',
                        'session': 'recall-probe',
                        'turn': f"recall-probe:{question['id']}",
                        'event': 'UserPromptSubmit',
                    }, timeout=2)
                except (OSError, ValueError, json.JSONDecodeError):
                    prompt_context = None
            if prompt_context is None:
                prompt_context = {
                    'status': 'SERVICE_UNAVAILABLE', 'context': '',
                    'selected_ids': [], 'delivered': False,
                }
            prompt_addition = prompt_context.get('context', '') or ''
            question_context = '\n\n'.join(part for part in (context, prompt_addition) if part)
            prompt_context_statuses[str(question['id'])] = prompt_context.get('status', 'UNKNOWN')
        placement = in_context(question_context, groups)
        if placement == 'WHOLE':
            status, holders = 'IN_CONTEXT', []
        elif placement == 'SPLIT':
            # Words present but spread over records: reported, not scored.
            status, holders = 'IN_CONTEXT_SPLIT', []
        else:
            holders = [m.get('memory_id') for m in memories if covers(m.get('content', ''), groups)]
            if not holders:
                # A key answer may be split across memories: every group held by some memory.
                if all(any(covers(m.get('content', ''), [g]) for m in memories) for g in groups):
                    holders = sorted({m.get('memory_id') for g in groups for m in memories
                                      if covers(m.get('content', ''), [g])})
            status = 'IN_MEMORY_NOT_DELIVERED' if holders else 'NOT_IN_MEMORY'
        review_ids, split = [], False
        if status == 'NOT_IN_MEMORY':
            review_ids, split = review_ids_for(pending, groups)
            if review_ids:
                status = 'IN_REVIEW_QUEUE'
        entry = {'id': question['id'], 'question': question['question'], 'status': status, 'memory_ids': holders}
        if review_ids:
            entry['review_ids'] = review_ids
            entry['split'] = split
        if status == 'IN_MEMORY_NOT_DELIVERED':
            if prompt_context is None:
                entry['why_not_delivered'] = {mid: (why.get(mid) or {}).get('reason', 'NOT_RANKED') for mid in holders}
            else:
                reason = 'PROMPT_NOT_DELIVERED' if not prompt_context.get('delivered') else 'NOT_SELECTED'
                entry['why_not_delivered'] = {mid: reason for mid in holders}
        if prompt_context is not None:
            entry['context_status'] = prompt_context.get('status', 'UNKNOWN')
        results.append(entry)
    result = {'bootstrap_status': bootstrap.get('status') if bootstrap else None,
              'delivered_memories': len(bootstrap.get('selected_ids', [])) if bootstrap else 0,
              'score': sum(r['status'] == 'IN_CONTEXT' for r in results), 'of': len(results),
              'in_memory_not_delivered': sum(r['status'] == 'IN_MEMORY_NOT_DELIVERED' for r in results),
              'in_review_queue': sum(r['status'] == 'IN_REVIEW_QUEUE' for r in results),
              'in_context_split': sum(r['status'] == 'IN_CONTEXT_SPLIT' for r in results),
              'results': results}
    if mode == 'prompt':
        result['mode'] = mode
        result['service_warm_wait_s'] = warm_wait
        result['prompt_context_statuses'] = prompt_context_statuses
    return result
