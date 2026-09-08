"""Tests for the observable global SessionStart hook contract."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
HOOK = ROOT / 'templates' / 'claude' / 'hooks' / 'brain-eleven-session-start'
BASH = shutil.which('bash')
PYTHON3 = shutil.which('python3') or sys.executable

pytestmark = pytest.mark.skipif(
    not BASH,
    reason='SessionStart hook tests require bash',
)


def _bash_path(path: Path) -> str:
    value = str(path)
    if os.name != 'nt':
        return value
    drive, tail = os.path.splitdrive(value)
    tail = tail.replace('\\', '/')
    if BASH and 'system32' in BASH.lower():
        return f'/mnt/{drive[0].lower()}{tail}'
    return f'/{drive[0].lower()}{tail}' if drive else value


def _write_compiler(vault: Path, source: str) -> None:
    scripts = vault / 'scripts'
    scripts.mkdir(parents=True)
    (scripts / 'context-compiler.py').write_text(source, encoding='utf-8')


def _run_hook(vault: Path) -> subprocess.CompletedProcess:
    command = (
        f'export BRAIN_ELEVEN_VAULT={shlex.quote(_bash_path(vault))}; '
        f'export CLAUDE_PROJECT_DIR={shlex.quote(_bash_path(vault))}; '
        f'export PYTHON={shlex.quote(_bash_path(Path(PYTHON3)))}; '
        f'exec bash {shlex.quote(_bash_path(HOOK))}'
    )
    return subprocess.run(
        [BASH, '-c', command],
        text=True,
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )


def _result(vault: Path, completed: subprocess.CompletedProcess) -> dict:
    path = vault / '.claude' / 'session-run-result.json'
    if not path.exists():
        raise AssertionError(
            f'no breadcrumb; returncode={completed.returncode}; '
            f'stdout={completed.stdout!r}; stderr={completed.stderr!r}'
        )
    return json.loads(path.read_text(encoding='utf-8'))


def test_session_start_writes_success_breadcrumb(tmp_path):
    vault = tmp_path / 'vault'
    _write_compiler(
        vault,
        """
import sys
print('compiled context')
assert '--load-bootstrap' in sys.argv
""".strip(),
    )

    completed = _run_hook(vault)

    result = _result(vault, completed)
    assert completed.returncode == 0
    assert result['exit_status'] == 0
    assert result['branch'] == 'bootstrap'
    assert isinstance(result['duration'], int)
    assert result['error'] is None
    assert result['bootstrap_exit_status'] == 0
    assert 'compiled context' in completed.stdout


def test_session_start_writes_failure_breadcrumb_and_keeps_session_unblocked(tmp_path):
    vault = tmp_path / 'vault'
    _write_compiler(
        vault,
        """
import sys
print('secret prompt/context')
print('compiler failure: private context omitted', file=sys.stderr)
sys.exit(17)
""".strip(),
    )

    completed = _run_hook(vault)

    result = _result(vault, completed)
    assert completed.returncode == 0
    assert result['exit_status'] == 17
    assert result['branch'] == 'stdout_fallback'
    assert result['error'] == 'compiler failure: private context omitted'
    assert result['bootstrap_exit_status'] == 17
    assert 'secret prompt/context' not in json.dumps(result)


def test_doctor_reports_failed_session_start_and_returns_attention(tmp_path, monkeypatch):
    from brain_eleven.runtime import install

    vault = tmp_path / 'vault'
    result_path = vault / '.claude' / 'session-run-result.json'
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps({'timestamp': '2026-09-09T10:11:12Z', 'exit_status': 17}),
        encoding='utf-8',
    )
    monkeypatch.setattr(install, 'client_paths', lambda home=None: {})

    checks = install.doctor(vault)

    assert checks['last_session_start'] == 'last SessionStart: failed at 2026-09-09T10:11:12Z'
    assert checks['status'] == 'ATTENTION'

    from brain_eleven.__main__ import main

    assert main(['--vault', str(vault), 'doctor']) == 1
