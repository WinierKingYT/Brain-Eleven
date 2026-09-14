"""W-02 terminal closure fault injection; existing queue/IG-02 tests stay intact."""

import json

import pytest

from brain_eleven.memory import MemoryStore
from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime.migration import migrate
from brain_eleven.runtime.storage import RuntimeConfig, read_json, write_json
from brain_eleven.runtime.worker import Worker, enqueue
from brain_eleven.state import StateService, StateStore
from scripts import capture_queue as module
from scripts.capture_event import EVENT_SESSION_END, parse_hook_event
from scripts.capture_queue import (
    CLAIMED, COMMITTED, PROCESSING, QUEUED, CaptureQueue,
    CaptureQueueCorruptError,
)


NOW = "2026-09-14T12:00:00Z"
LATER = "2026-09-14T13:00:00Z"


class Crash(BaseException):
    """Exit without entering the worker's ordinary Exception retry handler."""


@pytest.fixture
def queued(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    ProjectRegistry(vault).register(vault, proactive_capture=True)
    event = parse_hook_event({
        "event_type": EVENT_SESSION_END,
        "session_id": "private-session-w02",
        "project_root": str(vault),
        "event_at": NOW,
        "transcript_path": "C:/private/transcript.jsonl",
    }, vault_path=vault)
    queue = CaptureQueue(vault)
    receipt = queue.enqueue(event)
    queue.claim_next(now=NOW)
    queue.start_processing(receipt.job_id)
    return queue, event, receipt.job_id


def _terminal_records(queue):
    return [json.loads(line) for line in queue.ledger_path.read_text().splitlines()
            if json.loads(line)["action"] == "COMMITTED"]


def _assert_closed(queue, event, job_id):
    path = queue.job_path(job_id)
    assert path.parent.name == "completed"
    job = queue._read_job(path)
    assert job["status"] == COMMITTED
    assert job["committed_at"]
    assert job["idempotency_key"] == event.idempotency_key
    assert len(_terminal_records(queue)) == 1
    assert not list(queue._directory(CLAIMED).glob("*.json"))
    before = path.read_bytes(), queue.ledger_path.read_bytes()
    assert queue.recover_expired_claims(now=LATER) == 0
    assert queue.recover_expired_claims(now=LATER) == 0
    assert (path.read_bytes(), queue.ledger_path.read_bytes()) == before
    duplicate = queue.enqueue(event)
    assert (duplicate.job_id, duplicate.status, duplicate.duplicate) == (job_id, COMMITTED, True)
    assert len(_terminal_records(queue)) == 1
    ledger = queue.ledger_path.read_text()
    assert event.session_id not in ledger
    assert "C:/private/transcript.jsonl" not in ledger
    assert str(queue.vault_path) not in ledger


def _inject_commit_crash(monkeypatch, queue, boundary):
    original_write, original_move, original_ledger = module._atomic_write_json, queue._move, queue._ledger

    def write(path, job):
        if boundary == "before_write" and job["status"] == COMMITTED:
            raise Crash()
        original_write(path, job)

    def move(source, destination):
        if destination.parent.name == "completed":
            assert queue._read_job(source)["status"] == COMMITTED
            if boundary == "before_rename":
                raise Crash()
        original_move(source, destination)
        if destination.parent.name == "completed" and boundary == "after_rename":
            raise Crash()

    def ledger(**kwargs):
        original_ledger(**kwargs)
        if kwargs["action"] == "COMMITTED" and boundary == "after_ledger":
            raise Crash()

    monkeypatch.setattr(module, "_atomic_write_json", write)
    monkeypatch.setattr(queue, "_move", move)
    monkeypatch.setattr(queue, "_ledger", ledger)


@pytest.mark.parametrize("boundary", ["before_write", "before_rename", "after_rename", "after_ledger"])
def test_commit_crash_boundaries(queued, monkeypatch, boundary):
    queue, event, job_id = queued
    with monkeypatch.context() as patch:
        _inject_commit_crash(patch, queue, boundary)
        with pytest.raises(Crash):
            queue.commit(job_id)
    path = queue.job_path(job_id)
    document = queue._read_job(path)
    assert document["status"] == (PROCESSING if boundary == "before_write" else COMMITTED)
    assert path.parent.name == ("processing" if boundary in {"before_write", "before_rename"} else "completed")
    if boundary == "before_write":
        assert queue.recover_expired_claims(now=NOW) == 0
        assert queue.recover_expired_claims(now=LATER) == 1
        assert queue.claim_next(now=LATER)["attempt"] == 2
        queue.commit(job_id)
    else:
        assert queue.recover_expired_claims(now=NOW) == (0 if boundary == "after_ledger" else 1)
    _assert_closed(queue, event, job_id)


@pytest.mark.parametrize("state,location", [(CLAIMED, "completed"), (PROCESSING, "completed"), (COMMITTED, "processing")])
@pytest.mark.parametrize("entrypoint", ["recover", "duplicate"])
def test_legacy_and_stranded_terminal_reconciliation(queued, state, location, entrypoint):
    queue, event, job_id = queued
    path = queue.job_path(job_id)
    job = queue._read_job(path)
    job["status"] = state
    if state == COMMITTED:
        job["committed_at"] = NOW
    module._atomic_write_json(path, job)
    if location == "completed":
        queue._move(path, queue._job_path(COMMITTED, job_id))
    if entrypoint == "recover":
        assert queue.recover_expired_claims(now=NOW) == 1
    else:
        assert queue.enqueue(event).status == COMMITTED
    assert queue._read_job(queue.job_path(job_id))["attempt"] == 1
    _assert_closed(queue, event, job_id)


@pytest.mark.parametrize("boundary", ["before_write", "after_write", "after_ledger"])
def test_recovery_itself_can_crash_and_repeat(queued, monkeypatch, boundary):
    queue, event, job_id = queued
    path = queue.job_path(job_id)
    queue._move(path, queue._job_path(COMMITTED, job_id))
    original_write = module._atomic_write_json

    def write(path, job):
        if boundary == "before_write":
            raise Crash()
        original_write(path, job)
        if boundary == "after_write":
            raise Crash()

    with monkeypatch.context() as patch:
        _inject_commit_crash(patch, queue, boundary)
        patch.setattr(module, "_atomic_write_json", write)
        with pytest.raises(Crash):
            queue.recover_expired_claims(now=NOW)
    queue.recover_expired_claims(now=LATER)
    _assert_closed(queue, event, job_id)


@pytest.mark.parametrize("damage", ["json", "filename", "idempotency", "event_identity", "state", "timestamp", "missing_claim"])
@pytest.mark.parametrize("entrypoint", ["recover", "duplicate"])
def test_completed_corruption_is_visible_without_promotion(queued, damage, entrypoint):
    queue, event, job_id = queued
    path = queue.job_path(job_id)
    job = queue._read_job(path)
    if damage == "filename":
        other = queue._job_from_event(event)
        other["idempotency_key"] += "-other"
        job["idempotency_key"] = other["idempotency_key"]
        job["event"]["idempotency_key"] = other["idempotency_key"]
        job["job_id"] = module._job_id(other["idempotency_key"])
    elif damage == "idempotency":
        job["idempotency_key"] += "-bad"
    elif damage == "event_identity":
        job["event"]["idempotency_key"] += "-bad"
    elif damage == "state":
        job["status"] = QUEUED
    elif damage == "timestamp":
        job["status"] = COMMITTED
        job["committed_at"] = "not-a-time"
    elif damage == "missing_claim":
        del job["claimed_at"]
    module._atomic_write_json(path, job)
    destination = queue._job_path(COMMITTED, job_id)
    queue._move(path, destination)
    if damage == "json":
        destination.write_text("{broken", encoding="utf-8")
    before = destination.read_bytes(), queue.ledger_path.read_bytes()
    for _ in range(2):
        with pytest.raises(CaptureQueueCorruptError):
            if entrypoint == "recover":
                queue.recover_expired_claims(now=LATER)
            else:
                queue.enqueue(event)
    assert (destination.read_bytes(), queue.ledger_path.read_bytes()) == before
    assert not (queue.vault_path / ".claude" / "validated-memory.json").exists()
    assert not (queue.vault_path / ".claude" / "project-state.json").exists()


def test_duplicate_reads_processing_document_state(queued):
    queue, event, _ = queued
    assert queue.enqueue(event).status == PROCESSING


@pytest.mark.parametrize("boundary", ["before_write", "before_rename", "after_rename", "after_ledger", "legacy_completed"])
def test_worker_crash_recovery_has_one_effect_and_receipt(tmp_path, monkeypatch, boundary):
    vault = tmp_path / "vault"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, proactive_capture=True)
    StateService(vault).init_project(project["project_id"], source={"type": "user", "reference": "w02"})
    migrate(vault)
    write_json(RuntimeConfig(vault).path, {
        "schema_version": 1, "mode": "CANARY", "project_ids": [project["project_id"]],
        "local_model": None, "transcript_roots": {"claude": [str(tmp_path)], "codex": [str(tmp_path)]},
    })
    slug = str(vault.resolve()).replace(":", "-").replace("/", "-").replace("\\", "-")
    directory = tmp_path / slug
    directory.mkdir()
    transcript = directory / "w02-crash.jsonl"
    transcript.write_text(json.dumps({"type": "user", "sessionId": "w02-crash", "message": {
        "role": "user", "content": "We decided to use SQLite for persistent storage.",
    }}) + "\n", encoding="utf-8")
    receipt = enqueue(vault, "claude", {"session_id": "w02-crash", "cwd": str(vault), "transcript_path": str(transcript)})
    worker = Worker(vault)
    with monkeypatch.context() as patch:
        _inject_commit_crash(patch, worker.queue, "after_rename" if boundary == "legacy_completed" else boundary)
        with pytest.raises(Crash):
            worker.once()
    queue = CaptureQueue(vault)
    if boundary == "legacy_completed":
        path = queue.job_path(receipt["job_id"])
        job = queue._read_job(path)
        job["status"] = PROCESSING
        del job["committed_at"]
        module._atomic_write_json(path, job)
    memory = MemoryStore(vault).load()
    state = StateStore(vault).load()
    assert len(memory["validated_memory"]) == 1
    assert len(memory["operation_receipts"]) == 1
    receipt_paths = list((RuntimeConfig(vault).root / "capture-receipts").glob("*.json"))
    assert len(receipt_paths) == 1
    effect_receipt = read_json(receipt_paths[0])
    assert effect_receipt["status"] == "EFFECT_VERIFIED"
    assert effect_receipt["canonical_effect_count"] == 1
    if boundary == "before_write":
        queue.recover_expired_claims(now="2099-01-01T00:00:00Z")
    later = Worker(vault)
    monkeypatch.setattr(later, "process", lambda *_args, **_kwargs: pytest.fail("repair replayed extraction"))
    result = later.once()
    assert result["status"] == ("PROCESSED" if boundary == "before_write" else "IDLE")
    if boundary == "before_write":
        assert result["receipt_replayed"] is True
    assert later.once()["status"] == "IDLE"
    assert MemoryStore(vault).load() == memory
    assert StateStore(vault).load() == state
    final_receipt = read_json(receipt_paths[0])
    # The existing receipt replay refreshes only the observation timestamp.
    if boundary == "before_write":
        final_receipt.pop("at")
        effect_receipt.pop("at")
    assert final_receipt == effect_receipt
    assert len(list((RuntimeConfig(vault).root / "capture-receipts").glob("*.json"))) == 1
    path = queue.job_path(receipt["job_id"])
    assert path.parent.name == "completed"
    assert queue._read_job(path)["status"] == COMMITTED
    assert len(_terminal_records(queue)) == 1
