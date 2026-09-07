"""V1 compatibility at the native boundary while V2 remains shadow."""
import io
import json
import sys

import pytest

from tests.test_pre13_runtime import runtime, candidate
from brain_eleven.runtime.context import compile_context
from brain_eleven.runtime.storage import RuntimeConfig, identity, read_json, write_json
from brain_eleven.runtime.worker import apply_candidate
from brain_eleven.projects.registry import ProjectRegistry


@pytest.mark.parametrize('client', ['claude', 'codex'])
def test_shadow_bootstrap_is_v1_but_prompt_is_not_delivered(runtime, client):
    vault, project = runtime
    apply_candidate(vault, candidate(project), op_id=identity('op_', 'seed'))
    RuntimeConfig(vault).set_mode('SHADOW')
    result = compile_context(vault, vault, '', client=client, event='SessionStart')
    assert result['provider'] == 'V1' and result['delivered']
    assert 'SQLite' in result['context'] and result['estimated_tokens'] <= 3000
    assert not compile_context(vault, vault, 'Which database?', client=client)['delivered']


@pytest.mark.parametrize('change', ['OFF', 'optout', 'revision'])
def test_bootstrap_revalidates_after_render(runtime, monkeypatch, change):
    from brain_eleven._legacy import load_legacy_module
    compiler = load_legacy_module('brain_eleven_legacy_context_compiler', 'context-compiler.py').ContextCompiler
    original = compiler._generate_context_block
    vault, project = runtime
    def changed(self, *args):
        output = original(self, *args)
        if change == 'OFF':
            RuntimeConfig(vault).set_mode('OFF')
        elif change == 'optout':
            ProjectRegistry(vault).set_proactive_capture(project, False)
        else:
            apply_candidate(vault, candidate(project), op_id=identity('op_', 'later'))
        return output
    monkeypatch.setattr(compiler, '_generate_context_block', changed)
    if change == 'revision':
        with pytest.raises(RuntimeError):
            compile_context(vault, vault, '', event='SessionStart')
    else:
        assert not compile_context(vault, vault, '', event='SessionStart')['delivered']


def test_bootstrap_bounded_and_scope_disabled(runtime, tmp_path):
    vault, project = runtime
    apply_candidate(vault, candidate(project), op_id=identity('op_', 'seed'))
    assert not compile_context(vault, vault, '', event='SessionStart', budget=1)['delivered']
    assert not compile_context(vault, tmp_path / 'other', '', event='SessionStart')['delivered']
    RuntimeConfig(vault).set_mode('OFF')
    assert not compile_context(vault, vault, '', event='SessionStart')['delivered']


@pytest.mark.parametrize('client', ['claude', 'codex'])
def test_native_bootstrap_flush_receipt_deduplicates(runtime, monkeypatch, capsys, client):
    from brain_eleven.runtime import launcher
    vault, _ = runtime
    RuntimeConfig(vault).set_mode('SHADOW')
    monkeypatch.setattr(launcher, 'ensure_service', lambda *a, **kw: True)
    calls = []
    def request(vault, route, payload, **kwargs):
        calls.append(payload)
        return {'status': 'SUCCESS', 'context': 'Türkçe bağlam', 'delivered': True}
    monkeypatch.setattr(launcher, 'request_service', request)
    for index in range(2):
        monkeypatch.setattr(sys, 'stdin', type('Input', (), {'buffer': io.BytesIO(json.dumps({'cwd': str(vault), 'session_id': 'same'}).encode())})())
        assert launcher.main(['--vault', str(vault), '--client', client, '--event', 'SessionStart']) == 0
        output = json.loads(capsys.readouterr().out)
        assert bool(output.get('hookSpecificOutput')) == (index == 0)
    assert len(calls) == 1 and calls[0]['event'] == 'SessionStart'


def test_startup_unavailable_warns_and_continues(runtime, monkeypatch):
    from brain_eleven.runtime import launcher
    vault, _ = runtime
    monkeypatch.setattr(launcher, 'ensure_service', lambda *a, **kw: False)
    assert 'systemMessage' in launcher.hook(vault, 'codex', 'SessionStart', {'cwd': str(vault), 'session_id': 's'})


def test_cold_native_session_start_delivers_v1_within_hook_budget(runtime):
    import os
    import subprocess
    import time
    from pathlib import Path
    from brain_eleven.runtime.install import hook_python
    from brain_eleven.runtime.launcher import request_service
    vault, project = runtime
    apply_candidate(vault, candidate(project), op_id=identity('op_', 'seed'))
    RuntimeConfig(vault).set_mode('SHADOW')
    command = [hook_python(), str(Path(__file__).resolve().parents[1] / 'brain_eleven/runtime/launcher.py'),
               '--vault', str(vault), '--client', 'codex', '--event', 'SessionStart']
    started = time.monotonic()
    try:
        result = subprocess.run(command, input=json.dumps({'cwd': str(vault), 'session_id': 'cold'}),
                                capture_output=True, text=True, encoding='utf-8', timeout=4,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert 'SQLite' in output['hookSpecificOutput']['additionalContext'], output
        assert time.monotonic() - started < 3
    finally:
        try:
            request_service(vault, '/api/runtime/stop', {}, timeout=2)
        except OSError:
            pass
        deadline = time.monotonic() + 5
        while (RuntimeConfig(vault).root / 'service.json').exists() and time.monotonic() < deadline:
            time.sleep(.1)


def test_install_suspends_only_exact_legacy_and_uninstall_restores(runtime, tmp_path):
    from brain_eleven.runtime.install import install, uninstall, client_paths
    vault, _ = runtime
    home = tmp_path / 'home'
    base = home.as_posix()
    wsl = '/mnt/' + base[0].lower() + base[2:] if len(base) > 1 and base[1] == ':' else base
    legacy = {'matcher': '*', 'hooks': [{'type': 'command', 'command': f'bash {base}/.claude/hooks/brain-eleven-session-start || bash {wsl}/.claude/hooks/brain-eleven-session-start'}]}
    unrelated = {'matcher': 'startup', 'hooks': [{'type': 'command', 'command': 'cbm-session-reminder'}]}
    original = {'hooks': {'SessionStart': [unrelated, legacy]}, 'theme': 'dark'}
    path = client_paths(home)['claude']
    write_json(path, original)
    install(vault, home=home, clients=('claude',))
    install(vault, home=home, clients=('claude',))
    current = read_json(path)
    assert unrelated in current['hooks']['SessionStart'] and legacy not in current['hooks']['SessionStart']
    uninstall(vault)
    assert read_json(path) == original
