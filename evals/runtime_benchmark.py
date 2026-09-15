"""Synthetic local process benchmark; never emits live graduation evidence."""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from collections import Counter

from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.state import StateService
from brain_eleven.runtime.migration import migrate
from brain_eleven.runtime.storage import RuntimeConfig, read_json, write_json
from brain_eleven.runtime.launcher import ensure_service, request_service
from evals.fixture_generator import make_memory
from evals.schema import FixtureMemory
from evals.runtime_eval import implementation_fingerprint


def p95(values):
    return round(sorted(values)[math.ceil(len(values) * .95) - 1], 2)


def _hook_status(stdout, returncode, *, event):
    """Map launcher output to bounded benchmark status without persisting it."""
    try:
        payload = json.loads(stdout)
    except (TypeError, ValueError):
        return 'INVALID_OUTPUT'
    if returncode != 0:
        return 'NONZERO_EXIT'
    if not isinstance(payload, dict):
        return 'INVALID_OUTPUT'
    if event == 'Stop':
        return 'OK' if payload == {} else 'DEGRADED'
    return 'OK' if 'hookSpecificOutput' in payload else 'DEGRADED'


def run(samples=40, records=1000):
    if samples < 20 or records < 1000:
        raise ValueError('At least 20 events and 1000 records are required')
    with TemporaryDirectory(prefix='brain-runtime-perf-') as temporary:
        vault = Path(temporary) / 'vault'
        vault.mkdir()
        project = ProjectRegistry(vault).register(vault, proactive_capture=True)['project_id']
        StateService(vault).init_project(project, source={'type': 'user', 'reference': 'synthetic-benchmark'})
        store = MemoryStore(vault)
        document = store.load()
        document['validated_memory'] = [make_memory(FixtureMemory(
            memory_id=f'noise_{index}', memory_type='observation', status='active',
            content=f'Synthetic unrelated inventory observation {index}.', scope='project', project_id=project),
            seed=0, index=index, quality=.5) for index in range(records)]
        store.replace(document)
        migrate(vault)
        baseline_document = store.load()
        baseline_memory_count = len(baseline_document.get('validated_memory', []))
        baseline_revision = store.revision()
        cfg = RuntimeConfig(vault)
        # This disposable synthetic vault bypasses rollout only to exercise the
        # implementation. The production promotion command still enforces gates.
        # The synthetic transcript files below live outside the host native
        # roots.  Bind both clients explicitly to this disposable directory
        # so the benchmark exercises the queue path instead of failing at the
        # provenance boundary before any timing is measured.
        claude_root = Path(temporary) / 'claude-projects'
        codex_root = Path(temporary) / 'codex-sessions'
        claude_slug = str(vault.resolve()).replace(':', '-').replace('/', '-').replace('\\', '-')
        claude_project_root = claude_root / claude_slug
        claude_project_root.mkdir(parents=True)
        codex_root.mkdir(parents=True)
        write_json(cfg.path, {
            'schema_version': 1,
            'mode': 'CANARY',
            'project_ids': [project],
            'local_model': None,
            'transcript_roots': {'claude': [str(claude_root.resolve())], 'codex': [str(codex_root.resolve())]},
        })
        start = time.perf_counter()
        if not ensure_service(vault, wait=True):
            raise RuntimeError('Synthetic service did not start')
        cold_ms = (time.perf_counter() - start) * 1000
        launcher = Path(__file__).resolve().parents[1] / 'brain_eleven/runtime/launcher.py'
        stop_ms, prompt_ms = [], []
        stop_status, prompt_status = [], []
        try:
            first_service = read_json(cfg.root / 'service.json')
            assert ensure_service(vault, wait=True)
            singleton = read_json(cfg.root / 'service.json') == first_service
            for index in range(samples):
                client = 'claude' if index % 2 == 0 else 'codex'
                raw_session = f'benchmark-{index}'
                path = (claude_project_root if client == 'claude' else codex_root) / f'{raw_session}.jsonl'
                message = {'role': 'user', 'content': f'We decided to use SQLite for persistent storage in component {index}.'}
                if client == 'claude':
                    event = {'sessionId': raw_session, 'type': 'user', 'message': message}
                else:
                    event = {'type': 'session_meta', 'payload': {'session_id': raw_session, 'cwd': str(vault)}}
                    message = {'type': 'response_item', 'payload': {'type': 'message', **message}}
                path.write_text(json.dumps(event) + '\n' + (json.dumps(message) + '\n' if client == 'codex' else ''), encoding='utf-8')
                payload = {'cwd': str(vault), 'session_id': raw_session, 'transcript_path': str(path)}
                command = [sys.executable, str(launcher), '--vault', str(vault), '--client', client, '--event', 'Stop']
                start = time.perf_counter()
                result = subprocess.run(command, input=json.dumps(payload), text=True, encoding='utf-8', capture_output=True, timeout=5,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                stop_ms.append((time.perf_counter() - start) * 1000)
                stop_status.append(_hook_status(result.stdout, result.returncode, event='Stop'))
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                try:
                    status = request_service(vault, '/api/runtime/status', timeout=5)
                except (OSError, TimeoutError, ValueError):
                    status = None
                if status and not status['queue']['queued'] and not status['queue']['processing']:
                    break
                time.sleep(.05)
            capture_root = vault / '.brain-eleven/capture'
            from datetime import datetime
            latencies = []
            for path in (capture_root / 'completed').glob('*.json'):
                job = read_json(path)
                latencies.append((datetime.fromisoformat(job['committed_at']) - datetime.fromisoformat(job['created_at'])).total_seconds() * 1000)
            final_document = store.load()
            final_memory_count = len(final_document.get('validated_memory', []))
            final_revision = store.revision()
            canonical_effects = final_memory_count - baseline_memory_count
            canonical_revision_delta = final_revision - baseline_revision
            canonical_effect_verified = (
                canonical_effects == samples and canonical_revision_delta >= samples
            )
            for index in range(samples):
                payload = {'cwd': str(vault), 'session_id': 'benchmark-prompts', 'turn_id': str(index),
                           'prompt': 'Which database did we decide to use for persistent storage?'}
                client = 'claude' if index % 2 == 0 else 'codex'
                start = time.perf_counter()
                result = subprocess.run([sys.executable, str(launcher), '--vault', str(vault), '--client', client, '--event', 'UserPromptSubmit'],
                    input=json.dumps(payload), text=True, encoding='utf-8', capture_output=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                prompt_ms.append((time.perf_counter() - start) * 1000)
                prompt_status.append(_hook_status(result.stdout, result.returncode, event='UserPromptSubmit'))
            report = {'schema_version': 1, 'evidence_type': 'SYNTHETIC_PROCESS_BENCHMARK',
                      'implementation_fingerprint': implementation_fingerprint(), 'platform': sys.platform,
                      'records': records, 'samples_per_event': samples, 'cold_start_ms': round(cold_ms, 2),
                      'stop_hook_p95_ms': p95(stop_ms), 'prompt_hook_p95_ms': p95(prompt_ms),
                      'queue_p95_ms': p95(latencies) if latencies else None, 'queue_max_ms': round(max(latencies), 2) if latencies else None,
                      'completed': len(latencies), 'canonical_effects': canonical_effects,
                      'canonical_revision_delta': canonical_revision_delta,
                      'canonical_effect_verified': canonical_effect_verified,
                      'singleton': singleton,
                      'stop_status_counts': dict(sorted(Counter(stop_status).items())),
                      'prompt_status_counts': dict(sorted(Counter(prompt_status).items()))}
            all_hooks_ok = all(status == 'OK' for status in stop_status + prompt_status)
            report['gates'] = {'hook_p95_500ms': max(p95(stop_ms), p95(prompt_ms)) <= 500,
                               'queue_30s': len(latencies) == samples and max(latencies) <= 30000,
                               'all_hooks_ok': all_hooks_ok,
                               'canonical_effect_verified': canonical_effect_verified,
                               'no_dead_letters': not any((capture_root / 'dead-letter').glob('*.json')), 'singleton': singleton}
            report['status'] = 'PASS' if all(report['gates'].values()) else 'FAIL'
            return report
        finally:
            request_service(vault, '/api/runtime/stop', {}, timeout=2)
            deadline = time.monotonic() + 8
            while (cfg.root / 'service.json').exists() and time.monotonic() < deadline:
                time.sleep(.1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    write_json(args.report, report)
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
