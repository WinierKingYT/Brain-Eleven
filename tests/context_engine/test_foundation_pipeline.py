"""Cross-phase contracts for Task → State → Router → Authority → Compiler.

The fixtures intentionally use a temporary vault.  A graduation run therefore
proves the complete read path without mutating any user's canonical data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from authority import AuthorityOptions, AuthorityResolver  # noqa: E402
from context_compiler_v2 import BudgetContract, CompilationRequest, ContextCompilerV2  # noqa: E402
from context_router import ContextRouter, RoutingOptions  # noqa: E402
from project_registry import ProjectRegistry  # noqa: E402
from state_store import StateService  # noqa: E402
from task_state_context import TaskStateComposer  # noqa: E402


NOW = "2026-09-04T00:00:00Z"
SOURCE = {"type": "user", "reference": "foundation-e2e"}


def _memory(memory_id: str, project_id: str | None, content: str, *, status: str = "active", superseded_by: str = "") -> dict:
    return {
        "memory_id": memory_id, "type": "decision", "content": content,
        "confidence": 0.9, "quality_score": 0.9, "source": "test", "timestamp": NOW,
        "related_notes": [], "section": "test", "issues": [], "novelty": 1.0, "is_approved": True,
        "status": status, "resolved_at": "" if status == "active" else NOW,
        "resolved_by": "" if status == "active" else "test", "resolution_note": "",
        "superseded_by": superseded_by, "supersession_note": "",
        "dedup_fingerprint": f"fp-{memory_id}", "scope": "project" if project_id else "global",
        "project": project_id or "", "project_label": project_id or "", "project_id": project_id or "",
    }


def _configured(tmp_path):
    project_a, project_b = tmp_path / "project-a", tmp_path / "project-b"
    registry = ProjectRegistry(tmp_path)
    registry.register(project_a, project_id="project-a")
    registry.register(project_b, project_id="project-b")
    state = StateService(tmp_path)
    state.init_project("project-a", source=SOURCE, now=NOW)
    state.init_project("project-b", source=SOURCE, now=NOW)
    state.set_current_objective(
        "project-a", text="Implement durable persistence", expected_revision=1,
        source=SOURCE, record_id="obj_01J00000000000000000000000", now=NOW,
    )
    path = tmp_path / ".claude" / "validated-memory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 2, "revision": 7, "updated_at": NOW, "validated_at": NOW,
        "summary": {}, "rejected_memory": [], "validated_memory": [
            _memory("mem_current", "project-a", "Use Markdown before SQLite for durable persistence."),
            _memory("mem_old", "project-a", "Use SQLite before Markdown.", status="superseded", superseded_by="mem_current"),
            _memory("mem_global", None, "Use atomic writes for durable data."),
            _memory("mem_foreign", "project-b", "Project B storage design."),
        ],
    }), encoding="utf-8")
    context = TaskStateComposer(tmp_path, project_a).compose("Implement durable persistence ordering.")
    return context, state, path, tmp_path / ".claude" / "project-state.json"


def _pipeline(vault: Path, context, budget: int = 1024):
    route = ContextRouter(vault).route(context, RoutingOptions())
    authority = AuthorityResolver(vault).resolve(context, route, AuthorityOptions())
    bundle = ContextCompilerV2(vault).compile(
        CompilationRequest(context, authority, BudgetContract(budget, minimum_headroom_tokens=32, hard_byte_limit=12_000))
    )
    return route, authority, bundle


def test_pipeline_preserves_scope_lineage_and_canonical_authorities(tmp_path):
    context, _state, memory_path, state_path = _configured(tmp_path)
    before = memory_path.read_bytes(), state_path.read_bytes()

    route, authority, bundle = _pipeline(tmp_path, context)

    assert route.status in {"SUCCESS", "DEGRADED"}
    assert authority.status in {"SUCCESS", "DEGRADED"}
    assert bundle.status in {"SUCCESS", "DEGRADED"}
    assert "mem_foreign" not in {candidate.candidate_id for candidate in route.candidates}
    assert "mem_foreign" not in {candidate.candidate_id for candidate in authority.candidates}
    assert "mem_foreign" not in {candidate.candidate_id for candidate in bundle.selected}
    assert bundle.telemetry["route_id"]
    assert bundle.telemetry["authority_policy_version"] == authority.policy_version
    assert bundle.input_revisions["memory"] == route.input_revisions["memory"] == authority.input_revisions["memory"]
    assert memory_path.read_bytes() == before[0]
    assert state_path.read_bytes() == before[1]


def test_pipeline_refuses_stale_canonical_memory_before_bundle_creation(tmp_path):
    context, _state, memory_path, _state_path = _configured(tmp_path)
    route = ContextRouter(tmp_path).route(context)
    document = json.loads(memory_path.read_text(encoding="utf-8"))
    document["revision"] = 8
    memory_path.write_text(json.dumps(document), encoding="utf-8")

    authority = AuthorityResolver(tmp_path).resolve(context, route)

    assert authority.status == "STALE_INPUT"


def test_pipeline_never_silently_drops_mandatory_state_context(tmp_path):
    context, state, _memory_path, _state_path = _configured(tmp_path)
    state.add_constraint(
        "project-a", text="Preserve durable data. " * 120, expected_revision=2,
        source=SOURCE, record_id="con_01J00000000000000000000000", now=NOW,
    )
    project_root = tmp_path / "project-a"
    context = TaskStateComposer(tmp_path, project_root).compose("Implement durable persistence ordering.")

    _route, _authority, bundle = _pipeline(tmp_path, context, budget=256)

    assert bundle.status == "INSUFFICIENT_BUDGET"
    assert not bundle.selected
    assert "not silently" in bundle.error.casefold() or "mandatory" in bundle.error.casefold()


@pytest.mark.graduation
def test_full_pipeline_is_deterministic_across_one_hundred_identical_runs(tmp_path):
    context, _state, _memory_path, _state_path = _configured(tmp_path)
    results = []
    for _ in range(100):
        route, authority, bundle = _pipeline(tmp_path, context)
        results.append((
            tuple(candidate.candidate_id for candidate in route.candidates),
            tuple(candidate.candidate_id for candidate in authority.candidates),
            tuple(candidate.candidate_id for candidate in bundle.selected),
            tuple(item.reason for item in bundle.omitted),
        ))

    assert len(set(results)) == 1
