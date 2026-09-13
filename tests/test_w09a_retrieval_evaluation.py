from pathlib import Path
import pytest
from evals.w09a.evaluation import CORPUS_ROOT, corpus_fingerprint, load_public_tasks
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
