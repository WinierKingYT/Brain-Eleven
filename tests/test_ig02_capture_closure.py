"""IG-02 capture closure: receipt-verified worker effects and replay safety."""

from __future__ import annotations

import json

import pytest

from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime.migration import migrate
from brain_eleven.runtime.storage import RuntimeConfig, read_json, write_json, identity
from brain_eleven.runtime.worker import Worker, enqueue
from brain_eleven.state import StateService


@pytest.fixture
def runtime(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    StateService(vault).init_project(project["project_id"], source={"type": "user", "reference": "ig02-test"})
    migrate(vault)
    write_json(RuntimeConfig(vault).path, {
        "schema_version": 1,
        "mode": "CANARY",
        "project_ids": [project["project_id"]],
        "local_model": None,
    })
    return vault, project["project_id"]


def _transcript(tmp_path, text="We decided to use SQLite for persistent storage."):
    path = tmp_path / "session.jsonl"
    path.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n", encoding="utf-8")
    return path


def test_queue_ack_requires_verified_effect_receipt(runtime, tmp_path, monkeypatch):
    vault, _ = runtime
    path = _transcript(tmp_path)
    enqueue(vault, "claude", {"session_id": "unverified", "cwd": str(vault), "transcript_path": str(path)})
    worker = Worker(vault)
    monkeypatch.setattr(worker, "process", lambda _job: {"status": "SCOPE_DISABLED", "job_id": "unknown"})

    result = worker.once()

    assert result["status"] == "QUEUED"
    assert not list((vault / ".brain-eleven" / "capture" / "completed").glob("*.json"))
    assert not list((vault / ".brain-eleven" / "runtime" / "capture-receipts").glob("*.json"))


def test_effect_receipt_allows_replay_after_crash_before_queue_ack(runtime, tmp_path, monkeypatch):
    vault, _ = runtime
    path = _transcript(tmp_path)
    enqueue(vault, "claude", {"session_id": "ack-crash", "cwd": str(vault), "transcript_path": str(path)})
    worker = Worker(vault)
    original_commit = worker.queue.commit
    monkeypatch.setattr(worker.queue, "commit", lambda *_args: (_ for _ in ()).throw(OSError("simulated ack crash")))

    first = worker.once()

    assert first["status"] == "QUEUED"
    receipts = list((vault / ".brain-eleven" / "runtime" / "capture-receipts").glob("*.json"))
    assert len(receipts) == 1
    receipt = read_json(receipts[0])
    assert receipt["status"] == "EFFECT_VERIFIED"
    assert receipt["canonical_verified"] is True
    assert len(MemoryStore(vault).load()["validated_memory"]) == 1

    monkeypatch.setattr(worker.queue, "commit", original_commit)
    second = worker.once()

    assert second["status"] == "PROCESSED"
    assert second["receipt_replayed"] is True
    assert len(MemoryStore(vault).load()["validated_memory"]) == 1
    assert len(list((vault / ".brain-eleven" / "capture" / "completed").glob("*.json"))) == 1


def test_corrupt_effect_receipt_is_retryable_and_never_acknowledged(runtime, tmp_path, monkeypatch):
    vault, _ = runtime
    path = _transcript(tmp_path)
    enqueue(vault, "claude", {"session_id": "bad-receipt", "cwd": str(vault), "transcript_path": str(path)})
    worker = Worker(vault)
    monkeypatch.setattr(worker.queue, "commit", lambda *_args: (_ for _ in ()).throw(OSError("simulated ack crash")))
    worker.once()
    receipt_path = next((vault / ".brain-eleven" / "runtime" / "capture-receipts").glob("*.json"))
    write_json(receipt_path, {"status": "EFFECT_VERIFIED", "canonical_verified": True})
    monkeypatch.setattr(worker.queue, "commit", Worker(vault).queue.commit)

    result = worker.once()

    assert result["status"] == "QUEUED"
    assert not list((vault / ".brain-eleven" / "capture" / "completed").glob("*.json"))


def test_crash_before_canonical_write_is_retryable_without_receipt(runtime, tmp_path, monkeypatch):
    vault, _ = runtime
    path = _transcript(tmp_path)
    enqueue(vault, "claude", {"session_id": "before-write", "cwd": str(vault), "transcript_path": str(path)})
    monkeypatch.setattr(
        "brain_eleven.runtime.worker.apply_candidate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("simulated canonical write crash")),
    )

    result = Worker(vault).once()

    assert result["status"] == "QUEUED"
    assert not list((vault / ".brain-eleven" / "capture" / "completed").glob("*.json"))
    assert not list((vault / ".brain-eleven" / "runtime" / "capture-receipts").glob("*.json"))
    assert not MemoryStore(vault).load()["validated_memory"]


def test_native_session_end_golden_path_records_effect_and_receipt(runtime, tmp_path, monkeypatch):
    from brain_eleven.runtime import launcher

    vault, _ = runtime
    path = _transcript(tmp_path, "We decided to use session cookies for PromtGen authentication.")
    monkeypatch.setattr(launcher, "ensure_service", lambda *_args, **_kwargs: True)

    assert launcher.hook(vault, "claude", "SessionEnd", {
        "session_id": "native-golden",
        "cwd": str(vault),
        "transcript_path": str(path),
    }) == {}
    result = Worker(vault).once()

    assert result["status"] == "PROCESSED"
    assert result["effect_verified"] is True
    assert result["canonical_effect_count"] == 1
    assert len(MemoryStore(vault).load()["validated_memory"]) == 1
    receipt = next((vault / ".brain-eleven" / "runtime" / "capture-receipts").glob("*.json"))
    rendered = receipt.read_text(encoding="utf-8")
    assert "PromtGen" not in rendered
    assert "session cookies" not in rendered


def test_missing_transcript_is_bounded_and_does_not_enqueue(runtime):
    vault, _ = runtime

    result = enqueue(vault, "codex", {
        "session_id": "missing",
        "cwd": str(vault),
        "transcript_path": str(vault / "missing.jsonl"),
    })

    assert result == {"status": "DEGRADED", "error": "TRANSCRIPT_NOT_FOUND"}

