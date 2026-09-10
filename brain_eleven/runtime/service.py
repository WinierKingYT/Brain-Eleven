"""Loopback-only review API and single local worker lifecycle."""
import asyncio
from contextlib import asynccontextmanager
import hmac
from pathlib import Path
import secrets
import time
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from brain_eleven.infrastructure.locking import file_lock
from brain_eleven.memory import MemoryStore
from brain_eleven.state import StateStore
from .storage import RuntimeConfig, read_json, write_json, identity, now
from .review import ReviewStore
from .worker import Worker, apply_candidate
from .context import compile_context


def review_action(vault, review_id, action, payload):
    cfg = RuntimeConfig(vault)
    if action == 'accept' and cfg.load()['mode'] not in {'CANARY', 'ACTIVE'}:
        raise ValueError('Enable canary before accepting canonical changes')
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
            if action == 'reject':
                return store.finish(item, 'REJECTED')
            if action != 'accept':
                raise ValueError('Unknown review action')
            candidate = dict(item['candidate'])
            if 'content' in payload:
                if not isinstance(payload['content'], str) or not 3 <= len(payload['content']) <= 8000:
                    raise ValueError('Candidate text must be 3..8000 characters')
                candidate['text' if candidate['candidate_type'] == 'STATE_MUTATION' else 'content'] = payload['content']
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
            return result


def runtime_status(vault):
    cfg = RuntimeConfig(vault)
    capture = Path(vault) / '.brain-eleven' / 'capture'
    return {'mode': cfg.load()['mode'], 'queue': {name: len(list((capture / name).glob('*.json'))) for name in ('queued', 'processing', 'completed', 'dead-letter')},
            'worker': read_json(cfg.root / 'last-worker.json'), 'context': read_json(cfg.root / 'last-context.json'),
            'model': read_json(cfg.root / 'model-status.json'), 'graduation': read_json(cfg.root / 'graduation.json', {'status': 'PENDING_REAL_USE'})}


def create_app(vault, *, token=None, background=True):
    cfg = RuntimeConfig(vault)
    token = token or secrets.token_urlsafe(32)
    async def worker_loop():
        while True:
            delay = 2
            try:
                result = await asyncio.to_thread(Worker(vault).once)
                if result['status'] not in {'IDLE', 'OFF'}:
                    app.state.last_activity = time.monotonic()
                    delay = .05
            except Exception:
                write_json(cfg.root / 'last-worker.json', {'at': now(), 'status': 'FAILED', 'error': 'WORKER_UNAVAILABLE'})
            if time.monotonic() - app.state.last_activity > 900:
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
        from context_compiler_v2.safety import contains_secret
        from scripts.capture_safety import evaluate_capture
        items = ReviewStore(vault).list()
        memory = MemoryStore(vault).load()
        state = StateStore(vault)
        for item in items:
            if item['status'] == 'PENDING':
                c = item['candidate']
                item['expected_revision'] = state.project_revision(c['project_id']) if c['candidate_type'] == 'STATE_MUTATION' else memory['revision']
                if c['candidate_type'] == 'NEW_MEMORY':
                    targets = [{'id': x['memory_id'], 'text': x['content']} for x in memory['validated_memory']
                               if x.get('project_id') == c['project_id'] and x.get('status') == 'active']
                else:
                    project = state.get_project(c['project_id']) or {}
                    bucket = {'RESOLVE_BLOCKER': 'blockers', 'RESOLVE_REQUIREMENT': 'requirements'}.get(c.get('operation'))
                    targets = [{'id': x['id'], 'text': x['text']} for x in project.get(bucket, []) if x.get('status') in {'ACTIVE', 'OPEN', 'PLANNED', 'IN_PROGRESS'}] if bucket else []
                item['targets'] = [x for x in targets if evaluate_capture(x['text']).accepted and not contains_secret(x['text'])]
        return {'candidates': items}

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
        try:
            server.run(sockets=[sock])
        finally:
            sock.close()
            (cfg.root / 'service.json').unlink(missing_ok=True)
