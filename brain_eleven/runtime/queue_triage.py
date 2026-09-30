"""Automatic pre-evaluation of the review queue (owner decision 2026-09-30).

Until now ``runtime/review-suggestions.json`` was written by a model session
run by hand; when those sessions stopped, nothing reached memory from capture
(27 Sep - 30 Sep: zero). This module writes those suggestions itself:

1. Deterministic rules first. Clear noise (pasted tool output, diffs and
   markup, questions, fragments, observed-only state changes) is REJECTED,
   i.e. hidden until it expires. Rules never accept.
2. Everything the rules leave open goes to a local model through Ollama
   (default ``qwen2.5:7b``); no cloud quota is used. Its REJECTs hide the item;
   its ACCEPTs are left for a person, marked MODEL_ACCEPT, unless explicitly
   allowed. When the model is not reachable, items stay for a person.

Suggestions are applied only through ``value.apply_suggestions`` (safety, CAS,
audit, a note naming who suggested it); nothing is deleted, and a wrong
record can be retired later.
"""
from __future__ import annotations

import json
import re
import urllib.request

RULE_BY = 'rules'
DEFAULT_MODEL = 'qwen2.5:7b'
OLLAMA_URL = 'http://127.0.0.1:11434/api/chat'
MODEL_TIMEOUT_SECONDS = 60

MAX_KEEP_CHARS = 600
MIN_KEEP_CHARS = 20
DUPLICATE_SIMILARITY = 0.6

# Certain machine content: code fences, diff hunks and headers, escaped text
# pasted from logs, ANSI codes, JSON objects. Rejected outright.
_MACHINE = re.compile(
    r'```|^[+\-]{3} [ab]/|^@@ |^\s*\+\s*$|\\n[^\n]*\\n|\\u00|\x1b|\{\\?"[\w-]+\\?"\s*:', re.MULTILINE)
# Formatting the owner also types (bold, bullets, headings, tables, comments)
# is deliberately not a rule: such items go to the model (review 2026-09-30).
_MODEL_REASON = re.compile(r'[A-Z_]{1,40}')
_MODEL_VERDICTS = {'ACCEPT', 'REJECT', 'REVIEW'}

_PROMPT = """You triage candidate memories for a personal project-memory system.
A candidate is worth keeping only if it is ONE self-contained statement the user
made about their own project: a decision, a lesson, a preference, or a durable
fact, understandable on its own weeks later without the surrounding chat.

REJECT when it is: pasted tool/terminal/log output, code, a diff or a document
excerpt; instructions addressed to an AI assistant; a question; a short reply
such as "ok, next step"; a fragment that needs missing context; a transient
status ("tests are running now").
ACCEPT only when you are confident it is a self-contained user decision/lesson/
preference/fact. When unsure, answer REVIEW.

Answer with JSON only: {"verdict": "ACCEPT|REJECT|REVIEW", "reason": "UPPER_SNAKE_CODE"}
Candidate (type=%s, commitment=%s):
<<<
%s
>>>"""


def _pasted_output(text):
    from .extraction import _legacy
    return bool(_legacy._PASTED_OUTPUT.search(text))


def _text(candidate):
    if candidate.get('candidate_type') == 'STATE_MUTATION':
        return str(candidate.get('text') or '')
    return str(candidate.get('content') or '')


def rule_verdict(candidate, *, similarity=0.0):
    """(verdict, reason) from deterministic rules, or (None, '') to ask the model."""
    text = _text(candidate).strip()
    kind = candidate.get('candidate_type')
    commitment = candidate.get('commitment')
    if _pasted_output(text):
        return 'REJECT', 'PASTED_OUTPUT'
    if _MACHINE.search(text):
        return 'REJECT', 'MACHINE_CONTENT'
    if len(text) > MAX_KEEP_CHARS:
        return 'REJECT', 'TOO_LONG'
    if len(text) < MIN_KEEP_CHARS:
        return 'REJECT', 'TOO_SHORT'
    if commitment == 'QUESTION':
        return 'REJECT', 'QUESTION'
    if kind == 'STATE_MUTATION' and commitment != 'COMMITTED':
        return 'REJECT', 'STATE_NOT_COMMITTED'
    if similarity >= DUPLICATE_SIMILARITY:
        return 'REJECT', 'DUPLICATE'
    # Rules only reject. Real queue check (2026-09-30): of 25 rule-accepted
    # "committed decisions" ~10 were assistant instructions, docs or code
    # comments, so acceptance is always the local model's call.
    return None, ''


def model_verdict(candidate, *, model=DEFAULT_MODEL, url=OLLAMA_URL, timeout=MODEL_TIMEOUT_SECONDS):
    """(verdict, reason) from the local model; ('REVIEW', 'MODEL_UNAVAILABLE') on any failure."""
    prompt = _PROMPT % (candidate.get('memory_type') or candidate.get('candidate_type'),
                        candidate.get('commitment'), _text(candidate)[:MAX_KEEP_CHARS])
    body = json.dumps({'model': model, 'stream': False, 'format': 'json',
                       'options': {'temperature': 0},
                       'messages': [{'role': 'user', 'content': prompt}]}).encode('utf-8')
    request = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - fixed local URL
            answer = json.loads(json.loads(response.read().decode('utf-8'))['message']['content'])
    except Exception:
        return 'REVIEW', 'MODEL_UNAVAILABLE'
    verdict = str(answer.get('verdict') or '').upper()
    reason = str(answer.get('reason') or '').upper()
    if verdict not in _MODEL_VERDICTS:
        return 'REVIEW', 'MODEL_INVALID'
    return verdict, reason if _MODEL_REASON.fullmatch(reason) else ''


def triage(vault, *, use_model=True, model=DEFAULT_MODEL, limit=None, model_fn=None, accept_model=False):
    """Write suggestions for pending items that have none yet; return counts.

    A model ACCEPT is recorded as REVIEW (reason MODEL_ACCEPT) unless
    ``accept_model``: on the real queue (2026-09-30) qwen2.5:7b accepted 62 of
    155 items of which about 10 were worth keeping, so writing them without a
    person would refill memory with noise. Rejects are safe: they only hide an
    item until it expires.
    """
    from brain_eleven.memory import MemoryStore
    from .review import ReviewStore, rank_similar
    from .storage import RuntimeConfig, read_json, runtime_file_lock as file_lock, write_json

    path = RuntimeConfig(vault).root / 'review-suggestions.json'
    document = read_json(path, {}) or {}
    suggestions = dict(document.get('suggestions') or {}) if isinstance(document, dict) else {}
    memories = [m for m in MemoryStore(vault).load()['validated_memory']
                if str(m.get('status') or 'active') == 'active']
    pending = [x for x in ReviewStore(vault).list()
               if x.get('status') == 'PENDING' and x.get('id') not in suggestions]
    counts = {'pending_without_suggestion': len(pending), 'rule_reject': 0,
              'model_accept': 0, 'model_reject': 0, 'model_review': 0, 'left': 0}
    asked = 0
    fresh = {}
    ask = model_fn or (lambda candidate: model_verdict(candidate, model=model))
    for item in pending:
        candidate = item.get('candidate') or {}
        same_project = [m for m in memories if m.get('project_id') == candidate.get('project_id')]
        top = rank_similar(_text(candidate), same_project, limit=1)
        verdict, reason = rule_verdict(candidate, similarity=top[0][0] if top else 0.0)
        by = RULE_BY
        if verdict is None:
            if not use_model or (limit is not None and asked >= limit):
                counts['left'] += 1
                continue
            asked += 1
            verdict, reason = ask(candidate)
            by = model
            if verdict == 'ACCEPT' and not accept_model:
                verdict, reason = 'REVIEW', 'MODEL_ACCEPT'
            counts['model_' + verdict.lower()] += 1
            if reason in ('MODEL_UNAVAILABLE', 'MODEL_INVALID'):
                continue  # retry on a later run instead of recording a non-answer
        else:
            counts['rule_' + verdict.lower()] += 1
        fresh[item['id']] = {'suggestion': verdict, 'reason': reason, 'by': by}
    # Model calls take minutes: merge into the file as it is *now*, so a run
    # that finished meanwhile (service or CLI) keeps its entries, and give
    # older entries without their own ``by`` the author the file named.
    with file_lock(path):
        current = read_json(path, {}) or {}
        author = str(current.get('by') or 'model') if isinstance(current, dict) else 'model'
        merged = {}
        for review_id, entry in (current.get('suggestions') or {}).items() if isinstance(current, dict) else ():
            merged[review_id] = entry if not isinstance(entry, dict) or entry.get('by') else {**entry, 'by': author}
        merged.update(fresh)
        write_json(path, {'by': 'queue-triage', 'suggestions': merged})
    return counts
