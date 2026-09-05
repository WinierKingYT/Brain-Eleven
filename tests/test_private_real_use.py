from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.private_eval import (
    PrivateEvaluationCase,
    PrivateEvaluationError,
    UsageTelemetryError,
    UsageTelemetryStore,
    evaluate_case,
    load_case,
    write_case,
)


def _case() -> PrivateEvaluationCase:
    case = PrivateEvaluationCase.empty("case-1", "task-1", "brain-eleven")
    return (
        case.with_annotation("mem-required", "required")
        .with_annotation("mem-helpful", "helpful")
        .with_annotation("mem-noise", "noise")
        .with_annotation("mem-forbidden", "forbidden")
    )


def test_private_case_round_trip_is_content_free(tmp_path: Path):
    private_root = tmp_path / "private"
    path = write_case(_case(), private_root / "case.json", private_root=private_root)

    loaded = load_case(path, private_root=private_root)

    assert loaded.as_dict() == _case().as_dict()
    assert "content" not in path.read_text(encoding="utf-8")


def test_private_case_rejects_content_and_outside_paths(tmp_path: Path):
    private_root = tmp_path / "private"
    document = _case().as_dict()
    document["prompt"] = "private prompt"
    with pytest.raises(PrivateEvaluationError):
        from evals.private_eval.contracts import parse_case

        parse_case(document)

    with pytest.raises(PrivateEvaluationError):
        write_case(_case(), tmp_path / "outside.json", private_root=private_root)


def test_private_annotations_replace_one_label_and_score_hard_leakage():
    case = _case().with_annotation("mem-helpful", "noise")

    report = evaluate_case(case, ["mem-required", "mem-noise", "mem-forbidden", "unknown"])

    assert report["required_recall"] == 1.0
    assert report["relevant_precision"] == 0.25
    assert report["forbidden_selected"] == 1
    assert report["noise_selected"] == 1
    assert report["unknown_selected"] == 1
    assert report["hard_gates"]["forbidden_leakage"] is False


def test_usage_telemetry_records_observable_events_without_used_count(tmp_path: Path):
    store = UsageTelemetryStore(tmp_path)
    store.record("mem-1", "selected", occurred_at="2026-09-06T10:00:00Z")
    document = store.record("mem-1", "user_helpful", occurred_at="2026-09-06T10:01:00Z")

    record = document["memory"]["mem-1"]
    assert record["selected_count"] == 1
    assert record["user_helpful_count"] == 1
    assert "used_count" not in record
    assert "content" not in json.dumps(document)


def test_usage_telemetry_rejects_unknown_event_and_corrupt_store(tmp_path: Path):
    store = UsageTelemetryStore(tmp_path)
    with pytest.raises(UsageTelemetryError):
        store.record("mem-1", "used")

    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{\"memory\": {}}", encoding="utf-8")
    with pytest.raises(UsageTelemetryError):
        store.load()
