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
    worker.add_argument('--once', action='store_true', required=True)
    context = sub.add_parser('context')
    context.add_argument('request')
    context.add_argument('--project-root', default='.')
    review = sub.add_parser('review')
    review.add_argument('--no-open', action='store_true')
    rollout = sub.add_parser('rollout')
    rollout.add_argument('mode', choices=['OFF', 'SHADOW', 'CANARY', 'ACTIVE'])
    migration = sub.add_parser('migration')
    migration.add_argument('action', choices=['upgrade', 'rollback'])
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
            from .runtime.worker import Worker
            result = Worker(args.vault).once()
        elif args.command == 'context':
            from .runtime.context import compile_context
            result = compile_context(args.vault, args.project_root, args.request)
        elif args.command == 'rollout':
            from .runtime.storage import RuntimeConfig
            result = RuntimeConfig(args.vault).set_mode(args.mode)
        elif args.command == 'migration':
            from .runtime.migration import migrate, rollback
            result = migrate(args.vault) if args.action == 'upgrade' else rollback(args.vault)
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
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({'status': 'FAILED', 'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
