"""Phase 19 corpus, CLI, and evaluator regression coverage."""

from __future__ import annotations

import json

from context_compiler_v2.__main__ import main as compiler_main
from evals.compiler_v2_benchmark import run_compiler_benchmark
from evals.compiler_v2.corpus import expectations, load_sidecar, validate_corpus
from evals.compiler_v2_evaluation import run_compiler_evaluation

from .test_context_compiler_v2 import _configured, _resolved


def test_compiler_corpus_has_180_public_40_holdout_and_multi_budget_coverage():
    assert validate_corpus() == {"public": 180, "holdout": 40, "total": 220}
    assert load_sidecar()["privacy"] == "synthetic_only"
    assert len(expectations("smoke")) == 8
    assert {case.budget for case in expectations("public")} >= {512, 1024, 2048, 4096, 8192}


def test_compiler_smoke_evaluation_enforces_hard_safety_invariants():
    report = run_compiler_evaluation(suite="smoke")

    assert report["case_count"] == 8
    assert report["expectations_passed"] == 8
    assert all(value["state"] == "pass" for value in report["invariants"].values())


def test_compile_cli_manifest_never_persists_or_prints_memory_content(tmp_path, capsys):
    context, _state, _project = _configured(tmp_path)
    resolution = _resolved(tmp_path, context)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({
        "schema_version": 1,
        "task_state": context.to_dict(),
        "resolution_result": resolution.to_dict(),
        "budget": {"max_context_tokens": 1024, "minimum_headroom_tokens": 32, "hard_byte_limit": 12000},
    }), encoding="utf-8")

    exit_code = compiler_main([
        "compile", "--vault", str(tmp_path), "--request-file", str(request_path), "--manifest-only", "--json",
    ])
    payload = capsys.readouterr().out

    assert exit_code == 0
    assert "Use atomic SQLite persistence" not in payload
    assert "rendered_context" not in payload


def test_shadow_cli_is_non_injecting_and_supports_explicit_history(tmp_path, capsys):
    _context, _state, project = _configured(tmp_path)

    exit_code = compiler_main([
        "shadow", "--vault", str(tmp_path), "--project-root", str(project),
        "--request", "Implement atomic SQLite persistence.", "--allow-history", "--manifest-only", "--json",
    ])
    payload = capsys.readouterr().out

    assert exit_code == 0
    assert "Use atomic SQLite persistence" not in payload
    assert "rendered_context" not in payload


def test_compiler_benchmark_reports_p50_and_p95_without_a_latency_gate():
    report = run_compiler_benchmark(sizes=(4,), samples=2)

    assert report["hard_latency_gate"] is False
    assert report["measurement_scope"] == "compile_after_fixed_router_and_authority"
    assert report["results"][0]["p50_ms"] >= 0
    assert report["results"][0]["p95_ms"] >= report["results"][0]["p50_ms"]
