"""Automatic noise filter for review candidates (layer 1 of review triage).

Most captured candidates are not memories: quoted text, short acks
("tamam", "evet"), terminal output, and low-evidence prose. They used to
reach the review queue and bury the few real decisions. These rules drop
them before the queue, and ``triage`` applies the same rules to candidates
already waiting.

The rules are the owner-reviewed bulk filters that matched zero recall
answers and zero committed decisions on the real queue (2026-09-26). A
committed decision is never filtered, whatever rule it matches. Nothing is
written to canonical memory; filtered candidates are only counted (no
text), and existing ones are rejected with a note, never deleted.
Set ``auto_triage: false`` in the runtime config to turn it off.
"""

from __future__ import annotations

from .review import ReviewStore, content_shape
from .storage import RuntimeConfig, now, read_json, write_json

RULES = (
    ('QUOTED', lambda reason, commitment, shape: commitment == 'QUOTED'),
    ('SHORT_ACK', lambda reason, commitment, shape: shape == 'short_ack'),
    ('LOW_EVIDENCE_PROSE', lambda reason, commitment, shape: reason == 'LOW_EVIDENCE_COMMITMENT' and shape == 'prose'),
    ('LOW_EVIDENCE_CODE', lambda reason, commitment, shape: reason == 'LOW_EVIDENCE_COMMITMENT' and shape == 'terminal_or_code'),
    ('OBSERVED_UNKNOWN_TARGET', lambda reason, commitment, shape: reason == 'LIFECYCLE_TARGET_UNKNOWN' and commitment == 'OBSERVED'),
)


def _text(candidate):
    text = candidate.get('text') if candidate.get('candidate_type') == 'STATE_MUTATION' else candidate.get('content')
    return text if isinstance(text, str) else ''


def noise_rule(candidate, reason):
    """Name of the first noise rule the candidate matches, or None."""
    if not isinstance(candidate, dict):
        return None
    commitment = candidate.get('commitment')
    if commitment == 'COMMITTED' and candidate.get('memory_type') == 'decision':
        return None
    shape = content_shape(_text(candidate))
    for name, rule in RULES:
        if rule(reason, commitment, shape):
            return name
    return None


def enabled(vault):
    return RuntimeConfig(vault).load().get('auto_triage', True) is not False


def _counts_path(vault):
    return RuntimeConfig(vault).root / 'auto-triage.json'


def record(vault, rule):
    """Count one filtered candidate by rule; never stores its text."""
    path = _counts_path(vault)
    counts = read_json(path, {}) or {}
    by_rule = counts.get('by_rule') if isinstance(counts.get('by_rule'), dict) else {}
    by_rule[rule] = int(by_rule.get(rule, 0)) + 1
    write_json(path, {'since': counts.get('since') or now(), 'updated_at': now(),
                      'total': sum(by_rule.values()), 'by_rule': by_rule})


def summary(vault):
    return read_json(_counts_path(vault), {}) or {}


def filter_candidate(vault, candidate, reason):
    """True when the candidate is noise and was counted instead of queued."""
    if not enabled(vault):
        return False
    rule = noise_rule(candidate, reason)
    if rule is None:
        return False
    record(vault, rule)
    return True


def triage_existing(vault, *, apply=False):
    """Apply the noise rules to candidates already pending (dry run by default)."""
    store = ReviewStore(vault)
    result = {'dry_run': not apply, 'by_rule': {}, 'matched': 0}
    for name, _ in RULES:
        def predicate(item, name=name):
            candidate = item.get('candidate') if isinstance(item.get('candidate'), dict) else {}
            return noise_rule(candidate, item.get('reason')) == name
        outcome = store.reject_matching(predicate, f'Otomatik süzgeç: {name}', dry_run=not apply)
        result['by_rule'][name] = outcome.get('matched', 0)
        result['matched'] += outcome.get('matched', 0)
    return result
