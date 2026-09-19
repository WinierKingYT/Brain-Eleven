"""Cross-platform evidence for copied native-hook runtime boundaries."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime.capture_event import EVENT_SESSION_END, EVENT_USER_PROMPT_SUBMIT


ROOT = Path(__file__).resolve().parents[1]
COPIED_FILES = (
    "capture_event.py",
    "capture_queue.py",
    "project_registry.py",
    "memory_store_lock.py",
)


def _bootstrap_capture_scripts(vault: Path) -> Path:
    scripts = vault / "scripts"
    scripts.mkdir(parents=True)
    for name in COPIED_FILES:
        shutil.copy2(ROOT / "scripts" / name, scripts / name)
    return scripts / "capture_queue.py"


def _run_copied_queue(
    queue_script: Path,
    vault: Path,
    payload: dict[str, object],
    event_type: str,
    *,
    package_root: Path | None,
) -> subprocess.CompletedProcess[str]:
    caller = vault.parent / "external-caller"
    caller.mkdir(parents=True, exist_ok=True)

    environment = os.environ.copy()
    # The test must prove that the copied scripts do not accidentally resolve
    # this checkout through inherited interpreter configuration.
    for name in (
        "PYTHONPATH",
        "BRAIN_ELEVEN_ROOT",
        "BRAIN_ELEVEN_VAULT",
        "BRAIN_ELEVEN_VAULT_PATH",
    ):
        environment.pop(name, None)
    if package_root is not None:
        environment["BRAIN_ELEVEN_ROOT"] = str(package_root)

    return subprocess.run(
        [
            sys.executable,
            "-S",
            str(queue_script),
            "enqueue-hook",
            "--vault",
            str(vault),
            "--event-type",
            event_type,
            "--project-root",
            str(vault),
        ],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        cwd=caller,
        env=environment,
    )


@pytest.mark.parametrize("event_type", [EVENT_SESSION_END, EVENT_USER_PROMPT_SUBMIT])
def test_copied_queue_uses_explicit_package_root_outside_repository(tmp_path, event_type):
    vault = tmp_path / "vault"
    queue_script = _bootstrap_capture_scripts(vault)
    ProjectRegistry(vault).register(vault, project_id="proj_copied_hook")

    raw_prompt = "copied-hook prompt must never be persisted"
    payload: dict[str, object] = {
        "session_id": "session_01J0000000000000000000000",
        "cwd": str(vault),
        "timestamp": "2026-09-05T10:00:00Z",
    }
    if event_type == EVENT_SESSION_END:
        payload["transcript_path"] = str(tmp_path / "transcript.jsonl")
    else:
        payload["prompt"] = raw_prompt

    first = _run_copied_queue(
        queue_script,
        vault,
        payload,
        event_type,
        package_root=ROOT,
    )
    duplicate = _run_copied_queue(
        queue_script,
        vault,
        payload,
        event_type,
        package_root=ROOT,
    )

    assert first.returncode == 0, first.stderr
    assert duplicate.returncode == 0, duplicate.stderr
    first_result = json.loads(first.stdout)
    duplicate_result = json.loads(duplicate.stdout)
    assert first_result["status"] == "QUEUED"
    assert first_result["duplicate"] is False
    assert duplicate_result["status"] == "QUEUED"
    assert duplicate_result["duplicate"] is True

    queued = list((vault / ".brain-eleven" / "capture" / "queued").glob("*.json"))
    assert len(queued) == 1
    persisted = queued[0].read_text(encoding="utf-8")
    ledger = (vault / ".brain-eleven" / "capture" / "capture-ledger.jsonl").read_text(
        encoding="utf-8"
    )
    if event_type == EVENT_USER_PROMPT_SUBMIT:
        assert raw_prompt not in persisted
        assert raw_prompt not in ledger


def test_copied_queue_without_package_root_returns_content_free_fail_closed_error(tmp_path):
    vault = tmp_path / "vault"
    queue_script = _bootstrap_capture_scripts(vault)
    raw_prompt = "this prompt must not appear in a missing-runtime error"
    payload = {
        "session_id": "session_01J0000000000000000000000",
        "cwd": str(vault),
        "prompt": raw_prompt,
        "timestamp": "2026-09-05T10:00:00Z",
    }

    completed = _run_copied_queue(
        queue_script,
        vault,
        payload,
        EVENT_USER_PROMPT_SUBMIT,
        package_root=None,
    )

    assert completed.returncode == 2
    assert json.loads(completed.stdout) == {
        "error": {"code": "PROJECT_REGISTRY_UNAVAILABLE"}
    }
    assert raw_prompt not in completed.stdout
    assert raw_prompt not in completed.stderr
    assert not (vault / ".brain-eleven" / "capture").exists()
