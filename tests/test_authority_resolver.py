"""Phase 18 metadata-first authority safety and deterministic policy tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from authority import AuthorityOptions, AuthorityResolver  # noqa: E402
from authority.__main__ import main as authority_main  # noqa: E402
from context_router import ContextRouter, RoutingOptions  # noqa: E402
from project_registry import ProjectRegistry  # noqa: E402
from state_store import StateService  # noqa: E402
from task_state_context import TaskStateComposer  # noqa: E402


SOURCE = {"type": "user", "reference": "test"}
NOW = "2026-09-03T12:00:00Z"


def _memory(memory_id, project_id, content, *, status="active", fingerprint=None, superseded_by=""):
    scope = "project" if project_id else "global"
    return {
        "memory_id": memory_id,
        "type": "decision",
        "content": content,
        "confidence": 0.9,
        "quality_score": 0.9,
        "source": "test",
        "timestamp": NOW,
        "related_notes": [],
        "section": "test",
        "issues": [],
        "novelty": 1.0,
        "is_approved": True,
        "status": status,
        "resolved_at": "" if status == "active" else NOW,
        "resolved_by": "" if status == "active" else "test",
        "resolution_note": "" if status == "active" else "historical",
        "superseded_by": superseded_by,
        "supersession_note": "",
        "dedup_fingerprint": fingerprint or f"fp-{memory_id}",
        "scope": scope,
        "project": project_id or "",
        "project_label": project_id or "",
        "project_id": project_id or "",
    }


def _write_memory(vault, records, revision=7):
    path = vault / ".claude" / "validated-memory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "revision": revision,
                "updated_at": NOW,
                "validated_at": NOW,
                "summary": {},
                "validated_memory": records,
                "rejected_memory": [],
            }
        ),
        encoding="utf-8",
    )


def _configured(tmp_path, records=None):
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    registry = ProjectRegistry(tmp_path)
    registry.register(project_a, project_id="project-a")
    registry.register(project_b, project_id="project-b")
    state = StateService(tmp_path)
    state.init_project("project-a", source=SOURCE, now=NOW)
    state.init_project("project-b", source=SOURCE, now=NOW)
    state.set_current_objective(
        "project-a", text="Implement atomic persistence", expected_revision=1,
        source=SOURCE, record_id="obj_01J00000000000000000000000", now=NOW,
    )
    _write_memory(
        tmp_path,
        records
        or [
            _memory("mem_a_new", "project-a", "Use atomic SQLite persistence."),
            _memory("mem_b_other", "project-b", "Use atomic SQLite persistence in project B."),
            _memory("mem_global", None, "Use atomic writes for durable data."),
        ],
    )
    context = TaskStateComposer(tmp_path, project_a).compose("Implement atomic SQLite persistence.")
    return context, state


def test_authority_is_content_safe_deterministic_and_never_writes_canonical_sources(tmp_path):
    context, _state = _configured(tmp_path)
    before_memory = (tmp_path / ".claude" / "validated-memory.json").read_bytes()
    before_state = (tmp_path / ".claude" / "project-state.json").read_bytes()
    router_result = ContextRouter(tmp_path).route(context)

    first = AuthorityResolver(tmp_path).resolve(context, router_result)
    second = AuthorityResolver(tmp_path).resolve(context, router_result)

    assert first.status in {"SUCCESS", "DEGRADED"}
    assert [item.candidate_id for item in first.candidates] == [item.candidate_id for item in second.candidates]
    assert "mem_b_other" not in {item.candidate_id for item in first.candidates}
    payload = json.dumps(first.to_dict())
    assert "Use atomic SQLite persistence" not in payload
    assert "retrieval_score" not in payload
    assert (tmp_path / ".claude" / "validated-memory.json").read_bytes() == before_memory
    assert (tmp_path / ".claude" / "project-state.json").read_bytes() == before_state
    cache = (tmp_path / ".claude" / "authority-cache.json").read_text(encoding="utf-8")
    assert "Use atomic SQLite persistence" not in cache


def test_explicit_supersession_prefers_only_same_scope_successor(tmp_path):
    records = [
        _memory("mem_a_old", "project-a", "Use old SQLite ordering.", status="superseded", superseded_by="mem_a_new"),
        _memory("mem_a_new", "project-a", "Use new SQLite ordering."),
        _memory("mem_b_new", "project-b", "Use other SQLite ordering."),
    ]
    context, _state = _configured(tmp_path, records)
    routing = RoutingOptions(history_mode="ACTIVE_PLUS_RELEVANT_HISTORY")
    router_result = ContextRouter(tmp_path).route(context, routing)
    result = AuthorityResolver(tmp_path).resolve(
        context,
        router_result,
        AuthorityOptions(history_mode="ACTIVE_PLUS_RELEVANT_HISTORY"),
    )

    resolution = {item.candidate_id: item for item in result.candidates}
    assert resolution["mem_a_old"].status == "SUPERSEDED"
    assert resolution["mem_a_new"].status == "AUTHORITATIVE"
    assert all("mem_b_new" not in conflict.candidate_ids for conflict in result.conflict_sets)


def test_selected_projects_are_partitioned_and_require_matching_trusted_options(tmp_path):
    context, _state = _configured(tmp_path)
    routing = RoutingOptions(scope_mode="SELECTED_PROJECTS", selected_project_ids=("project-a", "project-b"))
    router_result = ContextRouter(tmp_path).route(context, routing)

    rejected = AuthorityResolver(tmp_path).resolve(context, router_result)
    accepted = AuthorityResolver(tmp_path).resolve(
        context,
        router_result,
        AuthorityOptions(scope_mode="SELECTED_PROJECTS", selected_project_ids=("project-a", "project-b")),
    )

    assert rejected.status == "SCOPE_ERROR"
    assert accepted.status in {"SUCCESS", "DEGRADED"}
    assert all(
        not ({"mem_a_new", "mem_b_other"} <= set(conflict.candidate_ids))
        for conflict in accepted.conflict_sets
    )


def test_active_blocker_referencing_historical_memory_is_an_implementation_gap(tmp_path):
    records = [
        _memory("mem_a_old", "project-a", "Use old SQLite ordering.", status="superseded", superseded_by="mem_a_new"),
        _memory("mem_a_new", "project-a", "Use new SQLite ordering."),
    ]
    context, state = _configured(tmp_path, records)
    state.add_blocker(
        "project-a", text="Implementation still follows the old rule", severity="HIGH", expected_revision=2,
        source=SOURCE, record_id="blk_01J00000000000000000000000", memory_ref="mem_a_old", now=NOW,
    )
    context = TaskStateComposer(tmp_path, tmp_path / "project-a").compose("Implement old SQLite ordering.")
    routing = RoutingOptions(history_mode="ACTIVE_PLUS_RELEVANT_HISTORY")
    router_result = ContextRouter(tmp_path).route(context, routing)
    result = AuthorityResolver(tmp_path).resolve(
        context, router_result, AuthorityOptions(history_mode="ACTIVE_PLUS_RELEVANT_HISTORY")
    )

    assert any(item.status == "IMPLEMENTATION_GAP" for item in result.candidates)
    assert any(conflict.kind == "IMPLEMENTATION_GAP" for conflict in result.conflict_sets)


def test_stale_router_memory_revision_is_never_reinterpreted(tmp_path):
    context, _state = _configured(tmp_path)
    router_result = ContextRouter(tmp_path).route(context)
    document = json.loads((tmp_path / ".claude" / "validated-memory.json").read_text(encoding="utf-8"))
    document["revision"] = 8
    (tmp_path / ".claude" / "validated-memory.json").write_text(json.dumps(document), encoding="utf-8")

    result = AuthorityResolver(tmp_path).resolve(context, router_result)

    assert result.status == "STALE_INPUT"


def test_incomplete_provenance_cannot_break_a_duplicate_identity_tie(tmp_path):
    records = [
        _memory("mem_first", "project-a", "Shared SQLite rule.", fingerprint="shared",),
        _memory("mem_second", "project-a", "Shared SQLite rule.", fingerprint="shared",),
    ]
    records[1]["source"] = ""
    context, _state = _configured(tmp_path, records)
    router_result = ContextRouter(tmp_path).route(context)

    result = AuthorityResolver(tmp_path).resolve(context, router_result)
    statuses = {item.candidate_id: item.status for item in result.candidates}

    assert statuses["mem_first"] == "UNRESOLVED"
    assert statuses["mem_second"] == "UNRESOLVED"


def test_corrupt_canonical_state_is_never_accepted_as_empty_authority(tmp_path):
    context, _state = _configured(tmp_path)
    router_result = ContextRouter(tmp_path).route(context)
    (tmp_path / ".claude" / "project-state.json").write_text("{corrupt", encoding="utf-8")

    result = AuthorityResolver(tmp_path).resolve(context, router_result)

    assert result.status == "FAILED"
    assert result.candidates == ()


def test_corrupt_policy_and_off_mode_fail_closed_without_authority_work(tmp_path):
    context, _state = _configured(tmp_path)
    router_result = ContextRouter(tmp_path).route(context)
    (tmp_path / ".claude" / "authority-resolver.json").write_text("{corrupt", encoding="utf-8")

    failed = AuthorityResolver(tmp_path).resolve(context, router_result)
    off = AuthorityResolver(tmp_path).resolve(context, router_result, AuthorityOptions(mode="OFF"))

    assert failed.status == "FAILED"
    assert off.status == "FAILED"  # invalid configured policy must never be bypassed


def test_supersession_cycle_is_never_silently_resolved(tmp_path):
    records = [
        _memory("mem_a", "project-a", "Cycle SQLite rule.", status="superseded", superseded_by="mem_b"),
        _memory("mem_b", "project-a", "Cycle SQLite rule.", status="superseded", superseded_by="mem_a"),
    ]
    context, _state = _configured(tmp_path, records)
    routing = RoutingOptions(history_mode="ACTIVE_PLUS_RELEVANT_HISTORY")
    router_result = ContextRouter(tmp_path).route(context, routing)

    result = AuthorityResolver(tmp_path).resolve(
        context, router_result, AuthorityOptions(history_mode="ACTIVE_PLUS_RELEVANT_HISTORY")
    )

    assert result.status == "FAILED"
    assert "cycle" in result.error.casefold()


def test_cli_resolve_round_trip_is_content_safe(tmp_path, capsys):
    context, _state = _configured(tmp_path)
    router_result = ContextRouter(tmp_path).route(context)
    task_path, router_path = tmp_path / "task-state.json", tmp_path / "router-result.json"
    task_path.write_text(json.dumps(context.to_dict()), encoding="utf-8")
    router_path.write_text(json.dumps(router_result.to_dict()), encoding="utf-8")

    exit_code = authority_main(
        [
            "resolve", "--vault", str(tmp_path), "--task-state", str(task_path),
            "--router-result", str(router_path), "--json", "--explain",
        ]
    )
    payload = capsys.readouterr().out

    assert exit_code == 0
    assert "Use atomic SQLite persistence" not in payload
    assert "retrieval_score" not in payload
