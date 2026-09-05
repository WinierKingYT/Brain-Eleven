"""Regression coverage for the PRE-02 bounded hook hand-off contracts."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
SESSION_END_HOOK = ROOT / ".claude" / "hooks" / "session-end.sh"
PROMPT_HOOK = ROOT / ".claude" / "hooks" / "prompt-counter.sh"
BASH = shutil.which("bash")
PYTHON3 = shutil.which("python3")


pytestmark = pytest.mark.skipif(
    not BASH or not PYTHON3,
    reason="hook hand-off contracts require bash and python3",
)


def _bootstrap_capture_scripts(vault: Path) -> None:
    scripts = vault / "scripts"
    scripts.mkdir(parents=True)
    for name in ("capture_event.py", "capture_queue.py", "project_registry.py", "memory_store_lock.py"):
        shutil.copy2(ROOT / "scripts" / name, scripts / name)


def _bash_path(path: Path) -> str:
    """Translate paths only for Windows' WSL launcher, not Git Bash."""
    value = str(path)
    if os.name != "nt" or not BASH or "system32" not in BASH.lower():
        return value
    drive, tail = os.path.splitdrive(value)
    tail = tail.replace("\\", "/")
    return f"/mnt/{drive[0].lower()}{tail}"


def _run_hook(hook: Path, vault: Path, payload: dict) -> subprocess.CompletedProcess:
    vault_path = _bash_path(vault)
    command = (
        f"export BRAIN_ELEVEN_VAULT={shlex.quote(vault_path)}; "
        f"export CLAUDE_PROJECT_DIR={shlex.quote(vault_path)}; "
        f"export PYTHON={shlex.quote(PYTHON3)}; "
        f"exec bash {shlex.quote(_bash_path(hook))}"
    )
    return subprocess.run(
        [BASH, "-c", command],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )


def test_session_end_queues_one_event_without_running_the_legacy_pipeline(tmp_path):
    vault = tmp_path / "vault"
    _bootstrap_capture_scripts(vault)
    payload = {
        "session_id": "session_01J0000000000000000000000",
        "cwd": str(vault),
        "transcript_path": "C:/local/transcripts/session.jsonl",
        "timestamp": "2026-09-05T10:00:00Z",
    }

    completed = _run_hook(SESSION_END_HOOK, vault, payload)
    duplicate = _run_hook(SESSION_END_HOOK, vault, payload)

    queued = list((vault / ".brain-eleven" / "capture" / "queued").glob("*.json"))
    assert completed.returncode == 0
    assert duplicate.returncode == 0
    assert "capture event queued" in completed.stderr
    assert len(queued) == 1
    assert not (vault / ".claude" / "session-run-result.json").exists()
    assert not (vault / ".claude" / "hook-execution.log").exists()
    assert not (vault / ".claude" / "compiled-memory.json").exists()


def test_prompt_hook_hashes_prompt_before_queueing_and_never_runs_counter(tmp_path):
    vault = tmp_path / "vault"
    _bootstrap_capture_scripts(vault)
    raw_prompt = "This raw hook prompt must never enter the capture spool."
    payload = {
        "session_id": "session_01J0000000000000000000000",
        "cwd": str(vault),
        "prompt": raw_prompt,
        "timestamp": "2026-09-05T10:00:00Z",
    }

    completed = _run_hook(PROMPT_HOOK, vault, payload)

    queued = list((vault / ".brain-eleven" / "capture" / "queued").glob("*.json"))
    assert completed.returncode == 0
    assert "capture event queued" in completed.stderr
    assert len(queued) == 1
    persisted = queued[0].read_text(encoding="utf-8")
    ledger = (vault / ".brain-eleven" / "capture" / "capture-ledger.jsonl").read_text(encoding="utf-8")
    assert raw_prompt not in persisted
    assert raw_prompt not in ledger
    assert not (vault / ".claude" / "prompt-counter-state.json").exists()


def test_malformed_hook_payload_fails_safe_without_creating_a_job(tmp_path):
    vault = tmp_path / "vault"
    _bootstrap_capture_scripts(vault)
    raw_prompt = "do not print this malformed evidence"

    completed = _run_hook(SESSION_END_HOOK, vault, {"session_id": "bad session", "prompt": raw_prompt})

    assert completed.returncode == 0
    assert "capture event was not queued" in completed.stderr
    assert raw_prompt not in completed.stderr
    assert not (vault / ".brain-eleven" / "capture" / "queued").exists()
