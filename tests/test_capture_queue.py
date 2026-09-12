"""PRE-02 durable capture-queue contract tests."""

from __future__ import annotations

import json

import pytest

from capture_event import EVENT_SESSION_END, EVENT_USER_PROMPT_SUBMIT, parse_hook_event
from capture_queue import (
    CLAIMED,
    COMMITTED,
    DEAD_LETTER,
    PROCESSING,
    QUEUED,
    CaptureQueue,
    CaptureQueueConfig,
    CaptureQueueCorruptError,
    CaptureQueueFullError,
    CaptureQueueWriteError,
)
from project_registry import ProjectRegistry


def _session_event(vault, project_root, *, session_id="session_01J0000000000000000000000"):
    return parse_hook_event(
        {
            "event_type": EVENT_SESSION_END,
            "session_id": session_id,
            "project_root": str(project_root),
            "event_at": "2026-09-05T10:00:00Z",
            "transcript_path": "C:/local/transcripts/session.jsonl",
        },
        vault_path=vault,
    )


def _prompt_event(vault, project_root, *, prompt, session_id="session_01J0000000000000000000000"):
    return parse_hook_event(
        {
            "event_type": EVENT_USER_PROMPT_SUBMIT,
            "session_id": session_id,
            "project_root": str(project_root),
            "event_at": "2026-09-05T10:00:00Z",
            "prompt": prompt,
        },
        vault_path=vault,
    )


def test_enqueue_is_content_safe_idempotent_and_never_writes_canonical_stores(tmp_path):
    vault = tmp_path / "vault"
    project_root = tmp_path / "project"
    ProjectRegistry(vault).register(project_root, project_id="proj_capture")
    secret_prompt = "capture-secret-must-never-be-persisted"
    event = _prompt_event(vault, project_root, prompt=secret_prompt)
    queue = CaptureQueue(vault)

    first = queue.enqueue(event)
    second = queue.enqueue(event)

    assert first.status == QUEUED
    assert first.duplicate is False
    assert second.status == QUEUED
    assert second.duplicate is True
    assert first.job_id == second.job_id
    queued = list((vault / ".brain-eleven" / "capture" / "queued").glob("*.json"))
    assert len(queued) == 1
    persisted = queued[0].read_text(encoding="utf-8")
    ledger = (vault / ".brain-eleven" / "capture" / "capture-ledger.jsonl").read_text(encoding="utf-8")
    assert secret_prompt not in persisted
    assert secret_prompt not in ledger
    assert event.prompt_sha256 in persisted
    assert "transcript_content" not in persisted
    assert not (vault / ".claude" / "validated-memory.json").exists()
    assert not (vault / ".claude" / "project-state.json").exists()


def test_queue_backpressure_is_explicit_and_leaves_no_canonical_side_effect(tmp_path):
    vault = tmp_path / "vault"
    queue = CaptureQueue(vault, config=CaptureQueueConfig(max_queued_jobs=1))
    queue.enqueue(_session_event(vault, tmp_path / "project-a"))

    with pytest.raises(CaptureQueueFullError) as exc:
        queue.enqueue(
            _session_event(
                vault,
                tmp_path / "project-b",
                session_id="session_01J0000000000000000000001",
            )
        )

    assert exc.value.code == "CAPTURE_QUEUE_FULL"
    assert not (vault / ".claude" / "validated-memory.json").exists()
    assert not (vault / ".claude" / "project-state.json").exists()


def test_claim_process_and_commit_preserve_one_stable_job_identity(tmp_path):
    vault = tmp_path / "vault"
    queue = CaptureQueue(vault)
    receipt = queue.enqueue(_session_event(vault, tmp_path / "project"))

    claimed = queue.claim_next(now="2026-09-05T10:01:00Z")
    assert claimed is not None
    assert claimed["job_id"] == receipt.job_id
    assert claimed["status"] == CLAIMED
    assert claimed["attempt"] == 1
    processing = queue.start_processing(receipt.job_id)
    assert processing["status"] == PROCESSING
    completed = queue.commit(receipt.job_id)

    assert completed.status == COMMITTED
    path = queue.job_path(receipt.job_id)
    assert path is not None
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["job_id"] == receipt.job_id
    assert document["status"] == COMMITTED
    assert path.parent.name == "completed"


def test_claim_crash_before_rename_leaves_recoverable_claimed_job(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    queue = CaptureQueue(vault)
    receipt = queue.enqueue(_session_event(vault, tmp_path / "project"))
    original_move = queue._move

    def fail_before_rename(source, destination):
        raise CaptureQueueWriteError("simulated rename crash")

    monkeypatch.setattr(queue, "_move", fail_before_rename)
    with pytest.raises(CaptureQueueWriteError, match="simulated rename crash"):
        queue.claim_next(now="2026-09-05T10:01:00Z")

    queued = queue._job_path(QUEUED, receipt.job_id)
    document = json.loads(queued.read_text(encoding="utf-8"))
    assert document["status"] == CLAIMED
    assert document["attempt"] == 1

    monkeypatch.setattr(queue, "_move", original_move)
    claimed = queue.claim_next(now="2026-09-05T10:01:01Z")
    assert claimed is not None
    assert claimed["job_id"] == receipt.job_id
    assert claimed["status"] == CLAIMED
    assert claimed["attempt"] == 2


def test_claim_crash_after_rename_leaves_recoverable_processing_job(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    queue = CaptureQueue(vault, config=CaptureQueueConfig(lease_seconds=10))
    receipt = queue.enqueue(_session_event(vault, tmp_path / "project"))
    original_move = queue._move

    def move_then_crash(source, destination):
        original_move(source, destination)
        raise CaptureQueueWriteError("simulated post-rename crash")

    monkeypatch.setattr(queue, "_move", move_then_crash)
    with pytest.raises(CaptureQueueWriteError, match="simulated post-rename crash"):
        queue.claim_next(now="2026-09-05T10:01:00Z")

    processing = queue._job_path(CLAIMED, receipt.job_id)
    document = json.loads(processing.read_text(encoding="utf-8"))
    assert document["status"] == CLAIMED

    monkeypatch.setattr(queue, "_move", original_move)
    assert queue.recover_expired_claims(now="2026-09-05T10:01:11Z") == 1
    assert queue.job_path(receipt.job_id).parent.name == "queued"
    reclaimed = queue.claim_next(now="2026-09-05T10:01:12Z")
    assert reclaimed is not None
    assert reclaimed["job_id"] == receipt.job_id
    assert reclaimed["attempt"] == 2


@pytest.mark.parametrize("fail_after_rename", [False, True])
def test_retry_requeue_transition_is_crash_recoverable(tmp_path, monkeypatch, fail_after_rename):
    vault = tmp_path / "vault"
    queue = CaptureQueue(vault, config=CaptureQueueConfig(max_attempts=3))
    receipt = queue.enqueue(_session_event(vault, tmp_path / "project"))
    assert queue.claim_next(now="2026-09-05T10:00:00Z") is not None
    assert queue.start_processing(receipt.job_id)["status"] == PROCESSING
    original_move = queue._move

    def move_then_crash(source, destination):
        original_move(source, destination)
        raise CaptureQueueWriteError("simulated post-rename crash")

    def fail_before_rename(source, destination):
        raise CaptureQueueWriteError("simulated pre-rename crash")

    monkeypatch.setattr(queue, "_move", move_then_crash if fail_after_rename else fail_before_rename)
    with pytest.raises(CaptureQueueWriteError):
        queue.retry_or_dead_letter(receipt.job_id, error_code="TRANSCRIPT_NOT_FOUND")

    monkeypatch.setattr(queue, "_move", original_move)
    if fail_after_rename:
        assert queue.recover_expired_claims(now="2026-09-05T10:00:11Z") == 0
    else:
        processing = queue._job_path(CLAIMED, receipt.job_id)
        assert json.loads(processing.read_text(encoding="utf-8"))["status"] == QUEUED
        assert queue.recover_expired_claims(now="2026-09-05T10:00:11Z") == 1

    queued = queue.job_path(receipt.job_id)
    assert queued is not None and queued.parent.name == "queued"
    assert json.loads(queued.read_text(encoding="utf-8"))["status"] == QUEUED
    reclaimed = queue.claim_next(now="2026-09-05T10:00:12Z")
    assert reclaimed is not None
    assert reclaimed["job_id"] == receipt.job_id
    assert reclaimed["attempt"] == 2


@pytest.mark.parametrize("fail_after_rename", [False, True])
def test_retry_dead_letter_transition_is_crash_recoverable(tmp_path, monkeypatch, fail_after_rename):
    vault = tmp_path / "vault"
    queue = CaptureQueue(vault, config=CaptureQueueConfig(max_attempts=1))
    receipt = queue.enqueue(_session_event(vault, tmp_path / "project"))
    assert queue.claim_next(now="2026-09-05T10:00:00Z") is not None
    assert queue.start_processing(receipt.job_id)["status"] == PROCESSING
    original_move = queue._move

    def move_then_crash(source, destination):
        original_move(source, destination)
        raise CaptureQueueWriteError("simulated post-rename crash")

    def fail_before_rename(source, destination):
        raise CaptureQueueWriteError("simulated pre-rename crash")

    monkeypatch.setattr(queue, "_move", move_then_crash if fail_after_rename else fail_before_rename)
    with pytest.raises(CaptureQueueWriteError):
        queue.retry_or_dead_letter(receipt.job_id, error_code="TRANSCRIPT_NOT_FOUND")

    monkeypatch.setattr(queue, "_move", original_move)
    if fail_after_rename:
        assert queue.recover_expired_claims(now="2026-09-05T10:00:11Z") == 0
    else:
        processing = queue._job_path(CLAIMED, receipt.job_id)
        assert json.loads(processing.read_text(encoding="utf-8"))["status"] == DEAD_LETTER
        assert queue.recover_expired_claims(now="2026-09-05T10:00:11Z") == 1

    dead_letter = queue.job_path(receipt.job_id)
    assert dead_letter is not None and dead_letter.parent.name == "dead-letter"
    assert json.loads(dead_letter.read_text(encoding="utf-8"))["status"] == DEAD_LETTER


@pytest.mark.parametrize("max_attempts", [1, 3])
@pytest.mark.parametrize("fail_after_rename", [False, True])
def test_lease_recovery_transition_is_crash_recoverable(
    tmp_path, monkeypatch, max_attempts, fail_after_rename
):
    vault = tmp_path / "vault"
    queue = CaptureQueue(
        vault,
        config=CaptureQueueConfig(max_attempts=max_attempts, lease_seconds=10),
    )
    receipt = queue.enqueue(_session_event(vault, tmp_path / "project"))
    assert queue.claim_next(now="2026-09-05T10:00:00Z") is not None
    original_move = queue._move

    def move_then_crash(source, destination):
        original_move(source, destination)
        raise CaptureQueueWriteError("simulated post-rename crash")

    def fail_before_rename(source, destination):
        raise CaptureQueueWriteError("simulated pre-rename crash")

    monkeypatch.setattr(queue, "_move", move_then_crash if fail_after_rename else fail_before_rename)
    with pytest.raises(CaptureQueueWriteError):
        queue.recover_expired_claims(now="2026-09-05T10:00:11Z")

    monkeypatch.setattr(queue, "_move", original_move)
    if fail_after_rename:
        assert queue.recover_expired_claims(now="2026-09-05T10:00:12Z") == 0
    else:
        processing = queue._job_path(CLAIMED, receipt.job_id)
        expected_status = DEAD_LETTER if max_attempts == 1 else QUEUED
        assert json.loads(processing.read_text(encoding="utf-8"))["status"] == expected_status
        assert queue.recover_expired_claims(now="2026-09-05T10:00:12Z") == 1

    destination = queue.job_path(receipt.job_id)
    assert destination is not None
    expected_status = DEAD_LETTER if max_attempts == 1 else QUEUED
    assert destination.parent.name == ("dead-letter" if max_attempts == 1 else "queued")
    assert json.loads(destination.read_text(encoding="utf-8"))["status"] == expected_status
    if max_attempts > 1:
        reclaimed = queue.claim_next(now="2026-09-05T10:00:13Z")
        assert reclaimed is not None
        assert reclaimed["job_id"] == receipt.job_id
        assert reclaimed["attempt"] == 2


def test_retry_and_lease_recovery_are_bounded_and_content_safe(tmp_path):
    vault = tmp_path / "vault"
    queue = CaptureQueue(vault, config=CaptureQueueConfig(max_attempts=2, lease_seconds=10))
    receipt = queue.enqueue(_session_event(vault, tmp_path / "project"))

    assert queue.claim_next(now="2026-09-05T10:00:00Z") is not None
    assert queue.start_processing(receipt.job_id)["status"] == PROCESSING
    assert queue.retry_or_dead_letter(receipt.job_id, error_code="TRANSCRIPT_NOT_FOUND").status == QUEUED
    assert queue.claim_next(now="2026-09-05T10:01:00Z") is not None
    assert queue.start_processing(receipt.job_id)["status"] == PROCESSING
    assert queue.retry_or_dead_letter(receipt.job_id, error_code="TRANSCRIPT_NOT_FOUND").status == DEAD_LETTER
    assert queue.job_path(receipt.job_id).parent.name == "dead-letter"

    recovered = queue.enqueue(
        _session_event(
            vault,
            tmp_path / "project",
            session_id="session_01J0000000000000000000002",
        )
    )
    assert queue.claim_next(now="2026-09-05T10:10:00Z") is not None
    assert queue.recover_expired_claims(now="2026-09-05T10:10:11Z") == 1
    assert queue.job_path(recovered.job_id).parent.name == "queued"


def test_corrupt_job_is_never_treated_as_an_empty_queue(tmp_path):
    vault = tmp_path / "vault"
    queue = CaptureQueue(vault)
    queue._ensure_layout()
    corrupt = vault / ".brain-eleven" / "capture" / "queued" / "cap_corrupt.json"
    corrupt.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(CaptureQueueCorruptError) as exc:
        queue.claim_next()

    assert exc.value.code == "CAPTURE_QUEUE_CORRUPT"
    assert corrupt.exists()


def test_malformed_job_identity_cannot_escape_queue_directory(tmp_path):
    vault = tmp_path / "vault"
    queue = CaptureQueue(vault)
    queue._ensure_layout()
    corrupt = vault / ".brain-eleven" / "capture" / "queued" / "cap_corrupt.json"
    corrupt.write_text(json.dumps({
        "schema_version": 1,
        "job_id": "cap_../outside",
        "idempotency_key": "key",
        "status": QUEUED,
        "attempt": 0,
        "created_at": "2026-09-05T10:00:00Z",
        "event": {
            "schema_version": 1,
            "event_id": "evt_test",
            "idempotency_key": "key",
            "event_type": "SESSION_END",
            "session_id": "session_test",
            "project_root": str(tmp_path),
            "project": {"project_id": "project", "status": "resolved"},
            "event_at": "2026-09-05T10:00:00Z",
        },
    }), encoding="utf-8")

    with pytest.raises(CaptureQueueCorruptError) as exc:
        queue.claim_next()

    assert exc.value.code == "CAPTURE_QUEUE_CORRUPT"
    assert not (vault / ".brain-eleven" / "capture" / "outside.json").exists()


def test_job_semantic_identity_must_match_idempotency_key(tmp_path):
    vault = tmp_path / "vault"
    queue = CaptureQueue(vault)
    event = _session_event(vault, tmp_path / "project")
    job = queue._job_from_event(event)
    job["job_id"] = "cap_" + "0" * 32
    queue._ensure_layout()
    path = queue._job_path(QUEUED, job["job_id"])
    path.write_text(json.dumps(job), encoding="utf-8")

    with pytest.raises(CaptureQueueCorruptError, match="identity mismatch"):
        queue.claim_next()


def test_event_idempotency_must_match_job_identity(tmp_path):
    vault = tmp_path / "vault"
    queue = CaptureQueue(vault)
    event = _session_event(vault, tmp_path / "project")
    job = queue._job_from_event(event)
    job["event"]["idempotency_key"] = "different-event-key"
    queue._ensure_layout()
    path = queue._job_path(QUEUED, job["job_id"])
    path.write_text(json.dumps(job), encoding="utf-8")

    with pytest.raises(CaptureQueueCorruptError, match="idempotency identity mismatch"):
        queue.claim_next()


def test_bounded_1000_event_fast_path_drops_no_distinct_jobs(tmp_path):
    vault = tmp_path / "vault"
    queue = CaptureQueue(vault)
    for index in range(1000):
        event = _session_event(
            vault,
            tmp_path / "project",
            session_id=f"session_{index:024d}",
        )
        assert queue.enqueue(event).status == QUEUED

    queued = list((vault / ".brain-eleven" / "capture" / "queued").glob("*.json"))
    assert len(queued) == 1000
