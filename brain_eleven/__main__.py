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
    shadow_recall = sub.add_parser('shadow-recall', help='deliver V1 per-prompt memory while staying in SHADOW (owner opt-in)')
    shadow_recall.add_argument('state', choices=['OFF', 'ON'])
    migration = sub.add_parser('migration')
    migration.add_argument('action', choices=['upgrade', 'rollback'])
    recall = sub.add_parser('recall-probe', help="automated owner recall test against bootstrap or prompt-time context")
    recall.add_argument('--project-root', default=None)
    recall.add_argument('--questions', default=None,
                        help='local questions file (same format); default: the owner five in evals/recall_probe')
    recall.add_argument('--mode', choices=['bootstrap', 'prompt'], default='bootstrap',
                        help='context path to measure (default: bootstrap)')
    explain = sub.add_parser('bootstrap-explain', help='why each active memory is or is not in the SessionStart context')
    explain.add_argument('--project-root', default=None)
    measure = sub.add_parser('measure', help='real-use measurement snapshot (capture, review noise, staleness, bootstrap)')
    measure.add_argument('--since', help='ISO time; default: last native install')
    backfill = sub.add_parser('backfill', help='re-run the current extractor on recent transcripts; review queue only')
    backfill.add_argument('--days', type=int, default=14)
    backfill.add_argument('--apply', action='store_true', help='add to the review queue (default: count only)')
    backfill.add_argument('--reoffer-expired', action='store_true',
                          help='offer candidates whose 7 days ran out without a decision again')
    triage = sub.add_parser('triage', help='apply the automatic noise filter to pending review candidates')
    triage.add_argument('--apply', action='store_true', help='reject matches with a note (default: count only)')
    sub.add_parser('digest', help="the day's most valuable review candidates")
    applier = sub.add_parser('apply-suggestions', help="apply the model's review verdicts (ACCEPT writes, REJECT hides)")
    applier.add_argument('--apply', action='store_true', help='write accepts (default: count only)')
    auto = sub.add_parser('queue-triage', help='pre-evaluate the review queue: rules reject noise, a local model decides the rest')
    auto.add_argument('state', nargs='?', choices=['OFF', 'ON'], help='turn the service schedule on/off (default: run once)')
    auto.add_argument('--no-model', action='store_true', help='rules only')
    auto.add_argument('--limit', type=int, help='at most this many model calls')
    auto.add_argument('--apply', action='store_true', help='also apply the verdicts (ACCEPT writes, REJECT hides)')
    auto.add_argument('--accept-model', action='store_true', help='for this run, write VERIFIED candidates even if auto_accept_verified is off')
    auto.add_argument('--accept-verified', choices=['OFF', 'ON'], help='turn automatic writing of VERIFIED candidates on/off')
    audit = sub.add_parser('memory-audit', help='weekly memory audit: retire guarded exact duplicates, suggest the rest')
    audit.add_argument('state', nargs='?', choices=['OFF', 'ON'], help='turn the weekly service run on/off (default: run once, dry)')
    audit.add_argument('--apply', action='store_true', help='retire guarded exact duplicates (default: report only)')
    audit.add_argument('--no-model', action='store_true', help='skip the local-model duplicate/conflict check')
    probation = sub.add_parser('probation', help='re-check memories written without a person (rules retire, model flags)')
    probation.add_argument('state', nargs='?', choices=['OFF', 'ON'], help='turn the service run on/off (default: run once, dry)')
    probation.add_argument('--apply', action='store_true', help='retire rule hits and record verdicts (default: report only)')
    project_cmd = sub.add_parser('project', help='enroll a project folder for memory capture')
    project_cmd.add_argument('action', choices=['add'])
    project_cmd.add_argument('root')
    project_cmd.add_argument('--label')
    cross = sub.add_parser('cross-project', help="prompts also get other projects' relevant decisions/lessons as references")
    cross.add_argument('state', choices=['OFF', 'ON'])
    cross.add_argument('--private', nargs='*', metavar='PROJECT', help='project labels or ids never shared with other projects')
    retire_cmd = sub.add_parser('retire', help='retire memories by id (status resolved; nothing is deleted)')
    retire_cmd.add_argument('memory_ids', nargs='+')
    retire_cmd.add_argument('--note', default='Sahip: yanlış veya gereksiz kayıt.')
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
        elif args.command == 'shadow-recall':
            from .runtime.storage import RuntimeConfig
            result = RuntimeConfig(args.vault).set_shadow_recall(args.state == 'ON')
        elif args.command == 'migration':
            from .runtime.migration import migrate, rollback
            result = migrate(args.vault) if args.action == 'upgrade' else rollback(args.vault)
        elif args.command == 'recall-probe':
            from .runtime.recall_probe import probe
            result = probe(args.vault, args.project_root, questions_path=args.questions, mode=args.mode)
        elif args.command == 'bootstrap-explain':
            from .runtime.context import explain_bootstrap
            result = explain_bootstrap(args.vault, args.project_root or args.vault)
        elif args.command == 'measure':
            from .runtime.measure import measure as run_measure
            result = run_measure(args.vault, since=args.since)
        elif args.command == 'backfill':
            from .runtime.backfill import backfill as run_backfill
            result = run_backfill(args.vault, days=args.days, apply=args.apply,
                                  reoffer_expired=args.reoffer_expired)
        elif args.command == 'triage':
            from .runtime.triage import triage_existing
            result = triage_existing(args.vault, apply=args.apply)
        elif args.command == 'apply-suggestions':
            from .runtime.value import apply_suggestions
            result = apply_suggestions(args.vault, apply=args.apply)
        elif args.command == 'queue-triage':
            if args.accept_verified:
                from .runtime.storage import RuntimeConfig
                result = RuntimeConfig(args.vault).set_auto_accept_verified(args.accept_verified == 'ON')
            elif args.state:
                from .runtime.storage import RuntimeConfig
                result = RuntimeConfig(args.vault).set_queue_triage(args.state == 'ON')
            else:
                from .runtime.queue_triage import triage
                from .runtime.value import apply_suggestions
                from .runtime.storage import RuntimeConfig
                accept = args.accept_model or bool(RuntimeConfig(args.vault).load().get('auto_accept_verified'))
                result = {'triage': triage(args.vault, use_model=not args.no_model, limit=args.limit,
                                          accept_verified=accept)}
                if args.apply:
                    result['applied'] = apply_suggestions(args.vault, apply=True)
        elif args.command == 'memory-audit':
            if args.state:
                from .runtime.storage import RuntimeConfig
                result = RuntimeConfig(args.vault).set_memory_audit(args.state == 'ON')
            else:
                from .runtime.memory_audit import audit
                result = audit(args.vault, apply=args.apply, use_model=not args.no_model)
        elif args.command == 'probation':
            if args.state:
                from .runtime.storage import RuntimeConfig
                result = RuntimeConfig(args.vault).set_probation_review(args.state == 'ON')
            else:
                from .runtime.probation import review as probation_review
                result = probation_review(args.vault, apply=args.apply)
        elif args.command == 'project':
            from .runtime.storage import RuntimeConfig
            result = RuntimeConfig(args.vault).enroll_project(args.root, label=args.label)
        elif args.command == 'cross-project':
            from .runtime.storage import RuntimeConfig
            private = None
            if args.private is not None:
                from .projects.registry import ProjectRegistry
                known = {p['project_id']: p for p in ProjectRegistry(args.vault).list_projects()}
                by_label = {str(p.get('project_label') or ''): pid for pid, p in known.items()}
                private = []
                for name in args.private:
                    if name not in known and name not in by_label:
                        raise ValueError(f'Unknown project: {name}')
                    private.append(name if name in known else by_label[name])
            result = RuntimeConfig(args.vault).set_cross_project_recall(args.state == 'ON', private=private)
        elif args.command == 'retire':
            from .runtime.staleness import retire
            result = {'retired': [], 'failed': {}}
            for memory_id in args.memory_ids:
                try:
                    retire(args.vault, memory_id, args.note, resolved_by='owner')
                    result['retired'].append(memory_id)
                except ValueError as exc:
                    result['failed'][memory_id] = str(exc)[:120]
        elif args.command == 'digest':
            from .runtime.value import digest
            result = digest(args.vault)
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
        if args.command == 'retire' and result.get('failed'):
            return 1
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({'status': 'FAILED', 'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
