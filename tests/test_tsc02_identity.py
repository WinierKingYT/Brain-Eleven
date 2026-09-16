"""TSC-02 project identity and registry-lineage safety evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from authority import AuthorityResolver
from authority.serialization import task_state_from_dict
from brain_eleven.projects.identity import (
    ROOT_IDENTITY_PATTERN,
    project_root_identity,
)
from context_router import ContextRouter
from project_registry import ProjectRegistry
from state_store import StateService
from task_state_context import TaskStateComposer, TaskStateLineage, TaskStateLineageError


SOURCE = {"type": "user", "reference": "tsc-02-test"}


def _configured(tmp_path: Path):
    project = tmp_path / "project-a"
    project.mkdir()
    ProjectRegistry(tmp_path).register(project, project_id="project-a")
    StateService(tmp_path).init_project("project-a", source=SOURCE)
    return project, TaskStateComposer(tmp_path, project).compose("Implement safe persistence.")


def test_root_identity_is_opaque_fixed_format_and_path_free(tmp_path):
    root = tmp_path / "private-project"
    identity = project_root_identity(root)

    assert ROOT_IDENTITY_PATTERN.fullmatch(identity)
    assert str(root) not in identity
    assert identity == project_root_identity(root.resolve())


def test_composer_emits_lineage_without_changing_task_state_fields(tmp_path):
    _project, context = _configured(tmp_path)
    payload = context.to_dict()

    assert list(payload) == ["schema_version", "task", "state", "lineage"]
    assert payload["schema_version"] == 1
    assert payload["lineage"]["project_id"] == "project-a"
    assert payload["lineage"]["registry_revision"] == 1
    assert payload["lineage"]["root_identity"].startswith("project-root-v1:")
    assert str(tmp_path) not in json.dumps(payload["lineage"])


def test_valid_relocation_preserves_project_id_but_stales_old_context(tmp_path):
    project, old_context = _configured(tmp_path)
    moved = tmp_path / "moved-project"
    moved.mkdir()
    registry = ProjectRegistry(tmp_path)
    registry.relocate("project-a", moved)

    old_result = ContextRouter(tmp_path).route(old_context)
    new_context = TaskStateComposer(tmp_path, moved).compose("Implement safe persistence.")
    new_result = ContextRouter(tmp_path).route(new_context)

    assert old_result.status == "STALE_INPUT"
    assert old_result.candidates == ()
    assert new_context.lineage.project_id == old_context.lineage.project_id == "project-a"
    assert new_context.lineage.root_identity != old_context.lineage.root_identity
    assert new_result.status in {"EMPTY", "SUCCESS", "DEGRADED"}
    assert project.exists()


def test_root_reuse_rejects_old_context_in_router_and_authority(tmp_path):
    old_root, context = _configured(tmp_path)
    moved = tmp_path / "moved-project"
    moved.mkdir()
    registry = ProjectRegistry(tmp_path)
    registry.relocate("project-a", moved)
    registry.register(old_root, project_id="project-b")

    router_result = ContextRouter(tmp_path).route(context)
    authority_result = AuthorityResolver(tmp_path).resolve(context, router_result)

    assert router_result.status == "STALE_INPUT"
    assert router_result.candidates == ()
    assert authority_result.status == "STALE_INPUT"
    assert authority_result.candidates == ()
    assert str(old_root) not in (router_result.error or "")
    assert str(old_root) not in (authority_result.error or "")


def test_composer_rejects_registry_change_between_reads(tmp_path, monkeypatch):
    project, _context = _configured(tmp_path)
    composer = TaskStateComposer(tmp_path, project)
    original_resolve = composer.resolver.resolve

    def race(project_id):
        state = original_resolve(project_id)
        ProjectRegistry(tmp_path).rename(project_id, "renamed-during-compose")
        return state

    monkeypatch.setattr(composer.resolver, "resolve", race)

    with pytest.raises(TaskStateLineageError, match="registry changed"):
        composer.compose("Implement safe persistence.")


def test_serialization_round_trip_requires_lineage(tmp_path):
    _project, context = _configured(tmp_path)
    payload = context.to_dict()

    decoded = task_state_from_dict(payload)
    assert decoded.to_dict() == payload

    missing = dict(payload)
    missing.pop("lineage")
    with pytest.raises(ValueError, match="lineage"):
        task_state_from_dict(missing)


def test_serialization_rejects_raw_path_and_mismatched_lineage(tmp_path):
    _project, context = _configured(tmp_path)
    payload = context.to_dict()

    raw_path = json.loads(json.dumps(payload))
    raw_path["lineage"]["root_identity"] = str(tmp_path / "private-root")
    with pytest.raises(ValueError, match="lineage"):
        task_state_from_dict(raw_path)

    mismatch = json.loads(json.dumps(payload))
    mismatch["lineage"]["project_id"] = "other-project"
    with pytest.raises(ValueError, match="identity"):
        task_state_from_dict(mismatch)


def test_unresolved_and_global_lineage_are_explicit_and_project_free(tmp_path):
    unknown = TaskStateComposer(tmp_path, tmp_path / "unknown").compose("Explain task state.")
    assert unknown.lineage == TaskStateLineage(status="unresolved")
    assert task_state_from_dict(unknown.to_dict()).lineage.status == "unresolved"

    global_payload = unknown.to_dict()
    global_payload["lineage"] = {"status": "global"}
    global_context = task_state_from_dict(global_payload)
    assert global_context.lineage.status == "global"
    assert global_context.task.project.project_id is None
    assert global_context.state.project_id is None


def test_router_checks_lineage_before_cache_lookup(tmp_path, monkeypatch):
    project, context = _configured(tmp_path)
    router = ContextRouter(tmp_path)
    registry = ProjectRegistry(tmp_path)
    moved = tmp_path / "moved-project"
    moved.mkdir()
    registry.relocate("project-a", moved)

    def forbidden_cache_load(*_args, **_kwargs):
        raise AssertionError("stale lineage must be rejected before cache lookup")

    monkeypatch.setattr(router.cache, "load", forbidden_cache_load)
    result = router.route(context)

    assert result.status == "STALE_INPUT"
    assert result.candidates == ()
    assert project.exists()


def test_router_cache_race_is_rejected_after_lookup_without_delivery(tmp_path, monkeypatch):
    project, context = _configured(tmp_path)
    router = ContextRouter(tmp_path)
    assert router.route(context).status in {"EMPTY", "SUCCESS", "DEGRADED"}
    cache_before = router.cache.path.read_bytes()
    moved = tmp_path / "moved-project"
    moved.mkdir()
    original_load = router.cache.load

    def race(key, revisions):
        ProjectRegistry(tmp_path).relocate("project-a", moved)
        return original_load(key, revisions)

    monkeypatch.setattr(router.cache, "load", race)
    result = router.route(context)

    assert result.status == "STALE_INPUT"
    assert result.candidates == ()
    assert router.cache.path.read_bytes() == cache_before
    assert project.exists()


def test_authority_cache_race_is_rejected_before_cached_delivery(tmp_path, monkeypatch):
    project, context = _configured(tmp_path)
    router_result = ContextRouter(tmp_path).route(context)
    resolver = AuthorityResolver(tmp_path)
    assert resolver.resolve(context, router_result).status in {"EMPTY", "SUCCESS", "DEGRADED"}
    cache_before = resolver.cache.path.read_bytes()
    moved = tmp_path / "moved-project"
    moved.mkdir()
    original_load = resolver.cache.load

    def race(key, revisions):
        ProjectRegistry(tmp_path).relocate("project-a", moved)
        return original_load(key, revisions)

    monkeypatch.setattr(resolver.cache, "load", race)
    result = resolver.resolve(context, router_result)

    assert result.status == "STALE_INPUT"
    assert result.candidates == ()
    assert resolver.cache.path.read_bytes() == cache_before
    assert project.exists()


def test_current_cache_hits_refresh_access_metadata_and_preserve_result(tmp_path):
    _project, context = _configured(tmp_path)
    router = ContextRouter(tmp_path)
    cold_router_result = router.route(context)
    router_document = json.loads(router.cache.path.read_text(encoding="utf-8"))
    router_document["entries"][cold_router_result.plan.fingerprint]["last_access_ns"] = 1
    router.cache.path.write_text(json.dumps(router_document, indent=2) + "\n", encoding="utf-8")

    cached_router_result = router.route(context)
    refreshed_router_document = json.loads(router.cache.path.read_text(encoding="utf-8"))

    assert cached_router_result.status == cold_router_result.status
    assert cached_router_result.plan == cold_router_result.plan
    assert cached_router_result.candidates == cold_router_result.candidates
    assert refreshed_router_document["entries"][cold_router_result.plan.fingerprint]["last_access_ns"] > 1

    resolver = AuthorityResolver(tmp_path)
    cold_authority_result = resolver.resolve(context, cold_router_result)
    authority_document = json.loads(resolver.cache.path.read_text(encoding="utf-8"))
    authority_key = next(iter(authority_document["entries"]))
    authority_document["entries"][authority_key]["last_access_ns"] = 1
    resolver.cache.path.write_text(json.dumps(authority_document, indent=2) + "\n", encoding="utf-8")

    cached_authority_result = resolver.resolve(context, cold_router_result)
    refreshed_authority_document = json.loads(resolver.cache.path.read_text(encoding="utf-8"))

    assert cached_authority_result.status == cold_authority_result.status
    assert cached_authority_result.candidates == cold_authority_result.candidates
    assert cached_authority_result.telemetry["cache_hit"] is True
    assert refreshed_authority_document["entries"][authority_key]["last_access_ns"] > 1
