from pathlib import Path
import pytest
from evals.w09a.evaluation import (
    CORPUS_ROOT,
    EvaluationError,
    compare_providers,
    corpus_fingerprint,
    evaluate_selection,
    load_public_tasks,
    run_provider,
)
from evals.w09a.metrics import metric_summary

def test_public_loader_reads_only_dev_and_test():
    tasks = load_public_tasks()
    assert len(tasks) == 130
    assert all(t.task_id for t in tasks)

def test_holdout_is_explicit_and_fingerprinted_separately():
    assert corpus_fingerprint(split="public") != corpus_fingerprint(split="holdout")
    assert len(load_public_tasks(split="holdout")) == 30

def test_metrics_are_frozen_and_select_all_is_penalized():
    m = metric_summary(("a", "b", "c"), ("a",), (), ("a",), k=3)
    assert m.precision == pytest.approx(1/3)
    assert m.recall == 1 and m.f1 == pytest.approx(.5)
    assert m.noise_ratio == pytest.approx(2/3)

def test_metrics_reject_over_k_and_report_token_unavailable():
    with pytest.raises(ValueError): metric_summary(("a", "b"), ("a",), (), ("a",), k=1)
    assert metric_summary((), (), (), (), k=1).token_waste == "unavailable"


def test_public_pair_uses_same_candidates_and_records_real_provider_metrics():
    report = compare_providers(split="public")
    assert report["same_input"] is True
    assert report["evaluation_status"] == {
        "evidence": "verified",
        "quality": "measured",
        "measurement": "complete",
        "promotion": "blocked",
    }
    assert report["source"]["candidate_content_fingerprint"].startswith("sha256:")
    assert report["source"]["candidate_order_fingerprint"].startswith("sha256:")
    assert report["providers"]["v1"]["metrics"]["case_count"] == 130
    assert report["providers"]["v2"]["metrics"]["case_count"] == 130


def test_provider_report_is_content_free_and_hard_safety_counters_are_visible():
    report = run_provider(provider_id="v1", split="public")

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                assert key not in {"prompt", "query", "content", "transcript", "raw"}
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    list(walk(report))
    assert report["safety"]["wrong_project_leakage"] == 0
    assert report["safety"]["forbidden_leakage"] == 0


def test_holdout_guard_rejects_ambiguous_split_name():
    with pytest.raises(EvaluationError):
        corpus_fingerprint(split="all")


def test_holdout_quality_unavailable_remains_explicit_when_a_provider_is_invalid():
    report = compare_providers(split="holdout")
    assert report["evaluation_status"]["evidence"] == "verified"
    assert report["evaluation_status"]["quality"] == "unavailable"
    assert report["evaluation_status"]["measurement"] == "incomplete"
    assert report["evaluation_status"]["promotion"] == "blocked"


def test_selection_unknown_candidate_fails_closed():
    task = load_public_tasks()[0]
    with pytest.raises(EvaluationError):
        evaluate_selection(
            task,
            ("not-in-candidate-pool",),
            k=10,
            candidate_ids=tuple(task.required),
            candidate_metadata={},
        )
