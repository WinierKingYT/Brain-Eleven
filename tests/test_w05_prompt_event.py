"""W-05 prompt-event terminal and zero-effect tests."""

from __future__ import annotations

import pytest

from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime.migration import migrate
from brain_eleven.runtime.storage import RuntimeConfig, write_json
from brain_eleven.runtime.worker import Worker
from brain_eleven.state import StateService, StateStore
from capture_event import EVENT_USER_PROMPT_SUBMIT, parse_hook_event
from capture_queue import CaptureQueue


@pytest.fixture
def runtime(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    StateService(vault).init_project(project["project_id"], source={"type": "user", "reference": "w05"})
    migrate(vault)
    write_json(RuntimeConfig(vault).path, {
        "schema_version": 1,
        "mode": "CANARY",
        "project_ids": [project["project_id"]],
        "local_model": None,
    })
    return vault, project["project_id"]


def _prompt_event(vault, project_id, text="raw prompt must not persist"):
    return parse_hook_event({
        "event_type": EVENT_USER_PROMPT_SUBMIT,
        "session_id": "prompt-session",
        "project_root": str(vault),
        "event_at": "2026-09-12T10:00:00Z",
        "prompt": text,
    }, vault_path=vault)


def test_prompt_event_commits_zero_effect_receipt_without_dead_letter(runtime):
    vault, project_id = runtime
    event = _prompt_event(vault, project_id)
    receipt = CaptureQueue(vault).enqueue(event)

    result = Worker(vault).once()

    assert result["status"] == "PROCESSED"
    assert result["job_id"] == receipt.job_id
    assert result["canonical_effect_count"] == 0
    assert result["review_effect_count"] == 0
    assert list((vault / ".brain-eleven" / "capture" / "completed").glob("*.json"))
    assert not list((vault / ".brain-eleven" / "capture" / "dead-letter").glob("*.json"))
    assert not MemoryStore(vault).load()["validated_memory"]
    assert not StateStore(vault).load()["projects"][project_id]["work_items"]
    receipt_path = next((vault / ".brain-eleven" / "runtime" / "capture-receipts").glob("*.json"))
    rendered = receipt_path.read_text(encoding="utf-8")
    assert "raw prompt must not persist" not in rendered


def test_prompt_event_replays_after_ack_crash_without_effect(runtime, monkeypatch):
    vault, project_id = runtime
    event = _prompt_event(vault, project_id, "replay raw prompt")
    queue = CaptureQueue(vault)
    receipt = queue.enqueue(event)
    worker = Worker(vault)
    original_commit = worker.queue.commit
    monkeypatch.setattr(worker.queue, "commit", lambda *_args: (_ for _ in ()).throw(OSError("ack crash")))

    first = worker.once()

    assert first["status"] == "QUEUED"
    assert len(list((vault / ".brain-eleven" / "runtime" / "capture-receipts").glob("*.json"))) == 1
    assert not MemoryStore(vault).load()["validated_memory"]

    monkeypatch.setattr(worker.queue, "commit", original_commit)
    second = worker.once()

    assert second["status"] == "PROCESSED"
    assert second["receipt_replayed"] is True
    assert second["job_id"] == receipt.job_id
    ledger = (vault / ".brain-eleven" / "capture" / "capture-ledger.jsonl").read_text(encoding="utf-8")
    assert "replay raw prompt" not in ledger
