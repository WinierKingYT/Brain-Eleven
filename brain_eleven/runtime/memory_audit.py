"""Weekly memory audit (owner decision 2026-09-30, step 5 of the quality plan).

Keeps canonical memory clean after it has been written:

- exact duplicates (semantic similarity >= EXACT_DUPLICATE) are retired
  automatically, keeping the copy that was used/delivered more (then the
  newer one); nothing is deleted, retirement goes through the truth engine;
- near duplicates and contradictions (local model, three-way SAME/CONFLICT/
  DIFFERENT question), stale status notes
  and never-delivered memories are only *suggested* for a person.

Recall guard: a memory that is the only one holding the whole answer to a
recall question (official set and local ``runtime/questions-*.json``) is
never retired; 2026-09-30 a manual clean-up retired exactly such a record.
Results go to ``runtime/memory-audit.json`` (ids and reason codes only).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

EXACT_DUPLICATE = 0.95
NEAR_DUPLICATE = 0.85
CONTRADICTION_FLOOR = 0.70
STATUS_NOTE_DAYS = 14
UNUSED_DAYS = 28
MAX_MODEL_PAIRS = 30

_STATUS_NOTE = re.compile(
    r'\b(?:currently|right now|still|in progress|for now|şu an(?:da)?|hâlâ|halen|devam ediyor|bekleniyor)\b', re.IGNORECASE)

_RELATION_PROMPT = """Two memory records from one software project.
SAME: they state the same fact/decision (one can be dropped).
CONFLICT: they disagree about the same thing (the newer replaces the older).
DIFFERENT: related but each says something the other does not.
Answer JSON only: {"relation": "SAME" | "CONFLICT" | "DIFFERENT"}
A: <<<%s>>>
B: <<<%s>>>"""


def _parse_time(value):
    try:
        moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _age_days(memory, now):
    moment = _parse_time(memory.get('timestamp') or memory.get('occurred_at'))
    return None if moment is None else (now - moment).total_seconds() / 86400


def _recall_questions(vault):
    from .recall_probe import load_questions
    from .storage import RuntimeConfig
    questions = []
    try:
        questions += load_questions()
    except (OSError, ValueError, KeyError):
        pass
    for path in sorted(RuntimeConfig(vault).root.glob('questions-*.json')):
        try:
            questions += load_questions(path)
        except (OSError, ValueError, KeyError):
            continue
    return questions


def protected_ids(memories, questions):
    """Ids that are the only whole-answer carrier for some recall question."""
    from .recall_probe import covers
    protected = set()
    for question in questions:
        carriers = [m['memory_id'] for m in memories if covers(str(m.get('content') or ''), question['groups'])]
        if len(carriers) == 1:
            protected.add(carriers[0])
    return protected


def _similarity_fn(vault):
    """Cosine over local embeddings when available, else word Jaccard."""
    import math

    try:
        from .context import _embed_cached, _prompt_providers, prompt_provider_config
        embedding_provider, _ = _prompt_providers(prompt_provider_config(vault))
        if getattr(embedding_provider, 'provider_id', 'unavailable') == 'unavailable':
            raise LookupError('no embeddings')

        def vectors(texts):
            return _embed_cached(embedding_provider, texts)

        def similarity(a, b):
            va, vb = a['_vector'], b['_vector']
            dot = sum(x * y for x, y in zip(va, vb))
            norm = math.sqrt(sum(x * x for x in va)) * math.sqrt(sum(y * y for y in vb))
            return dot / norm if norm else 0.0
        return 'embedding', vectors, similarity
    except Exception:
        return _jaccard()


def _jaccard():
    from .review import _words

    def similarity(a, b):
        wa, wb = _words(a.get('content', '')), _words(b.get('content', ''))
        return len(wa & wb) / len(wa | wb) if wa | wb else 0.0
    return 'jaccard', None, similarity


def _keep_first(a, b, usage):
    """Order a duplicate pair so the copy to keep comes first."""
    def rank(memory):
        counts = usage.get(memory['memory_id'], {})
        return (int(counts.get('used', 0)), int(counts.get('delivered', 0)),
                str(memory.get('timestamp') or ''), len(str(memory.get('content') or '')))
    return (a, b) if rank(a) >= rank(b) else (b, a)


def _ask_relation(older, newer, model_fn):
    """'SAME', 'CONFLICT' or 'DIFFERENT' from the local model; None when unavailable.

    A yes/no "conflict?" prompt flagged every related pair on the real memory
    (2026-09-30); the three-way question flagged only the true duplicate.
    """
    if model_fn is not None:
        return model_fn(older, newer)
    import urllib.request

    from .queue_triage import DEFAULT_MODEL, MODEL_TIMEOUT_SECONDS, OLLAMA_URL
    body = json.dumps({'model': DEFAULT_MODEL, 'stream': False, 'format': 'json', 'options': {'temperature': 0},
                       'messages': [{'role': 'user', 'content': _RELATION_PROMPT % (older[:500], newer[:500])}]})
    request = urllib.request.Request(OLLAMA_URL, data=body.encode('utf-8'), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=MODEL_TIMEOUT_SECONDS) as response:  # nosec B310 - fixed local URL
            answer = json.loads(json.loads(response.read().decode('utf-8'))['message']['content'])
    except Exception:
        return None
    relation = str(answer.get('relation') or '').upper()
    return relation if relation in {'SAME', 'CONFLICT', 'DIFFERENT'} else None


def audit(vault, *, apply=False, use_model=True, now=None, model_fn=None, similarity_fn=None):
    """Run the audit; with ``apply`` retire guarded exact duplicates. Returns the report."""
    from brain_eleven.memory import MemoryStore

    from .memory_usage import started_at, usage
    from .staleness import retire
    from .storage import RuntimeConfig, write_json

    now = now or datetime.now(timezone.utc)
    memories = [dict(m) for m in MemoryStore(vault).load()['validated_memory']
                if str(m.get('status') or 'active') == 'active' and m.get('memory_id')]
    counts = usage(vault)
    guard = protected_ids(memories, _recall_questions(vault))
    method, vectors, similarity = similarity_fn or _similarity_fn(vault)
    if vectors is not None:
        embedded = vectors([str(m.get('content') or '') for m in memories]) or []
        if len(embedded) != len(memories):
            method, vectors, similarity = _jaccard()
        else:
            for memory, vector in zip(memories, embedded):
                memory['_vector'] = vector

    report = {'at': now.isoformat(), 'method': method, 'active': len(memories), 'protected': sorted(guard),
              'retired': [], 'suggestions': []}
    retired = set()
    pairs = []
    for i, first in enumerate(memories):
        for second in memories[i + 1:]:
            if first.get('project_id') != second.get('project_id'):
                continue
            score = similarity(first, second)
            if score >= CONTRADICTION_FLOOR:
                pairs.append((score, first, second))
    pairs.sort(key=lambda entry: -entry[0])

    asked = 0
    for score, first, second in pairs:
        if first['memory_id'] in retired or second['memory_id'] in retired:
            continue
        keep, drop = _keep_first(first, second, counts)
        if score >= EXACT_DUPLICATE:
            if drop['memory_id'] in guard:
                keep, drop = drop, keep
            if drop['memory_id'] in guard:
                report['suggestions'].append({'kind': 'DUPLICATE_PROTECTED', 'memory_id': drop['memory_id'],
                                              'other_id': keep['memory_id'], 'similarity': round(score, 3)})
                continue
            entry = {'memory_id': drop['memory_id'], 'kept': keep['memory_id'], 'similarity': round(score, 3)}
            if apply:
                try:
                    retire(vault, drop['memory_id'], f"Hafıza denetimi: birebir tekrar, {keep['memory_id']} korundu.")
                except ValueError:
                    continue
            retired.add(drop['memory_id'])
            report['retired'].append(entry)
        elif score >= NEAR_DUPLICATE:
            report['suggestions'].append({'kind': 'NEAR_DUPLICATE', 'memory_id': drop['memory_id'],
                                          'other_id': keep['memory_id'], 'similarity': round(score, 3)})
        elif use_model and asked < MAX_MODEL_PAIRS:
            older, newer = sorted((first, second), key=lambda m: str(m.get('timestamp') or ''))
            asked += 1
            relation = _ask_relation(str(older.get('content') or ''), str(newer.get('content') or ''), model_fn)
            if relation == 'SAME':
                if drop['memory_id'] in guard:
                    keep, drop = drop, keep
                report['suggestions'].append({'kind': 'NEAR_DUPLICATE', 'memory_id': drop['memory_id'],
                                              'other_id': keep['memory_id'], 'similarity': round(score, 3),
                                              'by': 'model'})
            elif relation == 'CONFLICT':
                report['suggestions'].append({'kind': 'CONTRADICTION', 'memory_id': older['memory_id'],
                                              'other_id': newer['memory_id'], 'similarity': round(score, 3)})

    since = _parse_time(started_at(vault))
    tracking_days = None if since is None else (now - since).total_seconds() / 86400
    for memory in memories:
        if memory['memory_id'] in retired:
            continue
        age = _age_days(memory, now)
        if (memory.get('type') == 'observation' and age is not None and age >= STATUS_NOTE_DAYS
                and _STATUS_NOTE.search(str(memory.get('content') or ''))):
            report['suggestions'].append({'kind': 'STALE_STATUS_NOTE', 'memory_id': memory['memory_id']})
        if (tracking_days is not None and tracking_days >= UNUSED_DAYS and age is not None and age >= UNUSED_DAYS
                and not counts.get(memory['memory_id'], {}).get('delivered')
                and memory['memory_id'] not in guard):
            report['suggestions'].append({'kind': 'NEVER_DELIVERED', 'memory_id': memory['memory_id']})

    report['applied'] = bool(apply)
    write_json(RuntimeConfig(vault).root / 'memory-audit.json', report)
    return report
