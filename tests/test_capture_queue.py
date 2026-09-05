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
