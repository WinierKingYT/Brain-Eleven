"""IG-02 capture closure: receipt-verified worker effects and replay safety."""

from __future__ import annotations

import json

import pytest

from brain_eleven.memory import MemoryStore, MemoryStoreConflict
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime.migration import migrate
from brain_eleven.runtime.storage import RuntimeConfig, read_json, write_json, identity
from brain_eleven.runtime.worker import Worker, apply_candidate, enqueue
from brain_eleven.state import StateService, StateStore, StateStoreConflict
from evidence import EvidenceBatch
from brain_eleven.infrastructure.locking import MemoryStoreLockTimeout
from capture_queue import CaptureQueue


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
        "transcript_roots": {"claude": [str(tmp_path)], "codex": [str(tmp_path)]},
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


def test_receipt_failure_does_not_advance_checkpoint_or_ack_tampered_effect(runtime, tmp_path, monkeypatch):
    """A crash after canonical effects must replay from the old cursor safely."""
    import brain_eleven.runtime.worker as worker_module

    vault, project_id = runtime
    path = tmp_path / "multi.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({"type": "user", "message": {"role": "user", "content": text}})
            for text in (
                "We decided to use SQLite for persistent storage.",
                "We decided to use session cookies for authentication.",
            )
        ) + "\n",
        encoding="utf-8",
    )
    enqueue(vault, "claude", {"session_id": "receipt-window", "cwd": str(vault), "transcript_path": str(path)})
    original_read = worker_module.read_increment
    session = "claude:" + __import__("hashlib").sha256("receipt-window".encode()).hexdigest()
    full_batch, _ = original_read(vault, path, "claude", session, project_id, "2026-01-01T00:00:00+00:00")
    calls = {"index": 0}

    def chunked_read(_vault, _path, _client, _session, _project, _captured_at, cursor=None):
        if cursor is None:
            calls["index"] = 0
        index = calls["index"]
        calls["index"] += 1
        message = full_batch.messages[index]
        return EvidenceBatch((message.record,), (message,)), {
            "offset": index + 1,
            "prefix_hash": ("a" if index == 0 else "b") * 64,
            "has_more": index == 0,
        }

    monkeypatch.setattr(worker_module, "read_increment", chunked_read)
    worker = Worker(vault)
    original_write = worker._write_receipt
    failed = {"value": False}

    def fail_once(job, result):
        if not failed["value"]:
            failed["value"] = True
            raise OSError("simulated crash before receipt")
        return original_write(job, result)

    monkeypatch.setattr(worker, "_write_receipt", fail_once)
    first = worker.once()

    assert first["status"] == "QUEUED"
    assert not list((vault / ".brain-eleven" / "runtime" / "capture-receipts").glob("*.json"))
    assert not list((vault / ".brain-eleven" / "runtime" / "cursors").glob("*.json"))
    assert len(MemoryStore(vault).load()["validated_memory"]) == 2

    # Leave the operation receipt behind but remove its canonical records. A
    # retry must remain visible as a failure, never become a false completion.
    document = MemoryStore(vault).load()
    document["validated_memory"] = []
    write_json(MemoryStore(vault).path, document)
    second = worker.once()

    assert second["status"] == "QUEUED"
    assert not list((vault / ".brain-eleven" / "capture" / "completed").glob("*.json"))


def test_codex_worker_golden_path_records_verified_effect(runtime, tmp_path):
    path = tmp_path / "codex.jsonl"
    path.write_text(json.dumps({
        "type": "response_item",
        "payload": {"type": "message", "role": "user", "content": "We decided to use SQLite for Codex capture."},
    }) + "\n", encoding="utf-8")
    vault, _ = runtime

    enqueue(vault, "codex", {"session_id": "codex-golden", "cwd": str(vault), "transcript_path": str(path)})
    result = Worker(vault).once()

    assert result["status"] == "PROCESSED"
    assert result["effect_verified"] is True
    assert result["canonical_effect_count"] == 1
    assert len(MemoryStore(vault).load()["validated_memory"]) == 1


def test_state_mutation_worker_golden_path_records_verified_effect(runtime, tmp_path):
    vault, project_id = runtime
    path = _transcript(tmp_path, "The build is currently failing.")

    enqueue(vault, "claude", {"session_id": "state-golden", "cwd": str(vault), "transcript_path": str(path)})
    result = Worker(vault).once()

    assert result["status"] == "PROCESSED"
    assert result["effect_verified"] is True
    assert result["canonical_effect_count"] == 1
    state = StateStore(vault).load()
    project = state["projects"][project_id]
    assert len(project["blockers"]) == 1
    blocker_id = project["blockers"][0]["id"]
    assert result["effect_ids"] == [blocker_id]
    operation_id = result["canonical_operation_ids"][0]
    assert state["operation_receipts"][operation_id]["operation"] == "blocker_added"


def test_replay_rejects_missing_review_effect(runtime, tmp_path, monkeypatch):
    vault, _ = runtime
    path = _transcript(tmp_path, "Maybe we should use SQLite for storage.")
    enqueue(vault, "claude", {"session_id": "missing-review", "cwd": str(vault), "transcript_path": str(path)})
    worker = Worker(vault)
    monkeypatch.setattr(worker.queue, "commit", lambda *_args: (_ for _ in ()).throw(OSError("ack crash")))
    first = worker.once()
    assert first["status"] == "QUEUED"
    review_path = next((vault / ".brain-eleven" / "runtime" / "review").glob("rev_*.json"), None)
    assert review_path is not None
    review_path.unlink()
    monkeypatch.setattr(worker.queue, "commit", CaptureQueue(vault).commit)

    result = worker.once()

    assert result["status"] == "QUEUED"
    assert result["error"] == "CANONICAL_RECEIPT_MISMATCH"


def test_replay_rejects_tampered_review_candidate_identity(runtime, tmp_path, monkeypatch):
    vault, _ = runtime
    path = _transcript(tmp_path, "Maybe we should use SQLite for storage.")
    enqueue(vault, "claude", {"session_id": "tampered-review", "cwd": str(vault), "transcript_path": str(path)})
    worker = Worker(vault)
    monkeypatch.setattr(worker.queue, "commit", lambda *_args: (_ for _ in ()).throw(OSError("ack crash")))
    first = worker.once()
    assert first["status"] == "QUEUED"
    review_path = next((vault / ".brain-eleven" / "runtime" / "review").glob("rev_*.json"))
    review = read_json(review_path)
    review["candidate"]["candidate_id"] = "cand_tampered"
    write_json(review_path, review)
    monkeypatch.setattr(worker.queue, "commit", CaptureQueue(vault).commit)

    result = worker.once()

    assert result["status"] == "QUEUED"
    assert result["error"] == "CANONICAL_RECEIPT_MISMATCH"


def test_replay_rejects_tampered_review_source(runtime, tmp_path, monkeypatch):
    vault, _ = runtime
    path = _transcript(tmp_path, "Maybe we should use SQLite for storage.")
    enqueue(vault, "claude", {"session_id": "tampered-review-source", "cwd": str(vault), "transcript_path": str(path)})
    worker = Worker(vault)
    monkeypatch.setattr(worker.queue, "commit", lambda *_args: (_ for _ in ()).throw(OSError("ack crash")))
    first = worker.once()
    assert first["status"] == "QUEUED"
    review_path = next((vault / ".brain-eleven" / "runtime" / "review").glob("rev_*.json"))
    review = read_json(review_path)
    review["source"]["raw_prompt"] = "must never be persisted"
    write_json(review_path, review)
    monkeypatch.setattr(worker.queue, "commit", CaptureQueue(vault).commit)

    result = worker.once()

    assert result["status"] == "QUEUED"
    assert result["error"] == "CANONICAL_RECEIPT_MISMATCH"


@pytest.mark.parametrize("tampered_field", ["session_hash", "evidence_id"])
def test_replay_rejects_unbounded_review_source_ids(runtime, tmp_path, monkeypatch, tampered_field):
    vault, _ = runtime
    path = _transcript(tmp_path, "Maybe we should use SQLite for storage.")
    enqueue(vault, "claude", {"session_id": "tampered-review-ids-" + tampered_field, "cwd": str(vault), "transcript_path": str(path)})
    worker = Worker(vault)
    monkeypatch.setattr(worker.queue, "commit", lambda *_args: (_ for _ in ()).throw(OSError("ack crash")))
    first = worker.once()
    assert first["status"] == "QUEUED"
    review_path = next((vault / ".brain-eleven" / "runtime" / "review").glob("rev_*.json"))
    review = read_json(review_path)
    review["source"][tampered_field] = "raw transcript content"
    if tampered_field == "evidence_id":
        review["candidate"]["evidence_refs"] = [review["source"][tampered_field]]
    write_json(review_path, review)
    monkeypatch.setattr(worker.queue, "commit", CaptureQueue(vault).commit)

    result = worker.once()

    assert result["status"] == "QUEUED"
    assert result["error"] == "CANONICAL_RECEIPT_MISMATCH"


def test_replay_rejects_missing_state_record(runtime, tmp_path, monkeypatch):
    vault, project_id = runtime
    path = _transcript(tmp_path, "The build is currently failing.")
    enqueue(vault, "claude", {"session_id": "missing-state", "cwd": str(vault), "transcript_path": str(path)})
    worker = Worker(vault)
    monkeypatch.setattr(worker.queue, "commit", lambda *_args: (_ for _ in ()).throw(OSError("ack crash")))
    first = worker.once()
    assert first["status"] == "QUEUED"
    state_path = StateStore(vault).path
    state = StateStore(vault).load()
    state["projects"][project_id]["blockers"] = []
    write_json(state_path, state)
    monkeypatch.setattr(worker.queue, "commit", CaptureQueue(vault).commit)

    result = worker.once()

    assert result["status"] == "QUEUED"
    assert result["error"] == "CANONICAL_RECEIPT_MISMATCH"


def test_replay_rejects_tampered_state_operation(runtime, tmp_path, monkeypatch):
    vault, _ = runtime
    path = _transcript(tmp_path, "The build is currently failing.")
    enqueue(vault, "claude", {"session_id": "tampered-state-operation", "cwd": str(vault), "transcript_path": str(path)})
    worker = Worker(vault)
    monkeypatch.setattr(worker.queue, "commit", lambda *_args: (_ for _ in ()).throw(OSError("ack crash")))
    first = worker.once()
    assert first["status"] == "QUEUED"
    state_store = StateStore(vault)
    state = state_store.load()
    operation_id = next(iter(state["operation_receipts"]))
    state["operation_receipts"][operation_id]["operation"] = "bogus"
    write_json(state_store.path, state)
    monkeypatch.setattr(worker.queue, "commit", CaptureQueue(vault).commit)

    result = worker.once()

    assert result["status"] == "QUEUED"
    assert result["error"] == "CANONICAL_RECEIPT_MISMATCH"


def test_replay_allows_state_lifecycle_after_receipt(runtime, tmp_path, monkeypatch):
    vault, project_id = runtime
    path = _transcript(tmp_path, "The build is currently failing.")
    enqueue(vault, "claude", {"session_id": "state-lifecycle-replay", "cwd": str(vault), "transcript_path": str(path)})
    worker = Worker(vault)
    monkeypatch.setattr(worker.queue, "commit", lambda *_args: (_ for _ in ()).throw(OSError("ack crash")))
    first = worker.once()
    assert first["status"] == "QUEUED"
    state_store = StateStore(vault)
    state = state_store.load()
    blocker_id = state["projects"][project_id]["blockers"][0]["id"]
    StateService(vault).resolve_blocker(
        project_id,
        blocker_id=blocker_id,
        expected_revision=state["projects"][project_id]["revision"],
        source={"type": "user", "reference": "lifecycle-replay"},
    )
    monkeypatch.setattr(worker.queue, "commit", CaptureQueue(vault).commit)

    result = worker.once()

    assert result["status"] == "PROCESSED"
    assert result["receipt_replayed"] is True


def test_replay_rejects_tampered_state_record_provenance(runtime, tmp_path, monkeypatch):
    vault, project_id = runtime
    path = _transcript(tmp_path, "The build is currently failing.")
    enqueue(vault, "claude", {"session_id": "tampered-state-provenance", "cwd": str(vault), "transcript_path": str(path)})
    worker = Worker(vault)
    monkeypatch.setattr(worker.queue, "commit", lambda *_args: (_ for _ in ()).throw(OSError("ack crash")))
    first = worker.once()
    assert first["status"] == "QUEUED"
    state_store = StateStore(vault)
    state = state_store.load()
    state["projects"][project_id]["blockers"][0]["source"]["reference"] = "op_forged"
    write_json(state_store.path, state)
    monkeypatch.setattr(worker.queue, "commit", CaptureQueue(vault).commit)

    result = worker.once()

    assert result["status"] == "QUEUED"
    assert result["error"] == "CANONICAL_RECEIPT_MISMATCH"


def test_replay_rejects_cross_project_memory_effect(runtime, tmp_path, monkeypatch):
    vault, project_id = runtime
    other_root = tmp_path / "other-project"
    other_root.mkdir()
    other = ProjectRegistry(vault).register(other_root, proactive_capture=True)
    StateService(vault).init_project(other["project_id"], source={"type": "user", "reference": "ig02-foreign"})
    config = RuntimeConfig(vault).load()
    config["project_ids"].append(other["project_id"])
    write_json(RuntimeConfig(vault).path, config)
    foreign_candidate = {
        "candidate_id": "cand_foreign",
        "candidate_type": "NEW_MEMORY",
        "project_id": other["project_id"],
        "scope": "project",
        "content": "We decided to use PostgreSQL for foreign storage.",
        "memory_type": "decision",
        "commitment": "COMMITTED",
        "confidence": 0.97,
        "evidence_refs": ["evd_foreign"],
    }
    foreign_operation = identity("op_", foreign_candidate["candidate_id"], foreign_candidate["project_id"])
    foreign_result = apply_candidate(vault, foreign_candidate, op_id=foreign_operation)
    assert foreign_result["status"] == "SUCCESS"
    foreign_effect = foreign_result["decisions"][0]["successor_memory_id"]

    path = _transcript(tmp_path, "We decided to use SQLite for local storage.")
    enqueue(vault, "claude", {"session_id": "cross-project-replay", "cwd": str(vault), "transcript_path": str(path)})
    worker = Worker(vault)
    monkeypatch.setattr(worker.queue, "commit", lambda *_args: (_ for _ in ()).throw(OSError("ack crash")))
    first = worker.once()
    assert first["status"] == "QUEUED"
    receipt_path = next((vault / ".brain-eleven" / "runtime" / "capture-receipts").glob("*.json"))
    receipt = read_json(receipt_path)
    receipt["canonical_operation_ids"] = [foreign_operation]
    receipt["effect_ids"] = [foreign_effect]
    write_json(receipt_path, receipt)
    monkeypatch.setattr(worker.queue, "commit", CaptureQueue(vault).commit)

    result = worker.once()

    assert result["status"] == "QUEUED"
    assert result["error"] == "CANONICAL_RECEIPT_MISMATCH"


@pytest.mark.parametrize(
    ("text", "receipt_field"),
    [
        ("We decided to use SQLite for persistent storage.", "canonical_operation_ids"),
        ("Maybe we should use SQLite for storage.", "review_effect_ids"),
    ],
)
def test_replay_rejects_receipt_count_list_tampering(runtime, tmp_path, monkeypatch, text, receipt_field):
    vault, _ = runtime
    path = _transcript(tmp_path, text)
    enqueue(vault, "claude", {"session_id": "count-tamper-" + receipt_field, "cwd": str(vault), "transcript_path": str(path)})
    worker = Worker(vault)
    monkeypatch.setattr(worker.queue, "commit", lambda *_args: (_ for _ in ()).throw(OSError("ack crash")))
    first = worker.once()
    assert first["status"] == "QUEUED"
    receipt_path = next((vault / ".brain-eleven" / "runtime" / "capture-receipts").glob("*.json"))
    receipt = read_json(receipt_path)
    receipt[receipt_field] = []
    write_json(receipt_path, receipt)
    monkeypatch.setattr(worker.queue, "commit", CaptureQueue(vault).commit)

    result = worker.once()

    assert result["status"] == "QUEUED"
    assert result["error"] == "CAPTURE_RECEIPT_CORRUPT"


def test_worker_lock_timeout_is_bounded(runtime, tmp_path, monkeypatch):
    import brain_eleven.runtime.worker as worker_module

    class Locked:
        def __enter__(self):
            raise MemoryStoreLockTimeout("busy")

        def __exit__(self, *_args):
            return None

    vault, _ = runtime
    monkeypatch.setattr(worker_module, "file_lock", lambda *_args, **_kwargs: Locked())

    result = Worker(vault).once()

    assert result == {"status": "DEGRADED", "error": "WORKER_LOCK_TIMEOUT"}


def test_deleted_transcript_reaches_visible_dead_letter(runtime, tmp_path):
    vault, _ = runtime
    path = _transcript(tmp_path)
    enqueue(vault, "claude", {"session_id": "deleted", "cwd": str(vault), "transcript_path": str(path)})
    path.unlink()

    results = [Worker(vault).once() for _ in range(3)]

    assert [item["status"] for item in results] == ["QUEUED", "QUEUED", "DEAD_LETTER"]
    assert results[-1]["error"] == "TRANSCRIPT_NOT_FOUND"
    assert list((vault / ".brain-eleven" / "capture" / "dead-letter").glob("*.json"))


def test_corrupt_transcript_reaches_visible_dead_letter(runtime, tmp_path):
    vault, _ = runtime
    path = _transcript(tmp_path)
    enqueue(vault, "claude", {"session_id": "corrupt", "cwd": str(vault), "transcript_path": str(path)})
    path.write_text("{not-json\n", encoding="utf-8")

    results = [Worker(vault).once() for _ in range(3)]

    assert [item["status"] for item in results] == ["QUEUED", "QUEUED", "DEAD_LETTER"]
    assert results[-1]["error"] == "EVIDENCE_INVALID"


def test_worker_memory_cas_conflict_is_retryable(runtime, tmp_path, monkeypatch):
    vault, _ = runtime
    path = _transcript(tmp_path)
    enqueue(vault, "claude", {"session_id": "memory-conflict", "cwd": str(vault), "transcript_path": str(path)})
    worker = Worker(vault)
    monkeypatch.setattr(worker, "process", lambda _job: (_ for _ in ()).throw(MemoryStoreConflict(1, 2)))

    result = worker.once()

    assert result["status"] == "QUEUED"
    assert result["error"] == "CANONICAL_CONFLICT"


def test_worker_state_conflict_is_retryable(runtime, tmp_path, monkeypatch):
    vault, _ = runtime
    path = _transcript(tmp_path)
    enqueue(vault, "claude", {"session_id": "state-conflict", "cwd": str(vault), "transcript_path": str(path)})
    worker = Worker(vault)
    monkeypatch.setattr(worker, "process", lambda _job: (_ for _ in ()).throw(StateStoreConflict("project", 1, 2)))

    result = worker.once()

    assert result["status"] == "QUEUED"
    assert result["error"] == "CANONICAL_CONFLICT"


def test_invalid_project_job_is_retryable_and_never_completed(runtime, tmp_path):
    vault, _ = runtime
    path = _transcript(tmp_path)
    receipt = enqueue(vault, "claude", {"session_id": "invalid-project", "cwd": str(vault), "transcript_path": str(path)})
    queue = CaptureQueue(vault)
    job_path = queue.job_path(receipt["job_id"])
    document = read_json(job_path)
    document["event"]["project"]["project_id"] = "proj_foreign"
    write_json(job_path, document)

    result = Worker(vault).once()

    assert result["status"] == "QUEUED"
    assert result["error"] == "SCOPE_DISABLED"
    assert not list((vault / ".brain-eleven" / "capture" / "completed").glob("*.json"))


def test_replay_rejects_receipt_with_foreign_project(runtime, tmp_path, monkeypatch):
    vault, _ = runtime
    path = _transcript(tmp_path)
    enqueue(vault, "claude", {"session_id": "foreign-receipt", "cwd": str(vault), "transcript_path": str(path)})
    worker = Worker(vault)
    monkeypatch.setattr(worker.queue, "commit", lambda *_args: (_ for _ in ()).throw(OSError("ack crash")))
    worker.once()
    receipt_path = next((vault / ".brain-eleven" / "runtime" / "capture-receipts").glob("*.json"))
    receipt = read_json(receipt_path)
    receipt["project_id"] = "proj_foreign"
    write_json(receipt_path, receipt)
    monkeypatch.setattr(worker.queue, "commit", CaptureQueue(vault).commit)

    result = worker.once()

    assert result["status"] == "QUEUED"
    assert result["error"] == "CAPTURE_RECEIPT_IDENTITY_MISMATCH"


def test_replay_rejects_tampered_memory_operation_receipt(runtime, tmp_path, monkeypatch):
    vault, _ = runtime
    path = _transcript(tmp_path)
    enqueue(vault, "claude", {"session_id": "tampered-operation", "cwd": str(vault), "transcript_path": str(path)})
    worker = Worker(vault)
    monkeypatch.setattr(worker.queue, "commit", lambda *_args: (_ for _ in ()).throw(OSError("ack crash")))
    worker.once()
    document = MemoryStore(vault).load()
    operation_id = next(iter(document["operation_receipts"]))
    document["operation_receipts"][operation_id]["decisions"] = []
    write_json(MemoryStore(vault).path, document)
    monkeypatch.setattr(worker.queue, "commit", CaptureQueue(vault).commit)

    result = worker.once()

    assert result["status"] == "QUEUED"
    assert result["error"] == "CANONICAL_RECEIPT_MISMATCH"


def test_replay_rejects_tampered_memory_effect_ids(runtime, tmp_path, monkeypatch):
    vault, _ = runtime
    path = _transcript(tmp_path)
    enqueue(vault, "claude", {"session_id": "tampered-memory-effects", "cwd": str(vault), "transcript_path": str(path)})
    worker = Worker(vault)
    monkeypatch.setattr(worker.queue, "commit", lambda *_args: (_ for _ in ()).throw(OSError("ack crash")))
    first = worker.once()
    assert first["status"] == "QUEUED"
    receipt_path = next((vault / ".brain-eleven" / "runtime" / "capture-receipts").glob("*.json"))
    receipt = read_json(receipt_path)
    receipt["effect_ids"] = ["mem_forged_effect"]
    write_json(receipt_path, receipt)
    monkeypatch.setattr(worker.queue, "commit", CaptureQueue(vault).commit)

    result = worker.once()

    assert result["status"] == "QUEUED"
    assert result["error"] == "CANONICAL_RECEIPT_MISMATCH"

