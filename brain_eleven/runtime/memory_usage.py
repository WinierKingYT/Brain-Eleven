"""Per-memory usage signal (owner decision 2026-09-30).

Two counters per canonical memory id, stored in
``runtime/memory-usage.json`` (ids, counts and times only, never text):

- delivered: the hook handed the memory to the model (SessionStart or a
  prompt), with the time of the last delivery;
- used: a later assistant reply in the same session shares most of the
  memory's distinctive words. This is an approximation: several memories
  arrive together, and a reply can echo one without relying on it.

The weekly memory audit reads these counters to spot memories that are never
delivered or never used. Recording is advisory: any failure is swallowed and
never affects delivery or capture.
"""
from __future__ import annotations

import hashlib
import re

MAX_SESSIONS = 200
USE_OVERLAP = 0.5
MIN_DISTINCTIVE_WORDS = 3
_WORD = re.compile(r'[\wçğıöşüÇĞİÖŞÜ][\w\-çğıöşüÇĞİÖŞÜ]{3,}', re.UNICODE)
_COMMON = frozenset("""
this that with from have were will would should could there their about which when what then than
into also only just more most such some each other these those they them been being over under after
before because while where your ours ourselves bir için olarak olan daha çok gibi kadar sonra önce ancak
fakat ama veya ile bunu şunu buna şuna bunun şunun artık hâlâ yani şimdi burada orada değil
""".split())


def session_hash(session_key):
    """Content-free id shared by the hook and the worker for one session."""
    return 'sha256:' + hashlib.sha256(str(session_key).encode('utf-8')).hexdigest()


def distinctive_words(text):
    return {w.lower() for w in _WORD.findall(text or '') if w.lower() not in _COMMON}


def _path(vault):
    from .storage import RuntimeConfig
    return RuntimeConfig(vault).root / 'memory-usage.json'


def _load(path):
    from .storage import read_json
    document = read_json(path, {}) or {}
    if not isinstance(document, dict):
        document = {}
    memories = document.get('memories') if isinstance(document.get('memories'), dict) else {}
    sessions = document.get('sessions') if isinstance(document.get('sessions'), dict) else {}
    started = document.get('started_at') if isinstance(document.get('started_at'), str) else None
    return {'schema_version': 1, 'started_at': started, 'memories': memories, 'sessions': sessions}


def _update(vault, mutate):
    from .storage import runtime_file_lock, write_json
    path = _path(vault)
    # Short timeout: delivery runs on the prompt path and must never wait.
    with runtime_file_lock(path, timeout=0.5):
        document = _load(path)
        mutate(document)
        write_json(path, document)


def record_delivery(vault, memory_ids, *, session_key, event, at):
    """Count one delivery of each memory id and remember them for the session."""
    ids = [m for m in dict.fromkeys(memory_ids or ()) if isinstance(m, str) and m]
    if not ids:
        return
    kind = 'bootstrap' if event == 'SessionStart' else 'prompt'

    def mutate(document):
        document['started_at'] = document.get('started_at') or at
        for memory_id in ids:
            entry = document['memories'].setdefault(memory_id, {})
            entry['delivered'] = int(entry.get('delivered', 0)) + 1
            entry[kind + '_delivered'] = int(entry.get(kind + '_delivered', 0)) + 1
            entry['last_delivered'] = at
        sessions = document['sessions']
        key = session_hash(session_key)
        pending = list(dict.fromkeys([*(sessions.get(key, {}).get('ids') or []), *ids]))
        sessions[key] = {'at': at, 'ids': pending[-50:]}
        if len(sessions) > MAX_SESSIONS:
            for old in sorted(sessions, key=lambda k: str(sessions[k].get('at')))[:len(sessions) - MAX_SESSIONS]:
                sessions.pop(old, None)

    try:
        _update(vault, mutate)
    except Exception:
        pass


def record_use(vault, session_key, assistant_texts, *, at, contents):
    """Mark delivered memories the session's assistant replies clearly drew on.

    ``contents`` maps memory id -> memory text (only the session's delivered
    ids are looked up). A memory counts as used once per session.
    """
    reply = set()
    for text in assistant_texts or ():
        reply |= distinctive_words(text)
    if not reply:
        return

    def mutate(document):
        key = session_hash(session_key)
        session = document['sessions'].get(key)
        if not session:
            return
        used_here = set(session.get('used') or [])
        for memory_id in session.get('ids') or []:
            if memory_id in used_here:
                continue
            words = distinctive_words(contents.get(memory_id, ''))
            if len(words) < MIN_DISTINCTIVE_WORDS or len(words & reply) / len(words) < USE_OVERLAP:
                continue
            entry = document['memories'].setdefault(memory_id, {})
            entry['used'] = int(entry.get('used', 0)) + 1
            entry['last_used'] = at
            used_here.add(memory_id)
        session['used'] = sorted(used_here & set(session.get('ids') or []))

    try:
        _update(vault, mutate)
    except Exception:
        pass


def delivered_ids(vault, session_key):
    """Ids delivered in this session so far (read-only, empty on any error)."""
    try:
        return list(_load(_path(vault))['sessions'].get(session_hash(session_key), {}).get('ids') or [])
    except Exception:
        return []


def started_at(vault):
    """When usage recording began (first delivery), or None."""
    try:
        return _load(_path(vault)).get('started_at')
    except Exception:
        return None


def usage(vault):
    """The stored counters (read-only)."""
    return _load(_path(vault))['memories']
