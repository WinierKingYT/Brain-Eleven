"""Small native hook entry point. No framework or model import on fast paths."""
import argparse
from contextlib import nullcontext
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import time

# Supports an absolute script command even when the client cwd is another repo.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from brain_eleven.runtime.storage import RuntimeConfig, read_json, write_json, identity, now
from brain_eleven.infrastructure.locking import file_lock


def request_service(vault, route, payload=None, timeout=.35):
    service = read_json(RuntimeConfig(vault).root / 'service.json')
    if not isinstance(service, dict) or not isinstance(service.get('port'), int) or not 1 <= service['port'] <= 65535:
        raise OSError('Service unavailable')
    conn = http.client.HTTPConnection('127.0.0.1', service['port'], timeout=timeout)
    try:
        conn.request('GET' if payload is None else 'POST', route,
                     body=None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                     headers={'Authorization': 'Bearer ' + service['token'], 'Content-Type': 'application/json'})
        response = conn.getresponse()
        content = response.read(131073)
        if response.status != 200 or len(content) > 131072:
            raise OSError('Service request failed')
        return json.loads(content)
    finally:
        conn.close()


def ensure_service(vault, *, wait=False):
    cfg = RuntimeConfig(vault)
    if cfg.load()['mode'] == 'OFF':
        return False
    try:
        request_service(vault, '/api/runtime/status', timeout=.25)
        return True
    except (OSError, ValueError, KeyError, http.client.HTTPException):
        pass
    cfg.root.mkdir(parents=True, exist_ok=True)
    with file_lock(cfg.root / 'launch', timeout=.15):
        prior = read_json(cfg.root / 'launch.json', {})
        # Bounded throttle plus the server lock prevent concurrent hook starts.
        if time.time() - prior.get('started', 0) > 10:
            options = {'stdin': subprocess.DEVNULL, 'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL, 'cwd': str(ROOT)}
            if os.name == 'nt':
                # CREATE_NO_WINDOW is ignored when combined with DETACHED_PROCESS.
                options['creationflags'] = subprocess.CREATE_NO_WINDOW
            else:
                options['start_new_session'] = True
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--vault', str(Path(vault).resolve()), '--serve'], **options)
            write_json(cfg.root / 'launch.json', {'started': time.time()})
    if wait:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                request_service(vault, '/api/runtime/status', timeout=.2)
                return True
            except (OSError, ValueError, KeyError, http.client.HTTPException):
                time.sleep(.1)
    return False


def hook(vault, client, event, payload):
    from brain_eleven.runtime.worker import allowed, enqueue
    cfg = RuntimeConfig(vault)
    if cfg.load()['mode'] == 'OFF' or not allowed(vault, payload.get('cwd')):
        return {}
    if event in {'Stop', 'SessionEnd'}:
        # This path never reads a transcript or waits for service startup.
        result = enqueue(vault, client, payload)
        ensure_service(vault)
        return {} if result.get('status') not in {'DEGRADED', 'FAILED'} else {'systemMessage': 'Brain-Eleven: konuşma kaynağı alınamadı; doctor ile kontrol edin.'}
    ready = ensure_service(vault)
    if event == 'SessionStart':
        return {}
    if event != 'UserPromptSubmit':
        raise ValueError('Unsupported hook event')
    if not ready:
        return {'systemMessage': 'Brain-Eleven başlatılıyor; bu istemde kayıtlı bağlam kullanılamadı.'}
    prompt = payload.get('prompt', '')
    session = payload.get('session_id', '')
    if not isinstance(prompt, str) or not isinstance(session, str) or not session:
        raise ValueError('Invalid prompt event')
    # Native turn identity when provided; otherwise transcript position plus
    # prompt hash distinguishes repeated identical prompts in later turns.
    locator = payload.get('transcript_path')
    size = Path(locator).stat().st_size if locator and Path(locator).is_file() else None
    reliable_turn = payload.get('turn_id') or (identity('turn_', prompt, size) if size is not None else None)
    turn = reliable_turn or identity('turn_', prompt, time.time_ns())
    key = identity('delivery_', client, session, turn)
    path = cfg.root / 'deliveries' / (key + '.json')
    with file_lock(path, timeout=.15):
        if read_json(path, {}).get('status') == 'EMITTED':
            return {}
        result = request_service(vault, '/api/context', {'project_root': payload['cwd'], 'request': prompt,
                                 'client': client, 'session': session, 'turn': str(turn)}, timeout=2)
        output = {}
        if result.get('delivered') and result.get('context'):
            output['hookSpecificOutput'] = {'hookEventName': event, 'additionalContext': result['context']}
        if result.get('missing_critical_needs') or result.get('status') not in {'SUCCESS', 'EMPTY', 'OFF', 'SCOPE_DISABLED'}:
            output['systemMessage'] = 'Brain-Eleven: bağlam eksik veya kullanılamıyor; çalışma devam ediyor. İnceleme ekranını kontrol edin.'
        # Only the caller can acknowledge that stdout was successfully flushed.
        return output, path, {'status': 'EMITTED', 'at': now(), 'client': client,
                              'session_hash': identity('session_', session), 'turn_hash': identity('turn_', turn),
                              'context_delivered': bool(output.get('hookSpecificOutput')),
                              'selected_ids': result.get('selected_ids', []) if output.get('hookSpecificOutput') else [],
                              'v1_ids': result.get('v1_ids', []), 'project_id':result.get('project_id'),
                              'implementation_fingerprint':result.get('implementation_fingerprint'),
                              'context_elapsed_ms':result.get('elapsed_ms', 0)}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--vault', required=True)
    parser.add_argument('--client', choices=['claude', 'codex'])
    parser.add_argument('--event', choices=['SessionStart', 'UserPromptSubmit', 'Stop', 'SessionEnd'])
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args(argv)
    if args.serve:
        from brain_eleven.runtime.service import serve
        serve(args.vault)
        return 0
    started = time.perf_counter()
    record = None
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise ValueError('Hook input too large')
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError('Invalid hook input')
        # Retain ownership through stdout flush and its durable receipt. A
        # second native invocation cannot emit the same turn in that gap.
        delivery_lock = RuntimeConfig(args.vault).root / 'delivery-locks' / identity('session_', args.client, payload.get('session_id'))
        with file_lock(delivery_lock, timeout=.15) if args.event == 'UserPromptSubmit' else nullcontext():
            result = hook(args.vault, args.client, args.event, payload)
            if isinstance(result, tuple):
                result, path, record = result
            print(json.dumps(result, ensure_ascii=True), flush=True)
            if record:
                record['hook_elapsed_ms'] = round((time.perf_counter() - started) * 1000)
                write_json(path, record)
        status = 'OK'
    except Exception:
        # Never echo stdin, a prompt, a transcript location, or an exception.
        print(json.dumps({'systemMessage': 'Brain-Eleven kullanılamıyor; çalışma devam ediyor. doctor ile kontrol edin.'}), flush=True)
        status = 'DEGRADED'
    try:
        write_json(RuntimeConfig(args.vault).root / 'last-hook.json', {'at': now(), 'client': args.client, 'event': args.event,
                   'status': status, 'elapsed_ms': round((time.perf_counter() - started) * 1000)})
    except OSError:
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
