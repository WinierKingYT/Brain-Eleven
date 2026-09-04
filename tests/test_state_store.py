"""Phase 16 canonical StateStore persistence tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from state_store import (  # noqa: E402
    StateError,
    StateStore,
    StateStoreConflict,
    StateStoreCorrupt,
)


SOURCE = {"type": "user", "reference": "test"}


def test_explicit_initialization_is_revisioned_atomic_and_does_not_create_memory(tmp_path):
    store = StateStore(tmp_path)

    project = store.init_project("brain-eleven", source=SOURCE, now="2026-09-03T12:00:00Z")

    assert project["revision"] == 1
    assert store.project_revision("brain-eleven") == 1
    payload = store.load()
    assert payload["store_revision"] == 1
    assert payload["events"][0]["operation"] == "state_initialized"
    assert not (tmp_path / ".claude" / "validated-memory.json").exists()


def test_stale_project_cas_rejects_without_mutating_state(tmp_path):
    store = StateStore(tmp_path)
    store.init_project("brain-eleven", source=SOURCE)

    def set_marker(project):
        project["constraints"].append(
            {
                "id": "con_01J00000000000000000000000",
                "text": "offline_only",
                "status": "ACTIVE",
                "source": SOURCE,
                "created_at": "2026-09-03T12:00:00Z",
                "updated_at": "2026-09-03T12:00:00Z",
            }
        )
        return "changed"

    result, persisted = store._transact_project(
        "brain-eleven",
        expected_revision=1,
        operation="constraint_added",
        source=SOURCE,
        record_ids=["con_01J00000000000000000000000"],
        mutator=set_marker,
        now="2026-09-03T12:00:00Z",
    )
    assert result == "changed"
    assert persisted["revision"] == 2

    with pytest.raises(StateStoreConflict):
        store._transact_project(
            "brain-eleven",
            expected_revision=1,
            operation="constraint_added",
            source=SOURCE,
            record_ids=["con_01J00000000000000000000000"],
            mutator=set_marker,
        )
    assert store.project_revision("brain-eleven") == 2
    assert len(store.load()["events"]) == 2


def test_corrupt_state_is_never_treated_as_empty_and_duplicate_init_is_refused(tmp_path):
    store = StateStore(tmp_path)
    store.path.parent.mkdir(parents=True)
    store.path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(StateStoreCorrupt):
        store.load()

    fresh = StateStore(tmp_path / "fresh")
    fresh.init_project("brain-eleven", source=SOURCE)
    with pytest.raises(StateError, match="already exists"):
        fresh.init_project("brain-eleven", source=SOURCE)
