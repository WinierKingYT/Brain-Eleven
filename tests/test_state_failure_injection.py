"""Phase 16 adversarial tests for canonical StateStore failure behavior."""

from __future__ import annotations

from contextlib import contextmanager
import multiprocessing
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import state_store as state_store_module  # noqa: E402
from memory_store import MemoryStore  # noqa: E402
from memory_store_lock import MemoryStoreLockTimeout  # noqa: E402
from project_registry import ProjectRegistry  # noqa: E402
from state_store import (  # noqa: E402
    StateProjectUnknown,
    StateProvenanceError,
    StateReferenceError,
    StateService,
    StateStore,
    StateStoreConflict,
    StateStoreCorrupt,
    StateStoreLockTimeout,
    StateStorePersistenceError,
)


SOURCE = {"type": "user", "reference": "failure-injection"}
NOW = "2026-09-03T12:00:00Z"


def _concurrent_requirement_writer(vault_path: str, writer_number: int, outcome_queue) -> None:
    """One subprocess writer which retries only on a truthful CAS conflict."""
    service = StateService(vault_path)
    requirement_id = f"req_writer_{writer_number}"
    for _attempt in range(40):
        revision = service.store.project_revision("brain-eleven")
        try:
            service.add_requirement(
                "brain-eleven",
                text=f"writer {writer_number} completed",
                expected_revision=revision,
                source=SOURCE,
                record_id=requirement_id,
                now=NOW,
            )
        except StateStoreConflict:
            continue
        except Exception as exc:  # pragma: no cover - asserted by the parent process
            outcome_queue.put((False, repr(exc)))
            return
        outcome_queue.put((True, requirement_id))
        return
    outcome_queue.put((False, "retry_exhausted"))


def _active_service(tmp_path):
    ProjectRegistry(tmp_path).register(tmp_path / "brain-eleven", project_id="brain-eleven")
    service = StateService(tmp_path)
    service.init_project("brain-eleven", source=SOURCE, now=NOW)
    return service


def test_corrupt_state_and_unsupported_schema_fail_closed(tmp_path):
    ProjectRegistry(tmp_path).register(tmp_path / "brain-eleven", project_id="brain-eleven")
    store = StateStore(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text('{"schema_version": 999}', encoding="utf-8")

    with pytest.raises(StateStoreCorrupt):
        store.load()
    with pytest.raises(StateStoreCorrupt):
        store.get_project("brain-eleven")


def test_lock_timeout_and_write_failure_leave_the_previous_canonical_snapshot_intact(tmp_path, monkeypatch):
    service = _active_service(tmp_path)
    store = service.store
    original_revision = store.project_revision("brain-eleven")

    @contextmanager
    def unavailable_lock(*_args, **_kwargs):
        raise MemoryStoreLockTimeout("synthetic lock timeout")
        yield

    monkeypatch.setattr(state_store_module, "file_lock", unavailable_lock)
    with pytest.raises(StateStoreLockTimeout):
        store._transact_project(
            "brain-eleven",
            expected_revision=original_revision,
            operation="synthetic",
            source=SOURCE,
            record_ids=[],
            mutator=lambda project: project,
            now=NOW,
        )

    monkeypatch.undo()

    def disk_failure(_state):
        raise StateStorePersistenceError("synthetic disk failure")

    monkeypatch.setattr(store, "_write_unlocked", disk_failure)
    with pytest.raises(StateStorePersistenceError):
        service.add_requirement(
            "brain-eleven",
            text="must not persist",
            expected_revision=original_revision,
            source=SOURCE,
            record_id="req_disk_failure",
            now=NOW,
        )

    assert StateStore(tmp_path).project_revision("brain-eleven") == original_revision
    assert StateStore(tmp_path).get_project("brain-eleven")["requirements"] == []


def test_ai_proposed_state_and_invalid_memory_references_cannot_become_canonical(tmp_path):
    ProjectRegistry(tmp_path).register(tmp_path / "brain-eleven", project_id="brain-eleven")
    ProjectRegistry(tmp_path).register(tmp_path / "other", project_id="other-project")
    service = StateService(tmp_path)

    with pytest.raises(StateProvenanceError):
        service.init_project("brain-eleven", source={"type": "ai_proposed", "reference": "guess"}, now=NOW)
    assert service.store.project_revision("brain-eleven") is None

    service.init_project("brain-eleven", source=SOURCE, now=NOW)
    MemoryStore(tmp_path).append(
        {
            "memory_id": "mem_other_project",
            "content": "Synthetic other-project decision.",
            "type": "decision",
            "status": "active",
            "scope": "project",
            "project_id": "other-project",
        }
    )
    with pytest.raises(StateReferenceError):
        service.add_memory_reference(
            "brain-eleven",
            memory_id="mem_other_project",
            expected_revision=1,
            source=SOURCE,
            now=NOW,
        )
    assert service.store.project_revision("brain-eleven") == 1


def test_ten_concurrent_state_writers_persist_every_success_without_lost_updates(tmp_path):
    service = _active_service(tmp_path)
    context = multiprocessing.get_context("spawn")
    outcomes = context.Queue()
    workers = [
        context.Process(target=_concurrent_requirement_writer, args=(str(tmp_path), number, outcomes))
        for number in range(10)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=30)
        assert worker.exitcode == 0

    results = [outcomes.get(timeout=5) for _ in workers]
    assert all(succeeded for succeeded, _detail in results)
    state = StateStore(tmp_path).get_project("brain-eleven")
    assert state["revision"] == 11
    assert len(state["requirements"]) == 10
    assert {record["id"] for record in state["requirements"]} == {
        f"req_writer_{number}" for number in range(10)
    }


def test_unknown_project_is_never_created_by_a_failed_mutation(tmp_path):
    service = StateService(tmp_path)

    with pytest.raises(StateProjectUnknown):
        service.add_requirement(
            "unknown",
            text="must not create identity",
            expected_revision=0,
            source=SOURCE,
            record_id="req_unknown",
            now=NOW,
        )

    assert not service.store.exists()
