"""Local runtime CLI. Canonical changes require explicit commands or opt-in."""
import argparse
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m brain_eleven')
    parser.add_argument('--vault', default=str(Path(__file__).resolve().parents[1]))
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('install', 'uninstall', 'doctor', 'serve', 'status'):
        sub.add_parser(name)
    worker = sub.add_parser('worker')
    worker_mode = worker.add_mutually_exclusive_group(required=True)
    worker_mode.add_argument('--once', action='store_true')
    worker_mode.add_argument('--retry-dead-letter', nargs='*', metavar='ERROR_CODE',
                             help='requeue dead-lettered captures (default: fixed transcript-read codes)')
    context = sub.add_parser('context')
    context.add_argument('request')
    context.add_argument('--project-root', default='.')
    review = sub.add_parser('review')
    review.add_argument('--no-open', action='store_true')
    rollout = sub.add_parser('rollout')
    rollout.add_argument('mode', choices=['OFF', 'SHADOW', 'CANARY', 'ACTIVE'])
    approval = sub.add_parser('approval')
    approval.add_argument('state', choices=['OFF', 'ON'])
    shadow_accept = sub.add_parser('shadow-accept')
    shadow_accept.add_argument('state', choices=['OFF', 'ON'])
    migration = sub.add_parser('migration')
    migration.add_argument('action', choices=['upgrade', 'rollback'])
    recall = sub.add_parser('recall-probe', help="automated owner recall test: is each answer in today's SessionStart context?")
    recall.add_argument('--project-root', default=None)
    explain = sub.add_parser('bootstrap-explain', help='why each active memory is or is not in the SessionStart context')
    explain.add_argument('--project-root', default=None)
    measure = sub.add_parser('measure', help='real-use measurement snapshot (capture, review noise, staleness, bootstrap)')
    measure.add_argument('--since', help='ISO time; default: last native install')
    graduation = sub.add_parser('graduation')
    graduation.add_argument('--labels', required=True)
    graduation.add_argument('--quality-report', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in {'install', 'uninstall', 'doctor'}:
            from .runtime import install
            result = getattr(install, args.command)(args.vault)
        elif args.command in {'serve', 'status'}:
            from .runtime.service import serve, runtime_status
            result = serve(args.vault) if args.command == 'serve' else runtime_status(args.vault)
        elif args.command == 'worker':
            from .runtime.worker import Worker, RETRYABLE_DEAD_LETTER_CODES
            if args.retry_dead_letter is not None:
                from .runtime.capture_queue import CaptureQueue
                codes = args.retry_dead_letter or sorted(RETRYABLE_DEAD_LETTER_CODES)
                result = {'requeued': CaptureQueue(args.vault).requeue_dead_letters(codes), 'error_codes': codes}
            else:
                result = Worker(args.vault).once()
        elif args.command == 'context':
            from .runtime.context import compile_context
            result = compile_context(args.vault, args.project_root, args.request)
        elif args.command == 'rollout':
            from .runtime.storage import RuntimeConfig
            result = RuntimeConfig(args.vault).set_mode(args.mode)
        elif args.command == 'approval':
            from .runtime.storage import RuntimeConfig
            result = RuntimeConfig(args.vault).set_human_approval(args.state == 'ON')
        elif args.command == 'shadow-accept':
            from .runtime.storage import RuntimeConfig
            result = RuntimeConfig(args.vault).set_shadow_accept(args.state == 'ON')
        elif args.command == 'migration':
            from .runtime.migration import migrate, rollback
            result = migrate(args.vault) if args.action == 'upgrade' else rollback(args.vault)
        elif args.command == 'recall-probe':
            from .runtime.recall_probe import probe
            result = probe(args.vault, args.project_root)
        elif args.command == 'bootstrap-explain':
            from .runtime.context import explain_bootstrap
            result = explain_bootstrap(args.vault, args.project_root or args.vault)
        elif args.command == 'measure':
            from .runtime.measure import measure as run_measure
            result = run_measure(args.vault, since=args.since)
        elif args.command == 'graduation':
            from .runtime.graduation import record
            result = record(args.vault, args.labels, args.quality_report)
        elif args.command == 'review':
            from .runtime.launcher import ensure_service
            from .runtime.storage import RuntimeConfig, read_json
            if not ensure_service(args.vault, wait=True):
                raise ValueError('Local service unavailable; check doctor and rollout mode')
            service = read_json(RuntimeConfig(args.vault).root / 'service.json')
            url = 'http://127.0.0.1:' + str(service['port']) + '/review#token=' + service['token']
            if not args.no_open:
                import webbrowser
                webbrowser.open(url)
            result = {'url': url}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == 'doctor' and result.get('status') != 'READY':
            return 1
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({'status': 'FAILED', 'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
