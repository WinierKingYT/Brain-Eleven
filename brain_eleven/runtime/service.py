"""Loopback-only review API and single local worker lifecycle."""
import asyncio
from contextlib import asynccontextmanager
import hmac
import os
from pathlib import Path
import secrets
import time
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from .storage import RuntimeConfig, canonical_accept_allowed, read_json, write_json, identity, now, runtime_file_lock as file_lock


def apply_candidate(*args, **kwargs):
    """Keep the review seam patchable without importing the worker on startup."""
    from .worker import apply_candidate as implementation
    return implementation(*args, **kwargs)


SUGGEST_KEY_SIMILARITY = 0.25


ACCEPT_MANY_MAX = 10


def accept_many_reviews(vault, ids):
    """Accept several candidates as shown, one by one with a fresh revision each.

    The person clicked one button for the day's top list; every item still goes
    through the same ``review_action`` path (safety, CAS, audit) as a single
    accept. A failure on one item is reported and the rest continue.
    """
    from brain_eleven.memory import MemoryStore
    from brain_eleven.state import StateStore
    from .review import ReviewStore
    results = {}
    for review_id in ids:
        try:
            item = read_json(ReviewStore(vault).path(review_id)) or {}
            candidate = item.get('candidate') or {}
            if candidate.get('candidate_type') == 'STATE_MUTATION':
                revision = StateStore(vault).project_revision(candidate.get('project_id'))
            else:
                revision = MemoryStore(vault).load()['revision']
            result = review_action(vault, review_id, 'accept', {'expected_revision': revision})
            results[review_id] = result.get('status') if isinstance(result, dict) else 'UNKNOWN'
        except ValueError as exc:
            results[review_id] = 'FAILED: ' + str(exc)[:120]
    accepted = sum(1 for status in results.values() if status == 'ACCEPTED')
    return {'accepted': accepted, 'results': results}


def review_action(vault, review_id, action, payload):
    from .review import DECISION_NOTE_MAX, ReviewStore

    cfg = RuntimeConfig(vault)
    if action == 'accept' and not canonical_accept_allowed(cfg.load(), approved=True):
        raise ValueError('Enable canary, or shadow accept, before accepting canonical changes')
    store = ReviewStore(vault)
    store.expire()
    path = store.path(review_id)
    with file_lock(store.root / 'index'):
        requested = read_json(path)
        if requested is None:
            raise ValueError('Review candidate not found')
        if requested['status'] != 'PENDING':
            return requested
        # B2 hides duplicate pending records, but a stale/direct caller may
        # still address one by ID. Resolve it to the deterministic primary so
        # acceptance can never create a second canonical effect.
        item = store.primary(requested)
        primary_path = store.path(item['id'])
        with file_lock(primary_path):
            item = read_json(primary_path)
            if item is None:
                raise ValueError('Review candidate not found')
            if item['status'] != 'PENDING':
                return item
            note = payload.get('note')
            if note is not None:
                from .capture_safety import evaluate_capture
                from context_compiler_v2.safety import contains_secret
                if (not isinstance(note, str) or len(note) > DECISION_NOTE_MAX
                        or (note.strip() and (contains_secret(note) or not evaluate_capture(note).accepted))):
                    raise ValueError('Decision note must be at most 280 safe characters')
                if note.strip():
                    item['decision_note'] = note.strip()
            if action == 'reject':
                return store.finish(item, 'REJECTED')
            if action != 'accept':
                raise ValueError('Unknown review action')
            candidate = dict(item['candidate'])
            if 'content' in payload:
                if not isinstance(payload['content'], str) or not 3 <= len(payload['content']) <= 8000:
                    raise ValueError('Candidate text must be 3..8000 characters')
                candidate['text' if candidate['candidate_type'] == 'STATE_MUTATION' else 'content'] = payload['content']
            if 'claim_key' in payload:
                # MEMCLAIM-01: the reviewing person names the topic; a model never does.
                from brain_eleven.memory.truth import normalize_claim_key

                claim_key = normalize_claim_key(payload['claim_key'])
                if claim_key is None:
                    raise ValueError('claim_key must look like topic.attribute (lowercase, at most 80 characters)')
                candidate['claim_key'] = claim_key
            candidate['commitment'] = 'COMMITTED'
            expected = payload.get('expected_revision')
            if isinstance(expected, bool) or not isinstance(expected, int):
                raise ValueError('Expected revision required')
            # The request identity is durable before canonical write. A crash cannot
            # replay a changed edit under the old operation receipt.
            intent = {'candidate': candidate, 'target_id': payload.get('target_id'), 'expected_revision': expected}
            if 'accept_intent' in item and item['accept_intent'] != intent:
                raise ValueError('A different acceptance is already pending recovery')
            item['accept_intent'] = intent
            write_json(primary_path, item)
            result = apply_candidate(vault, candidate, op_id=identity('op_', item['id']), approved=True,
                                     target_id=intent['target_id'], expected_revision=expected)
            if result['status'] == 'SUCCESS':
                decisions = result.get('decisions', [])
                if any(x.get('action') in {'REJECT', 'REVIEW_REQUIRED', 'CONFLICT'} for x in decisions):
                    raise ValueError('Candidate still requires review')
                return store.finish(item, 'ACCEPTED', result)
            if result['status'] in {'STALE_INPUT', 'REVIEW_REQUIRED', 'SCOPE_ERROR', 'REJECTED', 'DEGRADED'}:
                item.pop('accept_intent', None)
                write_json(primary_path, item)
            conflict = _claim_conflict(vault, result)
            return {**result, 'conflict': conflict} if conflict else result


def _claim_conflict(vault, result):
    """Describe the active memory a same-claim_key acceptance collided with."""
    from brain_eleven.memory import MemoryStore
    from .capture_safety import evaluate_capture
    from context_compiler_v2.safety import contains_secret

    target = next((x.get('target_memory_id') for x in result.get('decisions', [])
                   if x.get('action') == 'CONFLICT' and x.get('reason_code') == 'ACTIVE_CLAIM_KEY_CONFLICT'), None)
    if not target:
        return None
    memory = next((x for x in MemoryStore(vault).load()['validated_memory'] if x.get('memory_id') == target), None)
    if memory is None:
        return None
    content = memory.get('content', '')
    safe = isinstance(content, str) and evaluate_capture(content).accepted and not contains_secret(content)
    return {'memory_id': target, 'claim_key': memory.get('claim_key', ''), 'content': content if safe else '',
            'occurred_at': memory.get('occurred_at', ''), 'timestamp': memory.get('timestamp', '')}


def _prompt_providers_state():
    """'ready', 'loading', or 'unavailable' (loaded, but no real model: V1 order)."""
    try:
        from .context import _PROVIDER_CACHE, _PROVIDER_LOCK, prompt_providers_loaded
        if not _PROVIDER_LOCK.acquire(blocking=False):
            return 'loading'
        try:
            settled = bool(list(_PROVIDER_CACHE.values()))
        finally:
            _PROVIDER_LOCK.release()
        if prompt_providers_loaded():
            return 'ready'
        return 'unavailable' if settled else 'loading'
    except Exception:
        return 'loading'


def _prompt_providers_ready():
    """True when prompt-time models are loaded and no warm-up holds them."""
    return _prompt_providers_state() == 'ready'


def runtime_status(vault):
    cfg = RuntimeConfig(vault)
    capture = Path(vault) / '.brain-eleven' / 'capture'
    config = cfg.load()
    return {'mode': config['mode'], 'shadow_accept': config['shadow_accept'], 'shadow_recall': config['shadow_recall'], 'queue': {name: len(list((capture / name).glob('*.json'))) for name in ('queued', 'processing', 'completed', 'dead-letter')},
            'worker': read_json(cfg.root / 'last-worker.json'), 'context': read_json(cfg.root / 'last-context.json'),
            'model': read_json(cfg.root / 'model-status.json'), 'graduation': read_json(cfg.root / 'graduation.json', {'status': 'PENDING_REAL_USE'}),
            **_prompt_status()}


def _prompt_status():
    state = _prompt_providers_state()
    return {'prompt_providers_ready': state == 'ready', 'prompt_providers_state': state}


def create_app(vault, *, token=None, background=True):
    cfg = RuntimeConfig(vault)
    token = token or secrets.token_urlsafe(32)
    async def worker_loop():
        from .worker import Worker

        while True:
            delay = 2
            try:
                result = await asyncio.to_thread(Worker(vault).once)
                maintenance_count = 0
                if result['status'] != 'OFF':
                    from .maintenance_delivery import process_pending, reconcile_completed
                    reconciled_count = await asyncio.to_thread(reconcile_completed, vault, limit=16)
                    maintenance_count = await asyncio.to_thread(process_pending, vault, limit=1)
                else:
                    reconciled_count = 0
                if result['status'] not in {'IDLE', 'OFF'}:
                    app.state.last_activity = time.monotonic()
                    delay = .05
                elif maintenance_count or reconciled_count:
                    app.state.last_activity = time.monotonic()
                    delay = .05
            except Exception:
                write_json(cfg.root / 'last-worker.json', {'at': now(), 'status': 'FAILED', 'error': 'WORKER_UNAVAILABLE'})
            await maybe_queue_triage(app)
            await maybe_memory_audit(app)
            if time.monotonic() - app.state.last_activity > idle_limit_seconds():
                app.state.idle = True
            await asyncio.sleep(delay)
    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(worker_loop()) if background else None
        yield
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.last_activity = time.monotonic()
    app.state.idle = False
    app.state.vault = vault
    app.state.queue_triage_running = False
    app.state.memory_audit_running = False
    app.state.queue_triage_at = float('-inf')
    app.state.token = token

    @app.middleware('http')
    async def local_access(request, call_next):
        host = request.headers.get('host', '')
        if host.split(':')[0] != '127.0.0.1':
            return JSONResponse({'error': 'LOCAL_HOST_REQUIRED'}, status_code=403)
        origin = request.headers.get('origin')
        if origin and origin != 'http://' + host:
            return JSONResponse({'error': 'ORIGIN_REJECTED'}, status_code=403)
        if request.url.path not in {'/health', '/review', '/review.js', '/review.css'}:
            supplied = request.headers.get('authorization', '').removeprefix('Bearer ')
            if not hmac.compare_digest(supplied, token):
                return JSONResponse({'error': 'LOCAL_SESSION_REQUIRED'}, status_code=401)
        app.state.last_activity = time.monotonic()
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    async def body(request):
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 32000:
                raise HTTPException(413, 'Request too large')
            chunks.append(chunk)
        import json
        try:
            value = json.loads(b''.join(chunks))
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except ValueError:
            raise HTTPException(400, 'Invalid request')

    @app.get('/health')
    def health():
        return {'status': 'ok', 'runtime_version': 1}

    @app.get('/review')
    def page():
        return HTMLResponse((Path(__file__).parent / 'ui' / 'index.html').read_text(encoding='utf-8'))

    @app.get('/review.js')
    def script():
        from fastapi.responses import Response
        return Response((Path(__file__).parent / 'ui' / 'review.js').read_text(encoding='utf-8'), media_type='application/javascript')

    @app.get('/review.css')
    def stylesheet():
        from fastapi.responses import Response
        return Response((Path(__file__).parent / 'ui' / 'review.css').read_text(encoding='utf-8'), media_type='text/css')

    @app.get('/api/runtime/status')
    def status():
        return runtime_status(vault)

    @app.post('/api/runtime/stop')
    def stop():
        app.state.idle = True
        return {'status': 'STOPPING'}

    @app.get('/api/review/candidates')
    def candidates():
        from brain_eleven.memory import MemoryStore
        from brain_eleven.state import StateStore
        from .capture_safety import evaluate_capture
        from .review import ReviewStore
        from context_compiler_v2.safety import contains_secret
        from brain_eleven.projects.registry import ProjectRegistry
        from .review import content_shape, rank_similar
        from .recall_probe import load_questions, pending_candidate_texts, review_tags
        from .value import DAILY_LIMIT, load_suggestions, value_score
        try:
            questions = load_questions()
        except (OSError, ValueError):
            questions = []
        items = ReviewStore(vault).list()
        memory = MemoryStore(vault).load()
        project_names = {p['project_id']: Path(str(p.get('root', ''))).name or p['project_id']
                         for p in ProjectRegistry(vault).list_projects()}
        state = StateStore(vault)
        # Recall tags per project: a candidate is tagged when it holds a recall
        # answer alone or as part of the smallest split that holds it.
        suggestions = load_suggestions(vault)
        tags = {}
        for project_id in {item.get('project_id') for item in items if item['status'] == 'PENDING'}:
            tags.update(review_tags(pending_candidate_texts(vault, project_id), questions))
        for item in items:
            if item['status'] == 'PENDING':
                c = item['candidate']
                item['expected_revision'] = state.project_revision(c['project_id']) if c['candidate_type'] == 'STATE_MUTATION' else memory['revision']
                item['project_name'] = project_names.get(c['project_id'], c['project_id'])
                item['recall_questions'] = tags.get(item['id'], [])
                text = c.get('text') if c['candidate_type'] == 'STATE_MUTATION' else c.get('content')
                item['shape'] = content_shape(text) if isinstance(text, str) else None
                if c['candidate_type'] == 'NEW_MEMORY':
                    active = [x for x in memory['validated_memory']
                              if x.get('project_id') == c['project_id'] and x.get('status') == 'active']
                    # Most similar first, so a likely duplicate or supersede target is on top.
                    ranked = rank_similar(c.get('content', ''), active)
                    targets = [{'id': x['memory_id'], 'text': x['content'], 'claim_key': x.get('claim_key', ''),
                                'similarity': score} for score, x in ranked]
                    item['similar'] = [t for t in targets if t['similarity'] > 0][:3]
                    # MEMCLAIM: a key is only ever suggested from a similar record the
                    # person can see; the person still decides whether to use it.
                    item['suggested_claim_keys'] = list(dict.fromkeys(
                        t['claim_key'] for t in targets if t['claim_key'] and t['similarity'] >= SUGGEST_KEY_SIMILARITY))[:3]
                    item['claim_keys'] = sorted({x['claim_key'] for x in active if x.get('claim_key')})
                else:
                    project = state.get_project(c['project_id']) or {}
                    bucket = {'RESOLVE_BLOCKER': 'blockers', 'RESOLVE_REQUIREMENT': 'requirements'}.get(c.get('operation'))
                    targets = [{'id': x['id'], 'text': x['text']} for x in project.get(bucket, []) if x.get('status') in {'ACTIVE', 'OPEN', 'PLANNED', 'IN_PROGRESS'}] if bucket else []
                item['targets'] = [x for x in targets if evaluate_capture(x['text']).accepted and not contains_secret(x['text'])]
                if 'similar' in item:
                    safe_ids = {x['id'] for x in item['targets']}
                    item['similar'] = [x for x in item['similar'] if x['id'] in safe_ids]
                item['value_score'] = value_score(item)
                if item['id'] in suggestions:
                    item['suggestion'] = suggestions[item['id']]
        return {'candidates': items, 'daily_limit': DAILY_LIMIT}

    @app.get('/api/staleness')
    def stale_memories():
        from .capture_safety import evaluate_capture
        from .staleness import scan
        from context_compiler_v2.safety import contains_secret
        result = scan(vault)
        result['stale_candidates'] = [x for x in result['stale_candidates']
                                      if evaluate_capture(x['content']).accepted and not contains_secret(x['content'])]
        return result

    @app.post('/api/staleness/{memory_id}/{action}')
    async def stale_action(memory_id: str, action: str, request: Request):
        from .staleness import acknowledge, retire
        payload = await body(request)
        try:
            if action == 'ack':
                return await asyncio.to_thread(acknowledge, vault, memory_id, str(payload.get('path', '')))
            if action == 'retire':
                if not canonical_accept_allowed(RuntimeConfig(vault).load(), approved=True):
                    raise ValueError('Enable canary, or shadow accept, before changing canonical memory')
                return await asyncio.to_thread(retire, vault, memory_id, str(payload.get('note', '')))
            raise ValueError('Unknown staleness action')
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/review/bulk-reject')
    async def bulk_reject(request: Request):
        from .review import ReviewStore, content_shape
        payload = await body(request)
        allowed_keys = {'reason', 'commitment', 'shape'}
        wanted = {k: v for k, v in payload.items() if k in allowed_keys and isinstance(v, str) and v}
        if not wanted:
            raise HTTPException(409, 'Choose at least one filter: reason, commitment or shape')

        def matches(item):
            c = item.get('candidate') if isinstance(item.get('candidate'), dict) else {}
            text = c.get('text') if c.get('candidate_type') == 'STATE_MUTATION' else c.get('content')
            values = {'reason': item.get('reason'), 'commitment': c.get('commitment'),
                      'shape': content_shape(text) if isinstance(text, str) else None}
            return all(values[k] == v for k, v in wanted.items())

        note = ('Toplu ret: ' + ', '.join(f'{k}={v}' for k, v in sorted(wanted.items())))[:280]
        dry_run = payload.get('confirm') is not True
        return await asyncio.to_thread(ReviewStore(vault).reject_matching, matches, note, dry_run=dry_run)

    @app.post('/api/review/accept-many')
    async def accept_many(request: Request):
        payload = await body(request)
        ids = payload.get('ids')
        if not isinstance(ids, list) or not ids or len(ids) > ACCEPT_MANY_MAX or not all(isinstance(x, str) for x in ids):
            raise HTTPException(409, f'Send 1-{ACCEPT_MANY_MAX} review ids')
        return await asyncio.to_thread(accept_many_reviews, vault, ids)

    @app.post('/api/review/candidates/{review_id}/extend')
    async def extend(review_id: str, request: Request):
        from .review import ReviewStore
        await body(request)
        try:
            return await asyncio.to_thread(ReviewStore(vault).extend, review_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/review/candidates/{review_id}/{action}')
    async def act(review_id: str, action: str, request: Request):
        payload = await body(request)
        try:
            result = await asyncio.to_thread(review_action, vault, review_id, action, payload)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return result

    @app.post('/api/context')
    async def context(request: Request):
        from .context import compile_context

        payload = await body(request)
        required = {'project_root', 'request', 'client', 'session', 'turn'}
        if set(payload) not in (required, required | {'event'}) or not all(isinstance(x, str) for x in payload.values()):
            raise HTTPException(400, 'Invalid context request')
        if payload.get('event', 'UserPromptSubmit') not in {'SessionStart', 'UserPromptSubmit'}:
            raise HTTPException(400, 'Invalid context event')
        try:
            return await asyncio.to_thread(compile_context, vault, payload['project_root'], payload['request'],
                                           client=payload['client'], session=payload['session'], turn=payload['turn'],
                                           event=payload.get('event', 'UserPromptSubmit'))
        except Exception:
            return {'status': 'FAILED', 'context': '', 'warnings': ['CONTEXT_UNAVAILABLE']}
    return app


QUEUE_TRIAGE_INTERVAL_SECONDS = 1800


async def maybe_queue_triage(app):
    """Owner decision 2026-09-30: pre-evaluate the review queue in the background.

    Runs at most every 30 minutes when ``queue_triage`` is on, one run at a time,
    off the event loop (the local model takes seconds per item). Rejects hide
    items; verified ones stay for a person unless auto_accept_verified is on.
    Never raises into the worker loop.
    """
    vault = app.state.vault
    try:
        config = RuntimeConfig(vault).load()
        if not (config.get('queue_triage') or config.get('probation_review')):
            return
    except Exception:
        return
    if app.state.queue_triage_running or time.monotonic() - app.state.queue_triage_at < QUEUE_TRIAGE_INTERVAL_SECONDS:
        return
    app.state.queue_triage_running = True
    app.state.queue_triage_at = time.monotonic()

    def run():
        from .queue_triage import triage
        try:
            config = RuntimeConfig(vault).load()
            accept = bool(config.get('auto_accept_verified'))
            result = {'at': now()}
            if config.get('queue_triage'):
                result.update(triage(vault, accept_verified=accept))
                if accept:
                    from .value import apply_suggestions
                    result['applied'] = apply_suggestions(vault, apply=True)
            if config.get('probation_review'):
                # Right after new writes: rules retire junk, the model only flags.
                from .probation import review as probation_review
                result['probation'] = probation_review(vault, apply=True)
        except Exception:
            result = {'at': now(), 'status': 'FAILED'}
        write_json(RuntimeConfig(vault).root / 'last-queue-triage.json', result)

    async def background():
        try:
            await asyncio.to_thread(run)
        finally:
            app.state.queue_triage_running = False

    asyncio.create_task(background())


MEMORY_AUDIT_INTERVAL_SECONDS = 7 * 24 * 3600
# A failed run is retried after hours, not a week later.
MEMORY_AUDIT_RETRY_SECONDS = 6 * 3600


def memory_audit_due(report, current=None):
    """Whether the last audit report is old enough for another run."""
    from datetime import datetime, timezone
    report = report if isinstance(report, dict) else {}
    try:
        when = datetime.fromisoformat(str(report['at']))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
    except (KeyError, ValueError, TypeError):
        return True  # never ran, or an unreadable time: run rather than stall forever
    elapsed = ((current or datetime.now(timezone.utc)) - when).total_seconds()
    if elapsed < 0:
        return True  # a time in the future (clock change) must not block the audit
    wait = MEMORY_AUDIT_RETRY_SECONDS if report.get('status') == 'FAILED' else MEMORY_AUDIT_INTERVAL_SECONDS
    return elapsed >= wait


async def maybe_memory_audit(app):
    """Owner decision 2026-09-30: weekly memory audit in the background.

    Runs when ``memory_audit`` is on and the last report is a week old; it
    retires only guarded exact duplicates and writes suggestions for the rest.
    """
    vault = app.state.vault
    try:
        if not RuntimeConfig(vault).load().get('memory_audit') or app.state.memory_audit_running:
            return
        if not memory_audit_due(read_json(RuntimeConfig(vault).root / 'memory-audit.json', {})):
            return
    except Exception:
        return
    app.state.memory_audit_running = True

    def run():
        from .memory_audit import audit
        try:
            audit(vault, apply=True)
        except Exception as exc:
            # audit() already wrote what it retired before failing; keep that
            # and add a content-free error code.
            report = read_json(RuntimeConfig(vault).root / 'memory-audit.json', {}) or {}
            write_json(RuntimeConfig(vault).root / 'memory-audit.json',
                       {**report, 'at': now(), 'status': 'FAILED', 'error': type(exc).__name__[:60]})

    async def background():
        try:
            await asyncio.to_thread(run)
        finally:
            app.state.memory_audit_running = False

    asyncio.create_task(background())


IDLE_LIMIT_SECONDS = 900
# With local prompt models loaded a restart costs a ~25 s warm-up during which
# prompts keep V1 order (and one may be lost), so the service stays up longer.
PROMPT_MODELS_IDLE_LIMIT_SECONDS = 4 * 3600


def idle_limit_seconds():
    from .context import prompt_providers_loaded
    try:
        loaded = prompt_providers_loaded()
    except Exception:
        loaded = False  # never let the idle check end the worker loop
    return PROMPT_MODELS_IDLE_LIMIT_SECONDS if loaded else IDLE_LIMIT_SECONDS


def serve(vault):
    import socket
    import threading
    import uvicorn
    cfg = RuntimeConfig(vault)
    with file_lock(cfg.root / 'server', timeout=.1):
        token = secrets.token_urlsafe(32)
        app = create_app(vault, token=token)
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        write_json(cfg.root / 'service.json', {'port': port, 'token': token, 'pid': __import__('os').getpid()})
        server = uvicorn.Server(uvicorn.Config(app, log_level='warning', access_log=False))
        def idle_watch():
            while not server.should_exit:
                time.sleep(2)
                if app.state.idle:
                    server.should_exit = True
        threading.Thread(target=idle_watch, daemon=True).start()
        from brain_eleven.runtime.context import prompt_provider_config, warm_prompt_providers
        threading.Thread(target=warm_prompt_providers, args=(prompt_provider_config(vault),),
                         kwargs={'vault': vault}, daemon=True).start()
        try:
            server.run(sockets=[sock])
        finally:
            sock.close()
            (cfg.root / 'service.json').unlink(missing_ok=True)
            launch = read_json(cfg.root / 'launch.json', {})
            if isinstance(launch, dict) and launch.get('pid') == os.getpid():
                (cfg.root / 'launch.json').unlink(missing_ok=True)
