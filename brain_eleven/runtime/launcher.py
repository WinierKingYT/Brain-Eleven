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

# Native hooks invoke this module directly by absolute file path. Keep the
# direct-file bootstrap while installed/module invocations use normal imports.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from brain_eleven.runtime.storage import (ECONOMICAL_SESSION_CHARS, ECONOMICAL_SUBAGENT_CHARS, RuntimeConfig, read_json,
                                          write_json, identity, now, runtime_file_lock as file_lock)


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


def _process_alive(pid):
    """Return whether a launch marker still belongs to a live process."""
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError, ValueError):
        return False
    return True


def _service_interpreter():
    """Console python.exe for the background service, even when hooks run pythonw.exe.

    CREATE_NO_WINDOW means nothing to GUI-subsystem pythonw.exe, so a pythonw
    service owns no console, and every console program it later starts (the
    Hermes/Codex provider CLIs) gets a new VISIBLE console -- measured
    2026-09-24 as one hermes.EXE window flash per captured message. Console
    python.exe under CREATE_NO_WINDOW owns one hidden console that all of its
    descendants inherit instead.
    """
    executable = Path(sys.executable)
    if os.name == 'nt' and executable.name.lower() == 'pythonw.exe':
        console = executable.with_name('python.exe')
        if console.is_file():
            return str(console)
    return sys.executable


def ensure_service(vault, *, wait=False, wait_timeout=8):
    deadline = time.monotonic() + wait_timeout
    cfg = RuntimeConfig(vault)
    if cfg.load()['mode'] == 'OFF':
        return False
    try:
        request_service(vault, '/api/runtime/status', timeout=.25)
        return True
    except (OSError, ValueError, KeyError, http.client.HTTPException):
        pass
    cfg.ensure_root()
    with file_lock(cfg.root / 'launch', timeout=.15):
        prior = read_json(cfg.root / 'launch.json', {})
        # Bounded throttle plus the server lock prevent concurrent hook starts.
        launch_recent = time.time() - prior.get('started', 0) <= 10
        launch_pid = prior.get('pid')
        if not launch_recent or not _process_alive(launch_pid):
            options = {'stdin': subprocess.DEVNULL, 'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL, 'cwd': str(ROOT)}
            if os.name == 'nt':
                # CREATE_NO_WINDOW is ignored when combined with DETACHED_PROCESS.
                options['creationflags'] = subprocess.CREATE_NO_WINDOW
            else:
                options['start_new_session'] = True
            process = subprocess.Popen([_service_interpreter(), str(Path(__file__).resolve()), '--vault', str(Path(vault).resolve()), '--serve'], **options)
            write_json(cfg.root / 'launch.json', {'started': time.time(), 'pid': process.pid})
    if wait:
        # Always probe at least once: on a slow machine the lock and the
        # launch.json write can use up a short wait_timeout before the loop.
        while True:
            try:
                request_service(vault, '/api/runtime/status', timeout=.2)
                return True
            except (OSError, ValueError, KeyError, http.client.HTTPException):
                if time.monotonic() >= deadline:
                    break
                time.sleep(.1)
    return False


def _capture_outcome(cfg, client, event, payload, outcome, error=None):
    """Per-client record of what the last Stop/SessionEnd actually did.

    A skipped capture (mode OFF, unregistered cwd) used to look identical to
    an enqueued one in last-hook.json ("OK"). Only presence flags, fixed
    codes and the ledger join hash are stored: no paths, prompts or content.
    """
    from brain_eleven.runtime.worker import capture_session_hash
    session = payload.get('session_id')
    record = {'at': now(), 'client': client, 'event': event, 'outcome': outcome, 'error': error,
              'cwd_present': bool(payload.get('cwd')), 'transcript_path_present': bool(payload.get('transcript_path')),
              'capture_session_hash': capture_session_hash(client, session) if isinstance(session, str) and session else None}
    try:
        write_json(cfg.root / f'last-capture-{client}.json', record)
    except OSError:
        pass


def hook(vault, client, event, payload):
    from brain_eleven.runtime.worker import allowed, capture_session_hash, enqueue
    cfg = RuntimeConfig(vault)
    capture = event in {'Stop', 'SessionEnd'}
    if cfg.load()['mode'] == 'OFF':
        if capture:
            _capture_outcome(cfg, client, event, payload, 'MODE_OFF')
        return {}
    if not allowed(vault, payload.get('cwd')):
        if capture:
            _capture_outcome(cfg, client, event, payload,
                             'CWD_NOT_REGISTERED' if payload.get('cwd') else 'CWD_MISSING')
        return {}
    if capture:
        # This path never reads a transcript or waits for service startup.
        result = enqueue(vault, client, payload)
        _capture_outcome(cfg, client, event, payload, str(result.get('status')), result.get('error'))
        ensure_service(vault)
        return {} if result.get('status') not in {'DEGRADED', 'FAILED'} else {'systemMessage': 'Brain-Eleven: konuşma kaynağı alınamadı; doctor ile kontrol edin.'}
    if event == 'SubagentStart':
        return subagent_start(vault, client, payload)
    profile = cfg.load().get('context_profile', 'normal')
    if profile == 'manual' or (profile == 'economical' and event == 'UserPromptSubmit'):
        # The owner chose fewer injected tokens; nothing is compiled or started.
        return {}
    deadline = time.monotonic() + 2.5
    ready = ensure_service(vault, wait=True, wait_timeout=2.2)
    if event not in {'SessionStart', 'UserPromptSubmit'}:
        raise ValueError('Unsupported hook event')
    prompt = payload.get('prompt', '')
    session = payload.get('session_id', '')
    if not isinstance(prompt, str) or not isinstance(session, str) or not session:
        raise ValueError('Invalid prompt event')
    if not ready:
        output = {'systemMessage': 'Brain-Eleven başlatılıyor; bu istemde kayıtlı bağlam kullanılamadı.'}
        if event != 'SessionStart':
            return output
        # A bootstrap that never compiled still leaves a receipt; its status
        # is not EMITTED, so a later SessionStart for the session may retry.
        key = identity('delivery_', client, session, 'bootstrap')
        return output, cfg.root / 'deliveries' / (key + '.json'), {
            'status': 'NOT_COMPILED', 'stage': 'NOT_COMPILED', 'reason': 'SERVICE_NOT_READY',
            'at': now(), 'client': client, 'event': event,
            'session_hash': identity('session_', session), 'turn_hash': identity('turn_', 'bootstrap'),
            'capture_session_hash': capture_session_hash(client, session), 'context_delivered': False}
    # Native turn identity when provided; otherwise transcript position plus
    # prompt hash distinguishes repeated identical prompts in later turns.
    locator = payload.get('transcript_path')
    size = Path(locator).stat().st_size if locator and Path(locator).is_file() else None
    reliable_turn = payload.get('turn_id') or (identity('turn_', prompt, size) if size is not None else None)
    turn = ('bootstrap' if event == 'SessionStart' else reliable_turn or identity('turn_', prompt, time.time_ns()))
    key = identity('delivery_', client, session, turn)
    path = cfg.root / 'deliveries' / (key + '.json')
    with file_lock(path, timeout=.15):
        if read_json(path, {}).get('status') == 'EMITTED':
            return {}
        result = request_service(vault, '/api/context', {'project_root': payload['cwd'], 'request': prompt,
                                 'client': client, 'session': session, 'turn': str(turn), 'event': event},
                                 timeout=max(.05, min(2, deadline - time.monotonic())))
        output = {}
        # ``delivery_approved`` and provider are mandatory at the native
        # model-facing boundary.  Missing metadata fails closed so a stale or
        # malformed service response cannot be relabeled as V1.
        provider = result.get('provider')
        approved = result.get('delivery_approved') is True
        provider_allowed = provider in {'V1', 'W06B_TASK_AWARE'}
        if approved and provider_allowed and result.get('delivered') is True and result.get('context'):
            text = result['context']
            if profile == 'economical':
                text = text[:ECONOMICAL_SESSION_CHARS]
            output['hookSpecificOutput'] = {'hookEventName': event, 'additionalContext': text}
        if result.get('missing_critical_needs') or result.get('status') not in {'SUCCESS', 'EMPTY', 'OFF', 'SCOPE_DISABLED'}:
            output['systemMessage'] = 'Brain-Eleven: bağlam eksik veya kullanılamıyor; çalışma devam ediyor. İnceleme ekranını kontrol edin.'
        delivered = bool(output.get('hookSpecificOutput'))
        if delivered:
            stage, reason = 'DELIVERED', None
        elif not result.get('context'):
            stage, reason = 'COMPILED_NOT_DELIVERED', 'EMPTY_CONTEXT'
        elif not provider_allowed:
            stage, reason = 'COMPILED_NOT_DELIVERED', 'PROVIDER_NOT_ALLOWED'
        else:
            stage, reason = 'COMPILED_NOT_DELIVERED', 'NOT_APPROVED'
        # Only the caller can acknowledge that stdout was successfully flushed.
        return output, path, {'status': 'EMITTED', 'at': now(), 'client': client, 'event': event,
                              'stage': stage, 'reason': reason, 'compile_status': result.get('status'),
                              'provider': provider, 'delivery_approved': approved,
                              'capture_session_hash': capture_session_hash(client, session),
                              'session_hash': identity('session_', session), 'turn_hash': identity('turn_', turn),
                              'context_delivered': delivered,
                              'selected_ids': result.get('selected_ids', []) if output.get('hookSpecificOutput') else [],
                              'project_id': result.get('project_id'),
                              'context_elapsed_ms':result.get('elapsed_ms', 0)}


SUBAGENT_FINDINGS_HEADING = '### Brain-Eleven bulguları'
SUBAGENT_INSTRUCTION = (
    'Brain-Eleven: Raporunu bitirirken en sona "' + SUBAGENT_FINDINGS_HEADING + '" başlığı ekle ve altına '
    'bu işte öğrendiğin kalıcı şeyleri madde madde yaz: verilen kararlar, bulunan hatalar ve çözümleri, '
    'projeye dair doğrulanmış gerçekler. Her madde tek başına anlaşılır olsun. Geçici durum, tahmin, '
    'dosya içeriği, sır veya tam dosya yolu yazma. Kalıcı bir şey yoksa başlığı hiç ekleme.')
SUBAGENT_CONTEXT_CHARS = 2500


def subagent_start(vault, client, payload):
    """Give a starting subagent the project's memory and ask it to report durable findings.

    A subagent starts without the parent's SessionStart context, and what it
    learns is lost unless it comes back in its report. The report reaches the
    parent transcript, where the findings section is captured for review.
    """
    if client != 'claude':
        raise ValueError('Unsupported hook event')
    session, agent = payload.get('session_id'), payload.get('agent_id')
    if not isinstance(session, str) or not session or not isinstance(agent, str) or not agent:
        raise ValueError('Invalid subagent event')
    profile = RuntimeConfig(vault).load().get('context_profile', 'normal')
    if profile == 'manual':
        return {}
    limit = ECONOMICAL_SUBAGENT_CHARS if profile == 'economical' else SUBAGENT_CONTEXT_CHARS
    context = ''
    if ensure_service(vault, wait=True, wait_timeout=1.5):
        try:
            result = request_service(vault, '/api/context', {
                'project_root': payload['cwd'], 'request': '', 'client': client, 'session': session,
                'turn': identity('subagent_', agent), 'event': 'SessionStart'}, timeout=1.2)
            if (result.get('delivery_approved') is True and result.get('delivered') is True
                    and result.get('provider') in {'V1', 'W06B_TASK_AWARE'} and isinstance(result.get('context'), str)):
                context = result['context'][:limit]
        except (OSError, ValueError, KeyError, http.client.HTTPException):
            context = ''
    text = (context + '\n\n' if context else '') + SUBAGENT_INSTRUCTION
    return {'hookSpecificOutput': {'hookEventName': 'SubagentStart', 'additionalContext': text}}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--vault', required=True)
    parser.add_argument('--client', choices=['claude', 'codex'])
    parser.add_argument('--event', choices=['SessionStart', 'UserPromptSubmit', 'Stop', 'SessionEnd', 'SubagentStart'])
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
        with file_lock(delivery_lock, timeout=.15) if args.event in {'SessionStart', 'UserPromptSubmit'} else nullcontext():
            result = hook(args.vault, args.client, args.event, payload)
            if isinstance(result, tuple):
                result, path, record = result
            print(json.dumps(result, ensure_ascii=True), flush=True)
            if record:
                record['hook_elapsed_ms'] = round((time.perf_counter() - started) * 1000)
                write_json(path, record)
        status = 'DEGRADED' if isinstance(result, dict) and result.get('systemMessage') else 'OK'
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
