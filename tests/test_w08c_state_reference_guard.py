"""Focused W-08C evidence for linearizable state/memory references."""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

import state_store as state_store_module
from memory_store import MemoryStore
from memory_store import MemoryStoreCorrupt
from project_registry import ProjectRegistry
from state_resolver import StateResolver
from state_store import (
    StateReferenceConflict,
    StateReferenceError,
    StateService,
    StateStoreConflict,
    StateStoreLockTimeout,
)


SOURCE = {"type": "user", "reference": "w08c-test"}
NOW = "2026-09-13T10:00:00Z"


def _service(tmp_path: Path, project_id: str = "project-a") -> StateService:
    ProjectRegistry(tmp_path).register(tmp_path / project_id, project_id=project_id)
    service = StateService(tmp_path)
    service.init_project(project_id, source=SOURCE, now=NOW)
    return service


def _memory(
    memory_id: str,
    *,
    scope: str = "global",
    project_id: str | None = None,
    status: str | None = "active",
    content: str = "bounded memory content",
) -> dict:
    result = {
        "memory_id": memory_id,
        "content": content,
        "type": "decision",
        "scope": scope,
    }
    if project_id is not None:
        result["project_id"] = project_id
    if status is not None:
        result["status"] = status
    return result


def _append(tmp_path: Path, record: dict, *, bucket: str = "validated_memory") -> None:
    MemoryStore(tmp_path).append(record, bucket=bucket)


def test_global_and_matching_project_reference_preserve_existing_shape(tmp_path):
    service = _service(tmp_path)
    _append(tmp_path, _memory("mem_global"))
    _append(tmp_path, _memory("mem_project", scope="project", project_id="project-a"))

    global_result = service.add_memory_reference(
        "project-a", memory_id="mem_global", expected_revision=1, source=SOURCE, now=NOW
    )
    project_result = service.add_memory_reference(
        "project-a", memory_id="mem_project", expected_revision=2, source=SOURCE, now=NOW
    )

    assert set(global_result) == {
        "project_id", "revision", "created_at", "updated_at", "current",
        "requirements", "work_items", "blockers", "constraints", "risks", "references",
    }
    assert project_result["references"] == {"memory_ids": ["mem_global", "mem_project"]}
    events = service.store.load()["events"]
    assert [event["operation"] for event in events] == [
        "state_initialized", "memory_reference_added", "memory_reference_added"
    ]
    assert events[-1]["record_ids"] == ["mem_project"]


@pytest.mark.parametrize(
    ("record", "bucket", "expected"),
    [
        (None, "validated_memory", "DANGLING_MEMORY_REFERENCE"),
        (_memory("mem_other", scope="project", project_id="project-b"), "validated_memory", "WRONG_PROJECT_MEMORY_REFERENCE"),
        (_memory("mem_deleted", status="deleted"), "validated_memory", "DELETED_MEMORY_REFERENCE"),
        (_memory("mem_unknown", status="quarantined"), "validated_memory", "INVALID_MEMORY_REFERENCE_STATUS"),
        (_memory("mem_rejected"), "rejected_memory", "DANGLING_MEMORY_REFERENCE"),
    ],
)
def test_invalid_reference_policy_has_no_state_effect(tmp_path, record, bucket, expected):
    service = _service(tmp_path)
    if record is not None:
        _append(tmp_path, record, bucket=bucket)
    before = service.store.load()

    with pytest.raises(StateReferenceError, match=expected):
        service.add_memory_reference(
            "project-a", memory_id=(record or {"memory_id": "mem_missing"})["memory_id"],
            expected_revision=1, source=SOURCE, now=NOW,
        )

    after = service.store.load()
    assert after == before
    assert len(after["events"]) == 1


@pytest.mark.parametrize("status", ["resolved", "superseded", None])
def test_historical_and_legacy_statuses_remain_valid(tmp_path, status):
    service = _service(tmp_path)
    _append(tmp_path, _memory("mem_historical", status=status))
    result = service.add_memory_reference(
        "project-a", memory_id="mem_historical", expected_revision=1, source=SOURCE, now=NOW
    )
    assert result["references"]["memory_ids"] == ["mem_historical"]


def test_rejected_target_in_blocker_path_is_guarded(tmp_path):
    service = _service(tmp_path)
    _append(tmp_path, _memory("mem_deleted", status="deleted"))
    with pytest.raises(StateReferenceError, match="DELETED_MEMORY_REFERENCE"):
        service.add_blocker(
            "project-a", text="guarded blocker", severity="HIGH", memory_ref="mem_deleted",
            expected_revision=1, source=SOURCE, now=NOW,
        )
    assert service.store.project_revision("project-a") == 1


def test_resolver_classifies_deleted_unknown_and_scope_drift_without_changing_shape(tmp_path):
    service = _service(tmp_path)
    _append(tmp_path, _memory("mem_deleted", status="deleted"))
    _append(tmp_path, _memory("mem_unknown", status="quarantined"))
    _append(tmp_path, _memory("mem_drift", scope="project", project_id="project-b"))
    state = service.store.load()["projects"]["project-a"]
    state["references"]["memory_ids"] = ["mem_deleted", "mem_unknown", "mem_drift"]
    # Build the fixture through the canonical state transaction to retain audit shape.
    service.store._transact_project(
        "project-a", expected_revision=1, operation="test_reference_fixture", source=SOURCE,
        record_ids=[], mutator=lambda project: project["references"].update(state["references"]), now=NOW,
    )

    references = StateResolver(tmp_path).resolve("project-a").references
    assert references["valid"] == []
    assert references["dangling"] == ["mem_deleted", "mem_unknown"]
    assert references["wrong_project"] == ["mem_drift"]
    assert set(references) == {"status", "valid", "dangling", "wrong_project"}


def test_stale_state_cas_has_no_memory_or_audit_effect(tmp_path):
    service = _service(tmp_path)
    _append(tmp_path, _memory("mem_global"))
    before_memory = MemoryStore(tmp_path).load()
    before_state = service.store.load()

    with pytest.raises(StateStoreConflict):
        service.add_memory_reference(
            "project-a", memory_id="mem_global", expected_revision=0, source=SOURCE, now=NOW
        )

    assert MemoryStore(tmp_path).load() == before_memory
    assert service.store.load() == before_state


def test_duplicate_reference_does_not_create_second_revision_or_event(tmp_path):
    service = _service(tmp_path)
    _append(tmp_path, _memory("mem_global"))
    service.add_memory_reference(
        "project-a", memory_id="mem_global", expected_revision=1, source=SOURCE, now=NOW
    )
    before = service.store.load()
    with pytest.raises(Exception, match="already references"):
        service.add_memory_reference(
            "project-a", memory_id="mem_global", expected_revision=2, source=SOURCE, now=NOW
        )
    assert service.store.load() == before


def test_memory_lock_timeout_is_typed_bounded_and_does_not_write(tmp_path, monkeypatch):
    service = _service(tmp_path)
    _append(tmp_path, _memory("mem_global"))
    before = service.store.load()

    @contextmanager
    def timeout(_vault):
        raise state_store_module.MemoryStoreLockTimeout("raw path and secret should not escape")
        yield  # pragma: no cover

    monkeypatch.setattr(state_store_module, "memory_store_lock", timeout)
    with pytest.raises(StateReferenceConflict) as error:
        service.add_memory_reference(
            "project-a", memory_id="mem_global", expected_revision=1, source=SOURCE, now=NOW
        )
    assert error.value.reason == "MEMORY_REFERENCE_LOCK_TIMEOUT"
    assert str(error.value) == "MEMORY_REFERENCE_CONFLICT: MEMORY_REFERENCE_LOCK_TIMEOUT"
    assert service.store.load() == before


def test_corrupt_memory_is_visible_as_typed_reference_failure_without_state_write(tmp_path, monkeypatch):
    service = _service(tmp_path)
    before = service.store.load()

    def corrupt_read():
        raise MemoryStoreCorrupt("raw content and project root must stay bounded")

    monkeypatch.setattr(service.memory_store, "_read_unlocked", corrupt_read)
    with pytest.raises(StateReferenceError, match="MemoryStore is unavailable") as error:
        service.add_memory_reference(
            "project-a", memory_id="mem_global", expected_revision=1, source=SOURCE, now=NOW
        )
    assert "raw content" not in str(error.value)
    assert service.store.load() == before


def test_state_lock_timeout_is_not_misclassified_as_memory_guard_timeout(tmp_path, monkeypatch):
    service = _service(tmp_path)
    _append(tmp_path, _memory("mem_global"))

    @contextmanager
    def state_timeout(_path):
        raise state_store_module.MemoryStoreLockTimeout("state lock timeout")
        yield  # pragma: no cover

    monkeypatch.setattr(state_store_module, "file_lock", state_timeout)
    with pytest.raises(StateStoreLockTimeout):
        service.add_memory_reference(
            "project-a", memory_id="mem_global", expected_revision=1, source=SOURCE, now=NOW
        )
    assert service.store.project_revision("project-a") == 1


def test_guard_serializes_normal_memory_writer_before_state_commit(tmp_path, monkeypatch):
    service = _service(tmp_path)
    _append(tmp_path, _memory("mem_global"))
    entered = threading.Event()
    release = threading.Event()
    writer_done = threading.Event()
    add_done = threading.Event()
    result = {}
    original_assert = service._assert_memory_reference_snapshot_unlocked

    def pause_after_guard(project_id, snapshot, document):
        original_assert(project_id, snapshot, document)
        entered.set()
        assert not writer_done.wait(0.15)
        release.wait(5)

    monkeypatch.setattr(service, "_assert_memory_reference_snapshot_unlocked", pause_after_guard)

    def add_reference():
        try:
            result["value"] = service.add_memory_reference(
                "project-a", memory_id="mem_global", expected_revision=1, source=SOURCE, now=NOW
            )
        except BaseException as exc:  # surfaced in the parent assertion below
            result["error"] = exc
        finally:
            add_done.set()

    def write_memory():
        MemoryStore(tmp_path).append(_memory("mem_after"))
        writer_done.set()

    add_thread = threading.Thread(target=add_reference)
    add_thread.start()
    assert entered.wait(5)
    writer_thread = threading.Thread(target=write_memory)
    writer_thread.start()
    time.sleep(0.15)
    assert not writer_done.is_set()
    release.set()
    assert add_done.wait(5)
    add_thread.join(5)
    writer_thread.join(5)
    assert "error" not in result
    assert result["value"]["references"]["memory_ids"] == ["mem_global"]
    assert writer_done.is_set()
    assert "mem_global" in service.store.get_project("project-a")["references"]["memory_ids"]
    assert MemoryStore(tmp_path).revision() == 2


def test_reference_guard_does_not_persist_snapshot_or_memory_content(tmp_path):
    service = _service(tmp_path)
    sentinel = "SECRET_PROMPT_ROOT_SENTINEL"
    _append(tmp_path, _memory("mem_global", content=sentinel))
    service.add_memory_reference(
        "project-a", memory_id="mem_global", expected_revision=1, source=SOURCE, now=NOW
    )
    state_text = service.store.path.read_text(encoding="utf-8")
    assert sentinel not in state_text
    assert "memory_revision" not in state_text
    assert "memory_scope" not in state_text


def test_package_and_legacy_state_service_identity_remains_intact():
    from brain_eleven.state import StateService as package_service
    from brain_eleven.state import StateReferenceConflict as package_conflict
    from brain_eleven.state.store import StateService as package_store_service
    from scripts.state import _error_code

    assert package_service is StateService
    assert package_store_service is StateService
    assert package_conflict is StateReferenceConflict
    assert _error_code(StateReferenceConflict("MEMORY_REFERENCE_LOCK_TIMEOUT")) == "MEMORY_REFERENCE_CONFLICT"
