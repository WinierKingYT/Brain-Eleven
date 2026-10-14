"""Context profiles: normal, economical, manual (owner request 2026-10-14)."""

import pytest

from brain_eleven.__main__ import main
from brain_eleven.runtime import launcher
from brain_eleven.runtime.storage import ECONOMICAL_SESSION_CHARS, ECONOMICAL_SUBAGENT_CHARS, RuntimeConfig
from tests.test_pre13_runtime import runtime  # noqa: F401  (fixture)

LONG = '## Hafıza\n' + '- uzun bir hafıza satırı burada duruyor.\n' * 200


@pytest.fixture
def service(monkeypatch):
    calls = []
    monkeypatch.setattr(launcher, 'ensure_service', lambda *a, **k: True)

    def request(vault, route, payload=None, timeout=.35):
        calls.append(payload)
        return {'delivery_approved': True, 'delivered': True, 'provider': 'V1', 'context': LONG, 'status': 'SUCCESS'}
    monkeypatch.setattr(launcher, 'request_service', request)
    return calls


def _hook(vault, event, **extra):
    payload = {'session_id': 's', 'cwd': str(vault), 'prompt': 'soru', **extra}
    result = launcher.hook(vault, 'claude', event, payload)
    return result[0] if isinstance(result, tuple) else result


def _context(output):
    return (output.get('hookSpecificOutput') or {}).get('additionalContext', '')


def test_default_profile_is_normal_and_unchanged(runtime, service):  # noqa: F811
    vault, _ = runtime
    assert RuntimeConfig(vault).load()['context_profile'] == 'normal'
    assert _context(_hook(vault, 'SessionStart')) == LONG
    assert _context(_hook(vault, 'UserPromptSubmit', turn_id='t1')) == LONG


def test_context_is_cut_at_a_line_under_the_client_limit():
    text = '## Seni tanıma\n' + 'x' * 50 + '\n' + 'satır\n' * 3000
    cut = launcher.fit_context(text, launcher.CLIENT_CONTEXT_CHARS)
    assert len(cut) <= launcher.CLIENT_CONTEXT_CHARS and cut.startswith('## Seni tanıma')
    assert cut.endswith('(bağlam kısaltıldı)')
    assert launcher.fit_context('kısa', 100) == 'kısa'


def test_economical_gives_a_short_session_start_and_no_prompt_context(runtime, service):  # noqa: F811
    vault, _ = runtime
    RuntimeConfig(vault).set_context_profile('economical')
    assert len(_context(_hook(vault, 'SessionStart'))) <= ECONOMICAL_SESSION_CHARS
    calls = len(service)
    assert _hook(vault, 'UserPromptSubmit', turn_id='t2') == {}
    assert len(service) == calls  # nothing compiled for the prompt
    sub = _context(_hook(vault, 'SubagentStart', agent_id='a1'))
    assert sub.endswith(launcher.SUBAGENT_INSTRUCTION)
    assert len(sub) <= ECONOMICAL_SUBAGENT_CHARS + len(launcher.SUBAGENT_INSTRUCTION) + 2


def test_manual_injects_nothing(runtime, service):  # noqa: F811
    vault, _ = runtime
    RuntimeConfig(vault).set_context_profile('manual')
    assert _hook(vault, 'SessionStart') == {}
    assert _hook(vault, 'UserPromptSubmit', turn_id='t3') == {}
    assert _hook(vault, 'SubagentStart', agent_id='a1') == {}
    assert service == []


def test_invalid_profile_is_rejected(runtime):  # noqa: F811
    vault, _ = runtime
    with pytest.raises(ValueError):
        RuntimeConfig(vault).set_context_profile('turbo')


def test_profile_cli_shows_and_sets(runtime, capsys):  # noqa: F811
    vault, _ = runtime
    assert main(['--vault', str(vault), 'profile', 'economical']) == 0
    assert '"economical"' in capsys.readouterr().out
    assert main(['--vault', str(vault), 'profile']) == 0
    assert '"economical"' in capsys.readouterr().out
