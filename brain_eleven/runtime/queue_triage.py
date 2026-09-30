"""Automatic pre-evaluation of the review queue (owner decision 2026-09-30).

Until now ``runtime/review-suggestions.json`` was written by a model session
run by hand; when those sessions stopped, nothing reached memory from capture
(27 Sep - 30 Sep: zero). This module writes those suggestions itself:

1. Deterministic rules first. Clear noise (pasted tool output, diffs and
   markup, questions, fragments, observed-only state changes) is REJECTED,
   i.e. hidden until it expires. Rules never accept.
2. Everything the rules leave open goes to the verifier: the local model
   (Ollama, default ``qwen2.5:7b``, no cloud quota) answers KEEP/DROP, then a
   fragment and project check. VERIFIED items are left for a person as
   MODEL_VERIFIED, or written when ``auto_accept_verified`` is on; DROP and
   fragments are hidden; a suspected wrong project is left for a person. When
   the model is not reachable or answers nonsense, items are retried later.

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


_VERIFY_PROMPT = """You check candidate memories for a software project's long-term memory.
KEEP only a complete, self-contained statement that stays true and useful for weeks:
 - a decision about the project
 - a lesson learned
 - a durable fact about how the system/code works
DROP: instructions or advice addressed to an AI agent or tool, documentation or tutorial text, a plan or
to-do, a temporary status or report, a fragment that needs missing context, an example or template, a question.
Answer JSON only: {"decision": "KEEP" or "DROP"}
Candidate: <<<%s>>>"""

_PROJECT_PROMPT = """Which software project is this statement about? Projects: %s.
Answer JSON only: {"project": "<one of the names above>" or "UNKNOWN"}
Statement: <<<%s>>>"""

# A statement that starts mid-sentence needs missing context.
# A leading article/particle or conjunction means the text starts mid-sentence;
# identifiers such as "qwen2.5:7b" or "npm ci" are not fragments.
_FRAGMENT = re.compile(r"^(?:the|a|an|of|to|in|on|at|for|with|is|are|was|were|ve|ile|bu|şu|da|de)\s"
                       r"|^(?i:ancak|ama|fakat|çünkü|dolayısıyla|yani|and|but|then|so|or)\b")
MIN_VERIFIED_CHARS = 25


def _chat(prompt, *, model=DEFAULT_MODEL, url=OLLAMA_URL, timeout=MODEL_TIMEOUT_SECONDS):
    body = json.dumps({'model': model, 'stream': False, 'format': 'json', 'options': {'temperature': 0},
                       'messages': [{'role': 'user', 'content': prompt}]}).encode('utf-8')
    request = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - fixed local URL
            answer = json.loads(json.loads(response.read().decode('utf-8'))['message']['content'])
    except Exception:
        return None
    return answer if isinstance(answer, dict) else None


def verify_candidate(candidate, project_labels, *, model=DEFAULT_MODEL, chat=None):
    """(verdict, reason): the second stage for everything the rules left open.

    Verdicts: 'VERIFIED' (keep, right project), 'DROP', 'WRONG_PROJECT',
    'FRAGMENT', or 'UNAVAILABLE'. Measured 2026-09-30 on 59 session-summary
    facts (provisional labels by Claude): about 96% precision, 82% recall.
    ``project_labels`` maps project id -> label (from the registry).
    """
    ask = chat or (lambda prompt: _chat(prompt, model=model))
    text = ' '.join(_text(candidate).split())
    if len(text) < MIN_VERIFIED_CHARS or _FRAGMENT.match(text):
        return 'FRAGMENT', 'FRAGMENT'
    answer = ask(_VERIFY_PROMPT % text[:MAX_KEEP_CHARS])
    if answer is None:
        return 'UNAVAILABLE', 'MODEL_UNAVAILABLE'
    decision = str(answer.get('decision') or '').upper()
    if decision not in {'KEEP', 'DROP'}:
        return 'UNAVAILABLE', 'MODEL_INVALID'  # retried on a later run, never hidden
    if decision == 'DROP':
        return 'DROP', 'VERIFY_DROP'
    own = project_labels.get(candidate.get('project_id'))
    if own and len(project_labels) > 1:
        names = ', '.join(sorted(set(project_labels.values())))
        answer = ask(_PROJECT_PROMPT % (names, text[:MAX_KEEP_CHARS]))
        if answer is None:
            return 'UNAVAILABLE', 'MODEL_UNAVAILABLE'
        named = str(answer.get('project') or '').strip().lower()
        if named and named != 'unknown' and named != own.lower() and named in {v.lower() for v in project_labels.values()}:
            return 'WRONG_PROJECT', 'WRONG_PROJECT'
    return 'VERIFIED', 'MODEL_VERIFIED'


def _project_labels(vault):
    try:
        from brain_eleven.projects.registry import ProjectRegistry
        return {p['project_id']: str(p.get('project_label') or '') for p in ProjectRegistry(vault).list()
                if p.get('project_id')}
    except Exception:
        return {}


def triage(vault, *, use_model=True, model=DEFAULT_MODEL, limit=None, model_fn=None, accept_model=False,
           verify=True, accept_verified=False, chat=None):
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
    listed = ReviewStore(vault).list()
    pending = [x for x in listed if x.get('status') == 'PENDING' and x.get('id') not in suggestions]
    promoted = {}
    if accept_verified:
        # Turning the flag on later also promotes items verified while it was off.
        for x in listed:
            entry = suggestions.get(x.get('id'))
            if (x.get('status') == 'PENDING' and isinstance(entry, dict)
                    and entry.get('suggestion') == 'REVIEW' and entry.get('reason') == 'MODEL_VERIFIED'):
                promoted[x['id']] = {**entry, 'suggestion': 'ACCEPT'}
    counts = {'pending_without_suggestion': len(pending), 'rule_reject': 0,
              'model_accept': 0, 'model_reject': 0, 'model_review': 0, 'left': 0}
    asked = 0
    fresh = {}
    labels = _project_labels(vault)
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
            by = model
            if verify and model_fn is None:
                # Owner decision 2026-09-30: the model's keep/drop answer plus a
                # fragment and project check; only VERIFIED can be accepted.
                outcome, reason = verify_candidate(candidate, labels, model=model, chat=chat)
                if outcome == 'UNAVAILABLE':
                    counts['model_review'] += 1
                    continue
                if outcome == 'VERIFIED':
                    verdict = 'ACCEPT' if accept_verified else 'REVIEW'
                    counts['model_accept' if accept_verified else 'model_review'] += 1
                elif outcome == 'WRONG_PROJECT':
                    # A real fact about another project: the owner decides,
                    # it is never hidden on one model answer.
                    verdict = 'REVIEW'
                    counts['model_review'] += 1
                else:
                    verdict = 'REJECT'
                    counts['model_reject'] += 1
                fresh[item['id']] = {'suggestion': verdict, 'reason': reason, 'by': by}
                continue
            verdict, reason = ask(candidate)
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
        merged.update(promoted)
        merged.update(fresh)
        write_json(path, {'by': 'queue-triage', 'suggestions': merged})
    try:
        from .value import refresh_owner_counts
        refresh_owner_counts(vault)
    except Exception:
        pass  # the notice is advisory
    return counts
