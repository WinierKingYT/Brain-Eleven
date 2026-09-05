"""Package-specific coverage gates cannot be hidden by legacy scripts."""

from __future__ import annotations

import json

from scripts.check_context_engine_coverage import evaluate_coverage, main


def _file(statements: int, covered: int) -> dict:
    return {"summary": {"num_statements": statements, "covered_lines": covered}}


def _document(*, core_covered: int = 85, total: float = 85.0) -> dict:
    return {
        "totals": {"percent_covered": total},
        "files": {
            "context_router/router.py": _file(100, core_covered),
            "authority/resolver.py": _file(100, core_covered),
            "context_compiler_v2/compiler.py": _file(100, core_covered),
            "retrieval_decision_v2/engine.py": _file(100, core_covered),
            "scripts/task_model.py": _file(100, core_covered),
            "scripts/task_state_context.py": _file(100, core_covered),
            "scripts/state_store.py": _file(100, core_covered),
            "scripts/state_resolver.py": _file(100, core_covered),
            "scripts/state.py": _file(100, core_covered),
        },
    }


def test_context_engine_coverage_accepts_global_and_package_thresholds():
    result = evaluate_coverage(_document())

    assert result["status"] == "pass"
    assert not result["failures"]


def test_context_engine_coverage_rejects_a_weak_core_package_even_when_global_is_green():
    result = evaluate_coverage(_document(core_covered=84, total=95.0))

    assert result["status"] == "fail"
    assert any(failure.startswith("context_router=") for failure in result["failures"])


def test_context_engine_coverage_rejects_missing_core_package():
    document = _document()
    del document["files"]["authority/resolver.py"]

    result = evaluate_coverage(document)

    assert result["status"] == "fail"
    assert "authority=missing" in result["failures"]


def test_context_engine_coverage_cli_emits_machine_readable_gate_result(tmp_path, capsys):
    coverage = tmp_path / "coverage.json"
    coverage.write_text(json.dumps(_document()), encoding="utf-8")

    assert main(["--coverage", str(coverage)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "pass"
