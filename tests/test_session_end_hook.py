"""Regression coverage for the SessionEnd shell hand-off contract."""

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
HOOK = ROOT / ".claude" / "hooks" / "session-end.sh"
BASH = shutil.which("bash")
PYTHON3 = shutil.which("python3")


pytestmark = pytest.mark.skipif(
    not BASH or not PYTHON3,
    reason="SessionEnd hook contract requires bash and python3",
)


def _write_runner(vault: Path, source: str) -> None:
    scripts = vault / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "session_pipeline.py").write_text(source, encoding="utf-8")


def _bash_path(path: Path) -> str:
    """Translate paths only for Windows' WSL launcher, not Git Bash."""
    value = str(path)
    if os.name != "nt" or not BASH or "system32" not in BASH.lower():
        return value
    drive, tail = os.path.splitdrive(value)
    tail = tail.replace("\\", "/")
    return f"/mnt/{drive[0].lower()}{tail}"


def _run_hook(vault: Path) -> subprocess.CompletedProcess:
    vault_path = _bash_path(vault)
    command = (
        f"export BRAIN_ELEVEN_VAULT={shlex.quote(vault_path)}; "
        f"export CLAUDE_PROJECT_DIR={shlex.quote(vault_path)}; "
        f"exec bash {shlex.quote(_bash_path(HOOK))}"
    )
    return subprocess.run(
        [BASH, "-c", command],
        text=True,
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )


def test_session_end_refuses_stale_result_when_runner_did_not_write_this_run(tmp_path):
    vault = tmp_path / "vault"
    claude = vault / ".claude"
    claude.mkdir(parents=True)
    (claude / "session-run-result.json").write_text(
        json.dumps({"run_id": "run-old", "status": "SUCCESS", "steps": []}),
        encoding="utf-8",
    )
    _write_runner(
        vault,
        "import json\nprint(json.dumps({'run_id': 'run-new', 'status': 'SUCCESS'}))\n",
    )

    completed = _run_hook(vault)

    assert completed.returncode == 0
    assert "Run result is unreadable; no step is reported as successful" in completed.stderr
    assert "Session pipeline complete" not in completed.stderr
    assert not (claude / "hook-execution.log").exists()


def test_session_end_accepts_only_the_matching_run_result(tmp_path):
    vault = tmp_path / "vault"
    _write_runner(
        vault,
        "\n".join(
            [
                "import json",
                "from pathlib import Path",
                "result_path = Path(__file__).resolve().parents[1] / '.claude' / 'session-run-result.json'",
                "result_path.parent.mkdir(parents=True, exist_ok=True)",
                "result_path.write_text(json.dumps({'run_id': 'run-new', 'status': 'SUCCESS', 'steps': []}), encoding='utf-8')",
                "print(json.dumps({'run_id': 'run-new', 'status': 'SUCCESS'}))",
            ]
        )
        + "\n",
    )

    completed = _run_hook(vault)

    assert completed.returncode == 0
    assert "Session pipeline complete: run-new" in completed.stderr
    assert "run-new" in (vault / ".claude" / "hook-execution.log").read_text(encoding="utf-8")
