#!/usr/bin/env python3
"""Read-only normalization of current project state for future routing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Mapping, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from memory_store import MemoryStore, MemoryStoreError
from brain_eleven.projects.registry import ProjectRegistry, ProjectRegistryError
from state_store import StateStore, StateStoreCorrupt


STATE_AVAILABLE = "AVAILABLE"
PROJECT_UNKNOWN = "PROJECT_UNKNOWN"
PROJECT_ARCHIVED = "PROJECT_ARCHIVED"
STATE_NOT_FOUND = "STATE_NOT_FOUND"
STATE_CORRUPT = "STATE_CORRUPT"
STATE_UNAVAILABLE = "STATE_UNAVAILABLE"
STALE_AFTER_DAYS = 30


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class CurrentProjectState:
    """Stable, read-only state response with explicit availability semantics."""

    project_id: Optional[str]
    status: str
    state_revision: Optional[int]
    updated_at: Optional[str]
    freshness: Mapping[str, Any]
    current: Mapping[str, Any]
    active_requirements: tuple[Mapping[str, Any], ...]
    active_work_items: tuple[Mapping[str, Any], ...]
    active_blockers: tuple[Mapping[str, Any], ...]
    constraints: tuple[Mapping[str, Any], ...]
    risks: tuple[Mapping[str, Any], ...]
    references: Mapping[str, Any]
    error: Optional[str] = None
    archived: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "status": self.status,
            "state_revision": self.state_revision,
            "updated_at": self.updated_at,
            "freshness": dict(self.freshness),
            "current": dict(self.current),
            "active_requirements": [dict(item) for item in self.active_requirements],
            "active_work_items": [dict(item) for item in self.active_work_items],
            "active_blockers": [dict(item) for item in self.active_blockers],
            "constraints": [dict(item) for item in self.constraints],
            "risks": [dict(item) for item in self.risks],
            "references": dict(self.references),
            "error": self.error,
            "archived": self.archived,
        }


def _empty_resolution(project_id: Optional[str], status: str, *, error: Optional[str] = None, archived: bool = False) -> CurrentProjectState:
    return CurrentProjectState(
        project_id=project_id,
        status=status,
        state_revision=None,
        updated_at=None,
        freshness={"status": "unknown", "age_days": None},
        current={"phase_id": None, "milestone": None, "objective": None},
        active_requirements=(),
        active_work_items=(),
        active_blockers=(),
        constraints=(),
        risks=(),
        references={"status": "not_checked", "valid": [], "dangling": [], "wrong_project": []},
        error=error,
        archived=archived,
    )


class StateResolver:
    """Resolve only the requested project's current structured truth."""

    def __init__(self, vault_path: str | Path, *, stale_after_days: int = STALE_AFTER_DAYS):
        self.vault_path = Path(vault_path).expanduser()
        self.registry = ProjectRegistry(self.vault_path)
        self.store = StateStore(self.vault_path)
        self.memory_store = MemoryStore(self.vault_path)
        self.stale_after_days = stale_after_days

    def _reference_health(self, project_id: str, state: Mapping[str, Any]) -> dict[str, Any]:
        reference_ids = list(state["references"]["memory_ids"])
        reference_ids.extend(
            blocker["memory_ref"] for blocker in state["blockers"] if blocker.get("memory_ref")
        )
        reference_ids = list(dict.fromkeys(reference_ids))
        if not reference_ids:
            return {"status": "checked", "valid": [], "dangling": [], "wrong_project": []}
        try:
            records = self.memory_store.load()["validated_memory"]
        except MemoryStoreError as exc:
            return {
                "status": "unavailable",
                "valid": [],
                "dangling": [],
                "wrong_project": [],
                "error": str(exc),
            }
        index = {record.get("memory_id"): record for record in records}
        valid, dangling, wrong_project = [], [], []
        for memory_id in reference_ids:
            record = index.get(memory_id)
            if record is None:
                dangling.append(memory_id)
            elif record.get("scope") == "global":
                valid.append(memory_id)
            elif record.get("scope") == "project" and record.get("project_id") == project_id:
                valid.append(memory_id)
            else:
                wrong_project.append(memory_id)
        return {
            "status": "checked",
            "valid": valid,
            "dangling": dangling,
            "wrong_project": wrong_project,
        }

    def resolve(self, project_id: str, *, now: Optional[datetime] = None) -> CurrentProjectState:
        project_id = str(project_id or "").strip()
        if not project_id:
            return _empty_resolution(None, PROJECT_UNKNOWN, error="project_id is required")
        try:
            registry_record = self.registry.get(project_id)
        except ProjectRegistryError as exc:
            return _empty_resolution(project_id, STATE_UNAVAILABLE, error=str(exc))
        if registry_record is None:
            return _empty_resolution(project_id, PROJECT_UNKNOWN, error="project is not registered")

        try:
            state = self.store.get_project(project_id)
        except StateStoreCorrupt as exc:
            return _empty_resolution(
                project_id,
                STATE_CORRUPT,
                error=str(exc),
                archived=registry_record["status"] == "archived",
            )
        except OSError as exc:
            return _empty_resolution(
                project_id,
                STATE_UNAVAILABLE,
                error=str(exc),
                archived=registry_record["status"] == "archived",
            )
        if state is None:
            return _empty_resolution(
                project_id,
                PROJECT_ARCHIVED if registry_record["status"] == "archived" else STATE_NOT_FOUND,
                error="state has not been initialized",
                archived=registry_record["status"] == "archived",
            )

        timestamp = _parse_timestamp(state["updated_at"])
        current_time = _utc_now() if now is None else now
        age_days = max(0, (current_time - timestamp).days)
        freshness = {
            "status": "stale_candidate" if age_days >= self.stale_after_days else "current",
            "age_days": age_days,
        }
        current = state["current"]
        milestone = current["milestone"]
        phase_id = None
        if milestone is not None and milestone["status"] in {"PLANNED", "ACTIVE", "BLOCKED"}:
            phase_id = milestone["phase_id"]
        archived = registry_record["status"] == "archived"
        return CurrentProjectState(
            project_id=project_id,
            status=PROJECT_ARCHIVED if archived else STATE_AVAILABLE,
            state_revision=int(state["revision"]),
            updated_at=state["updated_at"],
            freshness=freshness,
            current={
                "phase_id": phase_id,
                "milestone": dict(milestone) if milestone is not None else None,
                "objective": dict(current["objective"]) if current["objective"] is not None else None,
            },
            active_requirements=tuple(
                dict(record) for record in state["requirements"] if record["status"] == "ACTIVE"
            ),
            active_work_items=tuple(
                dict(record) for record in state["work_items"] if record["status"] in {"TODO", "ACTIVE", "BLOCKED"}
            ),
            active_blockers=tuple(
                dict(record) for record in state["blockers"] if record["status"] == "ACTIVE"
            ),
            constraints=tuple(dict(record) for record in state["constraints"]),
            risks=tuple(dict(record) for record in state["risks"]),
            references=self._reference_health(project_id, state),
            archived=archived,
        )
