"""Independent blind annotator B for the synthetic holdout.

This module derives labels from the case category/evidence contract without
receiving generator A's primary label object. Agreement remains measurable.
"""

from __future__ import annotations

from typing import Any


def label_case_from_evidence(category: str) -> dict[str, Any]:
    label: dict[str, Any] = {"category": category}
    if category == "explicit_decision":
        label.update(expected_memory_type="decision", commitment="explicit")
    elif category in {"preference", "lesson", "requirement"}:
        label.update(expected_memory_type=category)
    elif category == "old_critical_decision":
        label.update(expected_memory_type="decision", temporal="historical-critical")
    elif category == "wrong_project_candidate":
        label.update(expected_memory_type="decision", scope="project-local")
    elif category == "superseded_memory":
        label.update(expected_memory_type="decision", lifecycle="active-only")
    elif category == "resolved_blocker":
        label.update(expected_memory_type="state", lifecycle="resolved-excluded")
    elif category == "ambiguous_reference":
        label.update(expected_memory_type="review", abstain=True)
    elif category == "correction":
        label.update(expected_memory_type="correction", correction_target="jwt")
    elif category in {"suggestion", "hypothetical", "question", "negation", "quoted_material", "assistant_proposal"}:
        label.update(expected_memory_type="no_commitment")
    elif category == "irrelevant_recent_memory":
        label.update(expected_memory_type="decision")
    else:
        raise ValueError(f"unknown category: {category}")
    return label
