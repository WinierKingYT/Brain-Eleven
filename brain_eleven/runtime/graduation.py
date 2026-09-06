"""Recomputed live gates. A hand-edited PASS flag never enables ACTIVE."""
import hashlib
import math
from .storage import RuntimeConfig, read_json, write_json, now


def _p95(values):
    return sorted(values)[max(0, math.ceil(len(values) * .95) - 1)] if values else None


def evaluate(vault, labels, quality):
    from evals.runtime_eval import implementation_fingerprint
    cfg = RuntimeConfig(vault)
    if labels.get('schema_version') != 1 or labels.get('label_source') != 'human_independent' or not labels.get('labeler'):
        raise ValueError('Independent human labels and labeler identity are required')
    rows = labels.get('tasks', [])
    if not isinstance(rows, list):
        raise ValueError('Task labels must be an array')
    selected_count = relevant = required_count = covered = forbidden = 0
    v1_selected = v1_relevant = v1_covered = 0
    sessions, turns, clients = set(), set(), set()
    delays, hook_delays, projects = [], [], set()
    for row in rows:
        key = row.get('delivery_id', '')
        import re
        if not re.fullmatch(r'delivery_[a-f0-9]{64}', key) or key in turns:
            raise ValueError('Invalid or duplicate live delivery identity')
        observation = read_json(cfg.root / 'deliveries' / (key + '.json'))
        if not observation or not row.get('confirmed_real_turn') or observation.get('status') != 'EMITTED':
            raise ValueError('Each labeled turn needs an emitted native observation and human confirmation')
        if observation.get('implementation_fingerprint') != implementation_fingerprint():
            raise ValueError('Live observations were made against another implementation')
        for field in ('required', 'useful', 'forbidden'):
            if not isinstance(row.get(field), list) or not all(isinstance(x, str) for x in row[field]):
                raise ValueError('Invalid context labels')
        required_ids, useful_ids, forbidden_ids = set(row['required']), set(row['useful']), set(row['forbidden'])
        if (required_ids | useful_ids) & forbidden_ids:
            raise ValueError('Contradictory labels')
        selected, v1 = set(observation['selected_ids']), set(observation['v1_ids'])
        selected_count += len(selected)
        relevant += len(selected & (required_ids | useful_ids))
        required_count += len(required_ids)
        covered += len(selected & required_ids)
        forbidden += len(selected & forbidden_ids)
        v1_selected += len(v1)
        v1_relevant += len(v1 & (required_ids | useful_ids))
        v1_covered += len(v1 & required_ids)
        sessions.add(observation['session_hash'])
        clients.add(observation['client'])
        projects.add(observation['project_id'])
        turns.add(key)
        delays.append(observation['context_elapsed_ms'])
        hook_delays.append(observation['hook_elapsed_ms'])
    auto = {path.stem: read_json(path) for path in (cfg.root / 'capture-observations').glob('op_*.json')}
    capture_labels = labels.get('captures', [])
    captures = {item['operation_id']: item['correct'] for item in capture_labels}
    if len(captures) != len(capture_labels) or any(type(x) is not bool for x in captures.values()):
        raise ValueError('Capture labels must be unique booleans')
    precision = relevant / selected_count if selected_count else 0
    recall = covered / required_count if required_count else 0
    capture_precision = sum(captures.values()) / len(captures) if captures else 0
    gates = {
        'current_holdout_quality': quality.get('evidence_type') == 'SYNTHETIC_LABELED' and quality.get('suite') == 'holdout'
             and quality.get('implementation_fingerprint') == implementation_fingerprint() and bool(quality.get('gates')) and all(quality['gates'].values()),
        'twenty_real_turns':len(turns) >= 20, 'five_sessions':len(sessions) >= 5,
        'forty_independent_tasks':len(rows) >= 40, 'both_clients_observed':clients == {'claude','codex'},
        'canary_scope_only':bool(projects) and projects <= set(cfg.load()['project_ids']),
        'precision_70':precision >= .70, 'required_recall_80':recall >= .80, 'no_forbidden':forbidden == 0,
        'no_human_reported_leaks':labels.get('project_leaks') == 0 and labels.get('lifecycle_leaks') == 0,
        'v1_nonregression':precision >= (v1_relevant / v1_selected if v1_selected else 0) and recall >= (v1_covered / required_count if required_count else 0),
        'capture_labels_complete':bool(auto) and set(captures) == set(auto), 'capture_precision_98':capture_precision >= .98,
        'hook_p95_500ms':bool(hook_delays) and _p95(hook_delays) <= 500,
        'context_p95_2s':bool(delays) and _p95(delays) <= 2000,
        'no_dead_letters':not any((cfg.vault / '.brain-eleven/capture/dead-letter').glob('*.json')),
    }
    return {'schema_version':1, 'status':'PASS' if all(gates.values()) else 'PENDING_REAL_USE', 'gates':gates,
            'checked_at':now(), 'implementation_fingerprint':implementation_fingerprint(), 'real_turns':len(turns),
            'sessions':len(sessions), 'precision':precision, 'required_recall':recall, 'capture_precision':capture_precision}


def record(vault, labels_path, quality_path):
    labels, quality = read_json(labels_path), read_json(quality_path)
    result = evaluate(vault, labels, quality)
    root = RuntimeConfig(vault).root
    # Inputs are independently labeled IDs/booleans, never prompts/transcripts.
    write_json(root / 'graduation-input.json', {'labels':labels, 'quality':quality})
    write_json(root / 'graduation.json', result)
    return result


def verify(vault):
    data = read_json(RuntimeConfig(vault).root / 'graduation-input.json')
    if not data:
        raise ValueError('Independent live graduation evidence required')
    # Re-execute the frozen labeled suite; a forged report is not evidence.
    from evals.runtime_eval import run
    result = evaluate(vault, data['labels'], run('holdout'))
    if result['status'] != 'PASS':
        raise ValueError('Live graduation gates are not satisfied')
    return result
