"""Additive, reversible native client configuration; never changes hook trust."""
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import shlex
import sys
from brain_eleven.infrastructure.locking import file_lock
from .storage import RuntimeConfig, read_json, write_json, now

EVENTS = ('SessionStart', 'UserPromptSubmit', 'Stop', 'SessionEnd')


def hook_python():
    executable = Path(sys.executable).resolve()
    if os.name == 'nt':
        executable = executable.with_name('pythonw.exe')
        if not executable.is_file():
            raise ValueError('Windowless Python executable is required for Windows hooks')
    return str(executable)


def hook_command(vault, client, event):
    launcher = Path(__file__).with_name('launcher.py').resolve()
    args = [hook_python(), str(launcher), '--vault', str(Path(vault).resolve()), '--client', client, '--event', event]
    if os.name == 'nt':
        # Codex uses PowerShell on Windows; Claude's default hook shell is bash.
        return ('& ' if client == 'codex' else '') + ' '.join("'" + part.replace("'", "'\"'\"'" if client == 'claude' else "''") + "'" for part in args)
    return shlex.join(args)


def merge_hooks(document, additions, previous=None):
    value = deepcopy(document)
    hooks = value.setdefault('hooks', {})
    if not isinstance(hooks, dict):
        raise ValueError('Client hooks must be an object')
    for event in EVENTS:
        entries = hooks.setdefault(event, [])
        if not isinstance(entries, list):
            raise ValueError('Client hook event must be a list')
        old = (previous or {}).get(event)
        if old:
            entries[:] = [entry for entry in entries if entry != old]
        addition = additions.get(event)
        if addition and addition not in entries:
            entries.append(deepcopy(addition))
        if not entries:
            hooks.pop(event, None)
    return value


def client_paths(home=None):
    home = Path(home) if home else Path.home()
    return {'claude': home / '.claude' / 'settings.json',
            'codex': (Path(os.environ['CODEX_HOME']) if home == Path.home() and os.environ.get('CODEX_HOME') else home / '.codex') / 'hooks.json'}


def owned_entries(item):
    """Keep every journaled command until all client replacements succeed."""
    history = list(item.get('owned_entries', []))
    if item.get('entries') and item['entries'] not in history:
        history.append(item['entries'])
    return history


def remove_owned(document, item):
    for entries in owned_entries(item):
        document = merge_hooks(document, {}, entries)
    return document


def suspend_legacy(document, home):
    """Only replace the exact historical global Brain-Eleven commands."""
    value = deepcopy(document)
    suspended = {}
    base = Path(home).as_posix()
    wsl = '/mnt/' + base[0].lower() + base[2:] if len(base) > 1 and base[1] == ':' else base
    for event, filename in [('SessionStart', 'brain-eleven-session-start'), ('SessionEnd', 'brain-eleven-remember-opt-in')]:
        command = f'bash {base}/.claude/hooks/{filename} || bash {wsl}/.claude/hooks/{filename}'
        entries = value.get('hooks', {}).get(event, [])
        kept = []
        for entry in entries:
            removed = [hook for hook in entry.get('hooks', []) if hook == {'type': 'command', 'command': command}]
            remaining = [hook for hook in entry.get('hooks', []) if hook not in removed]
            if removed:
                suspended.setdefault(event, []).append({**entry, 'hooks': removed})
            if remaining or not removed:
                kept.append({**entry, 'hooks': remaining} if removed else entry)
        if event in value.get('hooks', {}):
            value['hooks'][event] = kept
    return value, suspended


def install(vault, *, home=None, clients=('claude', 'codex')):
    from .migration import migrate
    from brain_eleven.projects.registry import ProjectRegistry
    from brain_eleven.state import StateService, StateStore
    cfg = RuntimeConfig(vault)
    missing = [name for name in ('fastapi', 'uvicorn', 'httpx', 'networkx') if importlib.util.find_spec(name) is None]
    if missing:
        raise ValueError('Install requirements.txt in this Python environment first: ' + ', '.join(missing))
    cfg.root.mkdir(parents=True, exist_ok=True)
    with file_lock(cfg.root / 'install'):
        manifest = read_json(cfg.root / 'installation.json', {'clients': {}})
        paths = client_paths(home)
        # Validate every destination before any client configuration is changed.
        plans = []
        for client in clients:
            path = paths[client]
            before = read_json(path, {})
            if not isinstance(before, dict):
                raise ValueError('Invalid client configuration')
            additions = {event: {'hooks': [{'type': 'command', 'command': hook_command(vault, client, event), 'timeout': 3}]} for event in EVENTS}
            if client == 'claude':
                # Native exec form avoids Git Bash / PowerShell differences.
                for event, entry in additions.items():
                    entry['hooks'][0].update(command=hook_python(),
                        args=[str(Path(__file__).with_name('launcher.py').resolve()), '--vault', str(Path(vault).resolve()), '--client', client, '--event', event])
            if client == 'codex':
                additions['UserPromptSubmit']['hooks'][0]['additionalContextLimit'] = 3500
            old = manifest['clients'].get(client, {})
            cleaned = remove_owned(before, old)
            cleaned, suspended = suspend_legacy(cleaned, path.parent.parent) if client == 'claude' else (cleaned, {})
            for event, entries in old.get('suspended_legacy', {}).items():
                for entry in entries:
                    if entry not in suspended.setdefault(event, []):
                        suspended[event].append(entry)
            plans.append((client, path, before, additions, merge_hooks(cleaned, additions), suspended))
        registry = ProjectRegistry(vault)
        project = registry.resolve(Path(vault).resolve())
        if project is None:
            project = registry.register(vault, proactive_capture=True)
        elif project['status'] != 'active':
            raise ValueError('Canary project is archived')
        else:
            registry.set_proactive_capture(project['project_id'], True)
        if StateStore(vault).project_revision(project['project_id']) is None:
            StateService(vault).init_project(project['project_id'], source={'type': 'user', 'reference': 'runtime-install'})
        migrate(vault)
        config = cfg.load()
        config['project_ids'] = list(dict.fromkeys(config['project_ids'] + [project['project_id']]))
        if config['mode'] == 'OFF':
            config['mode'] = 'SHADOW'
        write_json(cfg.path, config)
        for client, path, before, entries, after, suspended in plans:
            # Journal before each replace permits recovery from partial installs.
            prior = manifest['clients'].get(client, {})
            history = owned_entries(prior)
            if entries not in history:
                history.append(entries)
            manifest['clients'][client] = {'path': str(path), 'entries': entries, 'owned_entries': history,
                                           'suspended_legacy': suspended,
                                           'original': prior.get('original', before), 'installed_at': now()}
            write_json(cfg.root / 'installation.json', manifest)
            with file_lock(path):
                current = read_json(path, {})
                if current != before:
                    raise ValueError('Client settings changed during installation; retry')
                write_json(path, after)
            manifest['clients'][client]['owned_entries'] = [entries]
            write_json(cfg.root / 'installation.json', manifest)
        write_json(cfg.root / 'native-hooks-installed.json', {'clients': list(manifest['clients'])})
        return {'status': 'INSTALLED', 'mode': config['mode'], 'clients': list(clients), 'project_id': project['project_id'], 'hook_trust': 'CLIENT_REVIEW_REQUIRED'}


def uninstall(vault):
    cfg = RuntimeConfig(vault)
    cfg.set_mode('OFF')
    from .launcher import request_service
    try:
        request_service(vault, '/api/runtime/stop', {})
    except (OSError, ValueError, KeyError):
        pass
    with file_lock(cfg.root / 'install'):
        manifest = read_json(cfg.root / 'installation.json', {'clients': {}})
        for item in manifest['clients'].values():
            path = Path(item['path'])
            with file_lock(path):
                current = read_json(path, {})
                restored = remove_owned(current, item)
                for event, entries in item.get('suspended_legacy', {}).items():
                    for entry in entries:
                        hooks = restored.setdefault('hooks', {}).setdefault(event, [])
                        if entry not in hooks:
                            hooks.append(entry)
                write_json(path, restored)
        write_json(cfg.root / 'installation.json', {'clients': {}, 'uninstalled_at': now()})
        (cfg.root / 'native-hooks-installed.json').unlink(missing_ok=True)
    return {'status': 'UNINSTALLED', 'canonical_data': 'PRESERVED'}


def _session_start_health(vault):
    path = Path(vault) / '.claude' / 'session-run-result.json'
    try:
        result = read_json(path, {})
    except (OSError, ValueError, TypeError):
        result = {}
    timestamp = result.get('timestamp') if isinstance(result, dict) else None
    exit_status = result.get('exit_status') if isinstance(result, dict) else None
    if type(exit_status) is int:
        state = 'ok' if exit_status == 0 else 'failed'
    else:
        state = 'unknown'
    if isinstance(timestamp, str) and timestamp:
        message = f'last SessionStart: {state} at {timestamp}'
    else:
        message = 'last SessionStart: unknown'
    return message, state == 'failed'


def doctor(vault, *, home=None):
    cfg = RuntimeConfig(vault)
    checks = {'python': {'version': sys.version.split()[0], 'executable': sys.executable}}
    checks['dependencies'] = {name: importlib.util.find_spec(name) is not None for name in ('fastapi', 'uvicorn', 'httpx', 'networkx')}
    manifest = read_json(cfg.root / 'installation.json', {'clients': {}})
    checks['clients'] = {}
    for client, path in client_paths(home).items():
        entry = manifest['clients'].get(client)
        document = read_json(path, {})
        installed = bool(entry) and all(item in document.get('hooks', {}).get(event, []) for event, item in entry['entries'].items())
        checks['clients'][client] = {'configured': installed, 'trust': 'VERIFY_IN_NATIVE_CLIENT'}
    checks['mode'] = cfg.load()['mode']
    from .launcher import request_service
    try:
        request_service(vault, '/api/runtime/status')
        checks['service'] = 'RUNNING'
    except (OSError, ValueError, KeyError):
        checks['service'] = 'STOPPED'
    checks['last_hook'] = read_json(cfg.root / 'last-hook.json')
    checks['last_session_start'], session_failed = _session_start_health(vault)
    checks['status'] = 'READY' if (
        all(checks['dependencies'].values())
        and all(x['configured'] for x in checks['clients'].values())
        and not session_failed
    ) else 'ATTENTION'
    return checks
