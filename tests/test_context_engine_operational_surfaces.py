"""Operational contracts for versioned configs, caches, and SHADOW-only CLIs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from authority import AuthorityResolver  # noqa: E402
from authority.__main__ import main as authority_main  # noqa: E402
from authority.cache import AuthorityCache  # noqa: E402
from authority.config import AuthorityConfig, AuthorityConfigError  # noqa: E402
from authority.shadow import AuthorityShadowRunner  # noqa: E402
from context_compiler_v2 import BudgetContract  # noqa: E402
from context_compiler_v2.__main__ import main as compiler_main  # noqa: E402
from context_compiler_v2.cache import CompilerCache  # noqa: E402
from context_compiler_v2.config import CompilerConfig, CompilerConfigError  # noqa: E402
from context_compiler_v2.shadow import CompilerShadowRunner  # noqa: E402
from context_router import ContextRouter  # noqa: E402
from context_router.cache import RouterCache  # noqa: E402
from context_router.config import RouterConfig, RouterConfigError  # noqa: E402
from project_registry import ProjectRegistry  # noqa: E402
from state_store import StateService  # noqa: E402
from task_state_context import TaskStateComposer  # noqa: E402


NOW = "2026-09-04T10:00:00Z"
SOURCE = {"type": "user", "reference": "operational-surface"}


def _memory(memory_id: str, project_id: str | None, content: str) -> dict:
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
        "status": "active",
        "resolved_at": "",
        "resolved_by": "",
        "resolution_note": "",
        "superseded_by": "",
        "supersession_note": "",
        "dedup_fingerprint": f"fp-{memory_id}",
        "scope": "project" if project_id else "global",
        "project": project_id or "",
        "project_label": project_id or "",
        "project_id": project_id or "",
    }


def _configured(tmp_path):
    project = tmp_path / "project-a"
    other = tmp_path / "project-b"
    registry = ProjectRegistry(tmp_path)
    registry.register(project, project_id="project-a")
    registry.register(other, project_id="project-b")
    state = StateService(tmp_path)
    state.init_project("project-a", source=SOURCE, now=NOW)
    state.init_project("project-b", source=SOURCE, now=NOW)
    state.set_current_objective(
        "project-a",
        text="Safely implement atomic persistence",
        expected_revision=1,
        source=SOURCE,
        record_id="obj_01J00000000000000000000000",
        now=NOW,
    )
    memory_path = tmp_path / ".claude" / "validated-memory.json"
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "revision": 7,
                "updated_at": NOW,
                "validated_at": NOW,
                "summary": {},
                "validated_memory": [
                    _memory("mem_local", "project-a", "Use atomic persistence after durable storage."),
                    _memory("mem_global", None, "Use atomic writes for durable information."),
                    _memory("mem_foreign", "project-b", "Foreign project persistence detail."),
                ],
                "rejected_memory": [],
            }
        ),
        encoding="utf-8",
    )
    context = TaskStateComposer(tmp_path, project).compose("Implement atomic persistence safely.")
    return context, project


@pytest.mark.parametrize(
    ("filename", "loader", "error", "invalid"),
    [
        ("context-router.json", RouterConfig.load, RouterConfigError, {"schema_version": 2}),
        ("authority-resolver.json", AuthorityConfig.load, AuthorityConfigError, {"schema_version": 2}),
        ("context-compiler-v2.json", CompilerConfig.load, CompilerConfigError, {"schema_version": 2}),
    ],
)
def test_versioned_engine_configs_have_safe_defaults_and_reject_partial_schema(tmp_path, filename, loader, error, invalid):
    assert loader(tmp_path)
    config_path = tmp_path / ".claude" / filename
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(invalid), encoding="utf-8")

    with pytest.raises(error):
        loader(tmp_path)


def test_versioned_engine_configs_accept_only_complete_safe_customizations(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "context-router.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": {"implementation": {"memory_candidate_budget": 31, "memory_types": ["decision"]}},
                "routing": {
                    "allow_implicit_cross_project": False,
                    "retry_on_revision_change": 1,
                    "max_queries_per_route": 17,
                    "max_graph_hops": 2,
                    "strict_min_memory_candidates": 4,
                    "cache_enabled": False,
                },
            }
        ),
        encoding="utf-8",
    )
    (claude / "authority-resolver.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "policy": {
                    "version": "authority-v1",
                    "allow_implicit_cross_project": False,
                    "allow_retrieval_score_authority": False,
                },
                "cache": {"enabled": False, "shadow_retry_on_stale": 0},
            }
        ),
        encoding="utf-8",
    )
    (claude / "context-compiler-v2.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "policy_version": "context-compiler-v2-policy-v1",
                "cache_enabled": False,
                "max_rebalance_iterations": 4,
                "default_mode": "SHADOW",
            }
        ),
        encoding="utf-8",
    )

    assert RouterConfig.load(tmp_path).profiles["implementation"].memory_candidate_budget == 31
    assert AuthorityConfig.load(tmp_path).shadow_retry_on_stale == 0
    assert CompilerConfig.load(tmp_path).max_rebalance_iterations == 4


def test_router_config_rejects_a_partial_profile_map_before_any_route_runs():
    with pytest.raises(RouterConfigError, match="Missing router profiles"):
        RouterConfig(profiles={})


def test_derived_caches_are_revision_bound_content_safe_and_corruption_tolerant(tmp_path):
    revisions = {"memory": 7, "state": {"project-a": 2}}
    reference = {"candidate_ids": ["mem_local"], "policy": "v1"}
    for cache_type in (RouterCache, AuthorityCache):
        cache = cache_type(tmp_path)
        assert cache.load("missing", revisions) is None
        cache.store("route", revisions, reference)
        assert cache.load("route", revisions) == reference
        assert cache.load("route", {"memory": 8}) is None
        cache.path.write_text("{corrupt", encoding="utf-8")
        assert cache.load("route", revisions) is None

    compiler_cache = CompilerCache(tmp_path)
    compiler_cache.store("compile", revisions, reference)
    assert compiler_cache.load("compile", revisions) == reference
    with pytest.raises(ValueError, match="refuses context content"):
        compiler_cache.store("unsafe", revisions, {"content": "private memory text"})
    compiler_cache.path.write_text("{corrupt", encoding="utf-8")
    assert compiler_cache.load("compile", revisions) is None


def test_shadow_runners_and_clis_remain_non_injecting_and_content_free(tmp_path, capsys):
    context, project = _configured(tmp_path)
    route = ContextRouter(tmp_path).route(context)
    resolution = AuthorityResolver(tmp_path).resolve(context, route)
    assert resolution.status in {"SUCCESS", "DEGRADED"}

    authority_router, authority_result = AuthorityShadowRunner(tmp_path, project).run("Implement atomic persistence safely.")
    authority_report = AuthorityShadowRunner.report(authority_router, authority_result)
    compiler_router, compiler_authority, bundle = CompilerShadowRunner(tmp_path, project).run(
        "Implement atomic persistence safely.", BudgetContract(1024, 32, 12_000)
    )
    compiler_report = CompilerShadowRunner.report(compiler_router, compiler_authority, bundle)
    assert authority_report["router"]["status"] in {"SUCCESS", "DEGRADED"}
    assert compiler_report["context_injection"] is False
    assert "Use atomic persistence after durable storage" not in json.dumps(authority_report)
    assert "Use atomic persistence after durable storage" not in json.dumps(compiler_report)

    authority_output = tmp_path / "authority-shadow.json"
    compiler_output = tmp_path / "compiler-shadow.json"
    assert authority_main(
        [
            "shadow", "--vault", str(tmp_path), "--project-root", str(project), "--request", "Implement atomic persistence safely.",
            "--json", "--shadow-report", str(authority_output),
        ]
    ) == 0
    assert compiler_main(
        [
            "shadow", "--vault", str(tmp_path), "--project-root", str(project), "--request", "Implement atomic persistence safely.",
            "--max-context-tokens", "1024", "--minimum-headroom-tokens", "32", "--json", "--manifest-only",
            "--shadow-report", str(compiler_output),
        ]
    ) == 0
    output = capsys.readouterr().out
    assert "Use atomic persistence after durable storage" not in output
    assert "Use atomic persistence after durable storage" not in authority_output.read_text(encoding="utf-8")
    assert "Use atomic persistence after durable storage" not in compiler_output.read_text(encoding="utf-8")
