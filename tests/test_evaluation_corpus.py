"""The committed public corpus must stay deterministic, valid, and sizable."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from evals.corpus_builder import (
    EXPECTED_PUBLIC_TASK_COUNT,
    EXPECTED_SUITE_COUNTS,
    check_public_corpus,
    public_task_documents,
)
from evals.schema import load_fixture, load_tasks


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "evals" / "fixtures" / "phase15-contract.json"
CORPUS_ROOT = ROOT / "evals" / "corpus"


def test_generated_public_corpus_is_committed_exactly_and_has_100_plus_cases():
    fixture = load_fixture(FIXTURE_PATH)

    check_public_corpus(CORPUS_ROOT, fixture)
    generated = public_task_documents()

    assert len(generated) == EXPECTED_PUBLIC_TASK_COUNT
    assert len(generated) >= 100
    assert Counter(path.parts[0] for path in generated) == EXPECTED_SUITE_COUNTS


def test_all_public_tasks_validate_together_and_keep_suite_boundaries():
    fixture = load_fixture(FIXTURE_PATH)
    paths = sorted(CORPUS_ROOT.glob("**/*.json"))

    tasks = load_tasks(paths, fixture)

    assert len(tasks) == EXPECTED_PUBLIC_TASK_COUNT + 1  # original dev smoke task
    assert {path.parent.name for path in paths} == {"dev", "test", "holdout"}
    assert all("synthetic" not in task.prompt.casefold() for task in tasks)


def test_active_context_labels_never_cross_project_or_lifecycle_boundaries():
    fixture = load_fixture(FIXTURE_PATH)
    tasks = load_tasks(sorted(CORPUS_ROOT.glob("**/*.json")), fixture)

    for task in tasks:
        for memory_id in (*task.required, *task.useful):
            memory = fixture.memories[memory_id]
            assert memory.status == "active" or task.inactive_allowed
            assert memory.project_id in {None, task.project_id} or task.wrong_project_allowed
