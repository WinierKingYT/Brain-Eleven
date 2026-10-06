"""Probation for memories written without a person (owner decision 2026-10-02).

A memory the worker or a model accepted is checked again within its first
PROBATION_DAYS:

- The deterministic triage rules (machine content, pasted output or document,
  too short/long) retire it when they fire: they are precise (2026-10-06: every
  hit on the real store was junk). Retire means status resolved, never
  deleted; the recall guard still protects the last carrier of a recall answer.
- The local model gives a sceptical second opinion that only FLAGS the
  memory for the owner's weekly sample. It never retires: measured
  2026-10-06 on 54 worker memories, qwen2.5:7b kept code and tool output and
  dropped short Turkish decisions, so its DROP is not evidence.
- Being unused is never a reason: knowledge from one project may be needed
  months later in another.

Memories the owner wrote (/remember, daily notes) or accepted by hand are
never on probation.
"""

from __future__ import annotations

from datetime import datetime, timezone

PROBATION_DAYS = 14
RESOLVED_BY = 'probation'
_HUMAN_NOTE_PREFIX = 'Model onayı'

_PROMPT = """A software project's memory system saved this record automatically. Check it sceptically.
Answer DROP if it is any of these:
- a proposal, plan, option or idea that is not stated as done or decided
- a fragment that needs missing context to be understood
- code, a file or path list, a table row, a heading or log output
- chat, a greeting, a question or a remark about the conversation itself
Answer KEEP only if it is a self-contained decision, lesson or fact about the project
that a developer would want to remember months later.
Answer JSON only: {"decision": "KEEP" or "DROP"}
Record: <<<%s>>>"""
MAX_CHARS = 1200


def second_opinion(text, *, chat=None, model=None):
    """'KEEP', 'DROP', or None when the model is unavailable or answers nonsense."""
    from .queue_triage import DEFAULT_MODEL, _chat
    ask = chat or (lambda prompt: _chat(prompt, model=model or DEFAULT_MODEL))
    answer = ask(_PROMPT % ' '.join(str(text or '').split())[:MAX_CHARS])
    decision = str((answer or {}).get('decision') or '').upper() if isinstance(answer, dict) else ''
    return decision if decision in {'KEEP', 'DROP'} else None


# Only rules about the *form* of the text retire: length or question rules
# fit the review queue but could retire a long, valid lesson.
RETIRE_REASONS = frozenset({'MACHINE_CONTENT', 'PASTED_OUTPUT', 'PASTED_DOCUMENT'})


def rule_reason(text):
    """The deterministic reason a memory is junk, or ''."""
    from .extraction import _legacy
    from .queue_triage import rule_verdict
    text = str(text or '')
    if _legacy._pasted_document(text):
        return 'PASTED_DOCUMENT'
    verdict, reason = rule_verdict({'candidate_type': 'NEW_MEMORY', 'commitment': 'COMMITTED', 'content': text})
    return reason if verdict == 'REJECT' and reason in RETIRE_REASONS else ''


def flagged_ids(vault):
    """Memories the model's second opinion flagged, for the owner's weekly sample."""
    from .storage import RuntimeConfig, read_json
    state = read_json(RuntimeConfig(vault).root / 'probation.json', {}) or {}
    checked = state.get('checked') if isinstance(state, dict) else {}
    return [memory_id for memory_id, entry in (checked or {}).items()
            if isinstance(entry, dict) and entry.get('verdict') == 'MODEL_DROP']


def human_accepted_ids(vault):
    """Memory ids a person accepted in review (not a model, whose note starts 'Model onayı')."""
    from .review import ReviewStore
    found = set()
    for item in ReviewStore(vault)._items():
        if not isinstance(item, dict) or item.get('status') != 'ACCEPTED':
            continue
        if str(item.get('decision_note') or '').startswith(_HUMAN_NOTE_PREFIX):
            continue
        result = item.get('result') if isinstance(item.get('result'), dict) else {}
        for decision in result.get('decisions') or ():
            if not isinstance(decision, dict):
                continue
            # A person confirming an existing memory (duplicate/confirm) names it as target.
            for key in ('successor_memory_id', 'target_memory_id'):
                if decision.get(key):
                    found.add(decision[key])
    return found


def on_probation(memories, human_ids, now):
    """Active worker-written memories younger than PROBATION_DAYS that no person accepted."""
    from .memory_audit import _age_days
    selected = []
    for memory in memories:
        if str(memory.get('status') or 'active') != 'active' or memory.get('source') != 'worker':
            continue
        if memory.get('memory_id') in human_ids:
            continue
        age = _age_days(memory, now)
        if age is not None and 0 <= age < PROBATION_DAYS:
            selected.append(memory)
    return selected


def review(vault, *, apply=False, now=None, chat=None, limit=20):
    """Give each unchecked probationary memory a second opinion; retire DROPs when ``apply``."""
    from brain_eleven.memory import MemoryStore

    from .memory_audit import _recall_questions, protected_ids
    from .staleness import retire
    from .storage import RuntimeConfig, read_json, write_json

    now = now or datetime.now(timezone.utc)
    path = RuntimeConfig(vault).root / 'probation.json'
    state = read_json(path, {}) or {}
    checked = dict(state.get('checked') or {}) if isinstance(state, dict) else {}
    memories = [m for m in MemoryStore(vault).load()['validated_memory'] if m.get('memory_id')]
    active = [m for m in memories if str(m.get('status') or 'active') == 'active']
    questions = _recall_questions(vault)
    report = {'at': now.isoformat(), 'apply': apply, 'kept': 0, 'retired': [], 'flagged': [],
              'protected': [], 'unavailable': 0, 'pending': 0}
    asked = 0
    model_down = False
    retired = set()
    for memory in on_probation(active, human_accepted_ids(vault), now):
        memory_id = memory['memory_id']
        if memory_id in checked:
            continue
        rule = rule_reason(memory.get('content'))
        if rule:
            live = [m for m in active if m['memory_id'] not in retired]
            if questions is None or memory_id in protected_ids(live, questions):
                report['protected'].append(memory_id)
                verdict = 'RULE_PROTECTED'
            else:
                verdict = 'RULE_' + rule
                if apply:
                    try:
                        retire(vault, memory_id, f'Deneme süresi: kural {rule}.', resolved_by=RESOLVED_BY)
                    except ValueError:
                        continue
                    retired.add(memory_id)
                report['retired'].append({'memory_id': memory_id, 'reason': rule})
        else:
            if asked >= limit:
                report['pending'] += 1
                continue
            asked += 1
            opinion = None if model_down else second_opinion(memory.get('content'), chat=chat)
            if opinion is None:
                # Asked again on a later run; after one failure this run stops
                # asking, so a stopped local model cannot hold the cycle for minutes.
                model_down = True
                report['unavailable'] += 1
                continue
            verdict = 'MODEL_' + opinion
            if opinion == 'DROP':
                report['flagged'].append(memory_id)
            else:
                report['kept'] += 1
        if apply:
            checked[memory_id] = {'at': now.isoformat(), 'verdict': verdict}
            # Saved after every verdict: an interrupted run keeps its progress.
            write_json(path, {'checked': checked, 'last': report})
    if apply:
        write_json(path, {'checked': checked, 'last': report})
    return report
