"""TSC-01 timezone-bound state validation and resolution evidence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from project_registry import ProjectRegistry
from state_resolver import STATE_AVAILABLE, STATE_CORRUPT, StateResolver
from state_store import StateSchemaError, StateService, StateStoreCorrupt
from task_state_context import TaskStateComposer


SOURCE = {"type": "user", "reference": "tsc-01-test"}
PROJECT_ID = "brain-eleven"
VALID_TIMESTAMP = "2026-09-03T12:00:00Z"


def _configured_vault(tmp_path: Path, *, timestamp: str = VALID_TIMESTAMP) -> StateService:
    ProjectRegistry(tmp_path).register(tmp_path / PROJECT_ID, project_id=PROJECT_ID)
    service = StateService(tmp_path)
    service.init_project(PROJECT_ID, source=SOURCE, now=timestamp)
    return service


def _file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _replace_project_updated_at(service: StateService, value: object) -> None:
    payload = json.loads(service.store.path.read_text(encoding="utf-8"))
    payload["projects"][PROJECT_ID]["updated_at"] = value
    service.store.path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def test_state_service_rejects_naive_timestamp_without_write_or_revision_change(tmp_path):
    service = _configured_vault(tmp_path)
    state_path = service.store.path
    before_bytes = state_path.read_bytes()
    before_revision = service.store.project_revision(PROJECT_ID)
    backup_path = service.store.backup_path
    before_backup = backup_path.read_bytes() if backup_path.exists() else None

    with pytest.raises(StateSchemaError, match="timezone offset"):
        service.set_current_objective(
            PROJECT_ID,
            text="This mutation must not persist.",
            expected_revision=1,
            source=SOURCE,
            record_id="obj_01J00000000000000000000000",
            now="2026-09-03T12:00:00",
        )

    assert state_path.read_bytes() == before_bytes
    assert service.store.project_revision(PROJECT_ID) == before_revision
    assert (backup_path.read_bytes() if backup_path.exists() else None) == before_backup


@pytest.mark.parametrize(
    "timestamp",
    (
        "2026-09-03T12:00:00Z",
        "2026-09-03T12:00:00+03:00",
        "2026-09-03T07:00:00-02:00",
    ),
)
def test_resolver_accepts_explicit_offsets_without_rewriting_and_computes_freshness(
    tmp_path, timestamp
):
    _configured_vault(tmp_path, timestamp=timestamp)

    resolved = StateResolver(tmp_path).resolve(
        PROJECT_ID,
        now=datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc),
    )

    assert resolved.status == STATE_AVAILABLE
    assert resolved.updated_at == timestamp
    assert resolved.freshness == {"status": "current", "age_days": 0}


@pytest.mark.parametrize("bad_timestamp", ("2026-09-03T12:00:00", "not-a-timestamp"))
def test_seeded_bad_timestamp_is_corrupt_without_type_error_or_content_leak(tmp_path, bad_timestamp):
    service = _configured_vault(tmp_path)
    _replace_project_updated_at(service, bad_timestamp)
    before_bytes = service.store.path.read_bytes()

    resolved = StateResolver(tmp_path).resolve(PROJECT_ID)

    assert resolved.status == STATE_CORRUPT
    assert resolved.error == "state document is corrupt"
    assert bad_timestamp not in (resolved.error or "")
    assert str(tmp_path) not in (resolved.error or "")
    assert service.store.path.read_bytes() == before_bytes


def test_resolver_maps_bypassed_naive_state_to_bounded_corruption(tmp_path, monkeypatch):
    service = _configured_vault(tmp_path)
    resolver = StateResolver(tmp_path)
    state = service.store.get_project(PROJECT_ID)
    assert state is not None
    state["updated_at"] = "2026-09-03T12:00:00"
    monkeypatch.setattr(resolver.store, "get_project", lambda _project_id: state)

    resolved = resolver.resolve(PROJECT_ID)

    assert resolved.status == STATE_CORRUPT
    assert resolved.error == "state.updated_at is invalid"
    assert "2026-09-03T12:00:00" not in (resolved.error or "")
    assert str(tmp_path) not in (resolved.error or "")


def test_resolver_sanitizes_path_bearing_store_corruption(tmp_path, monkeypatch):
    _configured_vault(tmp_path)
    resolver = StateResolver(tmp_path)
    raw_error = f"Cannot read canonical project state: {tmp_path / 'private.json'} token=secret"
    monkeypatch.setattr(
        resolver.store,
        "get_project",
        lambda _project_id: (_ for _ in ()).throw(StateStoreCorrupt(raw_error)),
    )

    resolved = resolver.resolve(PROJECT_ID)

    assert resolved.status == STATE_CORRUPT
    assert resolved.error == "state document is corrupt"
    assert str(tmp_path) not in (resolved.error or "")
    assert "private.json" not in (resolved.error or "")
    assert "secret" not in (resolved.error or "")


def test_composer_exposes_bounded_corrupt_state_without_side_effects(tmp_path):
    service = _configured_vault(tmp_path)
    _replace_project_updated_at(service, "2026-09-03T12:00:00")
    before_files = _file_snapshot(tmp_path)

    context = TaskStateComposer(tmp_path, tmp_path / PROJECT_ID).compose(
        "Explain the current task state."
    )

    assert context.state.status == STATE_CORRUPT
    assert context.state.error == "state document is corrupt"
    assert str(tmp_path) not in (context.state.error or "")
    assert _file_snapshot(tmp_path) == before_files
