"""One-command real-use measurement (roadmap steps 1-9 evidence).

Runs the read-only reports the roadmap relies on against this vault and
keeps a dated snapshot, so each measurement day is one command and the
results can be compared over time:

- capture: the capture gap audit gate (steps 1-3) since ``since``
- review_noise: review candidates created since ``since`` by reason (step 4)
- staleness: the current stale_candidate scan (step 6)
- bootstrap: old vs distinct SessionStart slots per project (step 9)

Nothing canonical is written; the snapshot goes to
``runtime/measurements/<timestamp>.json`` and holds counts and ids only.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

from .storage import RuntimeConfig, read_json, write_json, now

_SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'


def _scripts():
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))


def default_since(vault):
    """The last native install time: measurements start where the current code started."""
    manifest = read_json(RuntimeConfig(vault).root / 'installation.json', {}) or {}
    times = [c.get('installed_at') for c in (manifest.get('clients') or {}).values() if isinstance(c, dict)]
    times = [t for t in times if isinstance(t, str) and t]
    return max(times) if times else None


def _review_since(vault, since):
    from .review import ReviewStore
    by_reason, by_status = Counter(), Counter()
    for item in ReviewStore(vault)._items():
        if not isinstance(item, dict) or (since and str(item.get('created_at', '')) < since):
            continue
        by_reason[str(item.get('reason'))] += 1
        by_status[str(item.get('status'))] += 1
    return {'created_since': dict(by_reason), 'status': dict(by_status), 'total': sum(by_reason.values())}


def measure(vault, *, since=None, claude_home=None, codex_home=None, save=True):
    _scripts()
    from capture_gap_audit import _parse_since, audit, verdict
    from bootstrap_selectivity_report import compare
    from .staleness import scan

    since = since or default_since(vault)
    home = Path.home()
    capture = audit(Path(vault), Path(claude_home or home / '.claude'), since=_parse_since(since),
                    codex_home=Path(codex_home or home / '.codex'), clients=('claude', 'codex'))
    capture['verdict'] = verdict(capture, min_projects=2, min_sessions=20,
                                 require_clients=('claude', 'codex'), min_client_sessions=5)
    stale = scan(vault)
    result = {
        'measured_at': now(), 'since': since,
        'capture': {key: capture[key] for key in ('verdict', 'totals', 'clients', 'dead_letter_error_codes',
                                                  'bootstrap_receipts', 'projects_with_sessions')},
        'review_noise': _review_since(vault, since),
        'staleness': {'references_checked': stale['references_checked'],
                      'stale_candidates': len(stale['stale_candidates'])},
        'bootstrap': compare(vault),
    }
    if save:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        path = RuntimeConfig(vault).root / 'measurements' / f'{stamp}.json'
        write_json(path, result)
        result['saved_to'] = str(path)
    return result
