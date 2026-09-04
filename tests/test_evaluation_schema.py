"""Phase 15 corpus contracts must fail before a mislabeled suite reaches CI."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from evals.schema import (
    CorpusValidationError,
    load_fixture,
    load_tasks,
    parse_fixture,
    validate_fixture_documents,
    validate_task_documents,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "evals" / "fixtures" / "phase15-contract.json"
TASK_PATH = ROOT / "evals" / "corpus" / "dev" / "eleven-capture-atomic-save-001.json"


def _fixture_document():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _task_document():
    return json.loads(TASK_PATH.read_text(encoding="utf-8"))


def test_contract_fixture_and_dev_task_load_from_disk():
    fixture = load_fixture(FIXTURE_PATH)

    tasks = load_tasks([TASK_PATH], fixture)

    assert fixture.fixture_id == "phase15_contract"
    assert tasks[0].task_id == "eleven_capture_atomic_save_001"
    assert tasks[0].required == (
        "mem_markdown_source_of_truth",
        "mem_markdown_before_sqlite",
    )


def test_rejects_duplicate_memory_identity_in_fixture():
    document = _fixture_document()
    duplicate = copy.deepcopy(document["memories"][0])
    document["memories"].append(duplicate)

    with pytest.raises(CorpusValidationError, match="duplicate memory_id"):
        parse_fixture(document)


def test_rejects_unknown_memory_label():
    fixture = parse_fixture(_fixture_document())
    document = _task_document()
    document["expected_context"]["required"].append("mem_missing")

    with pytest.raises(CorpusValidationError, match="unknown memory_id"):
        validate_task_documents([document], fixture)


def test_rejects_overlapping_context_labels():
    fixture = parse_fixture(_fixture_document())
    document = _task_document()
    document["expected_context"]["forbidden"].append("mem_markdown_source_of_truth")

    with pytest.raises(CorpusValidationError, match="both required and forbidden"):
        validate_task_documents([document], fixture)


def test_rejects_empty_expectation_set():
    fixture = parse_fixture(_fixture_document())
    document = _task_document()
    document["expected_context"] = {"required": [], "useful": [], "forbidden": []}

    with pytest.raises(CorpusValidationError, match="at least one labeled memory"):
        validate_task_documents([document], fixture)


def test_rejects_unknown_task_project():
    fixture = parse_fixture(_fixture_document())
    document = _task_document()
    document["task"]["project_id"] = "unknown-project"

    with pytest.raises(CorpusValidationError, match="unknown project_id"):
        validate_task_documents([document], fixture)


def test_rejects_unsupported_memory_lifecycle():
    document = _fixture_document()
    document["memories"][0]["status"] = "retired"

    with pytest.raises(CorpusValidationError, match="must be one of"):
        parse_fixture(document)


def test_rejects_duplicate_fixture_identity():
    document = _fixture_document()

    with pytest.raises(CorpusValidationError, match="duplicate fixture_id"):
        validate_fixture_documents([document, copy.deepcopy(document)])


def test_rejects_duplicate_task_identity():
    fixture = parse_fixture(_fixture_document())
    document = _task_document()

    with pytest.raises(CorpusValidationError, match="duplicate task_id"):
        validate_task_documents([document, copy.deepcopy(document)], fixture)
