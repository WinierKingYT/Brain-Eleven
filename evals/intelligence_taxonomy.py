"""Shared evaluation vocabulary for the IG program.

This is an IG-00 shared contract artifact retained for the future IG-01
evaluator.  It declares corpus families, categories and metric names only; it
contains no evaluator, ranking or tuning implementation and does not open
IG-01.  The taxonomy is deliberately separate from the production router and
extractor so a suite cannot appear stronger merely by selecting every
available memory.
"""

from __future__ import annotations

from typing import Mapping


TAXONOMY_VERSION = "ig-01-taxonomy-v1"

TAXONOMY: Mapping[str, tuple[str, ...]] = {
    "retrieval": (
        "exact_relevant_memory",
        "related_relevant_memory",
        "irrelevant_recent_memory",
        "old_critical_decision",
        "cross_project_distractor",
        "superseded_decision",
        "resolved_blocker",
        "preference",
        "lesson",
        "current_state",
        "historical_context",
    ),
    "extraction": (
        "explicit_decision",
        "suggestion",
        "hypothetical",
        "question",
        "correction",
        "negation",
        "preference",
        "lesson",
        "requirement",
        "current_blocker",
        "resolved_blocker",
        "assistant_proposal",
        "quoted_material",
    ),
    "reference_resolution": (
        "previous_decision",
        "cancel_previous_target",
        "pronoun_reference",
        "claim_key_target",
        "ambiguous_reference",
    ),
    "safety": (
        "wrong_project_leakage",
        "forbidden_leakage",
        "resolved_leakage",
        "superseded_leakage",
        "secret_leakage",
    ),
}

METRICS: Mapping[str, tuple[str, ...]] = {
    "retrieval": ("precision", "recall", "f1", "mrr", "noise_ratio", "mandatory_context_recall"),
    "extraction": ("decision_precision", "decision_recall", "false_commitment_rate", "correction_detection"),
    "reference_resolution": ("correct_target_rate", "ambiguous_target_abstention_rate", "false_supersession_rate"),
    "safety": ("wrong_project_leakage", "forbidden_leakage", "resolved_leakage", "superseded_leakage"),
}


def taxonomy_manifest() -> dict[str, object]:
    """Return a stable, serializable taxonomy manifest for corpus reports."""

    return {
        "version": TAXONOMY_VERSION,
        "families": {family: list(categories) for family, categories in TAXONOMY.items()},
        "metrics": {family: list(metrics) for family, metrics in METRICS.items()},
    }


def validate_category(family: str, category: str) -> None:
    """Fail closed when a corpus case uses an unregistered category."""

    if family not in TAXONOMY:
        raise ValueError(f"unknown taxonomy family: {family}")
    if category not in TAXONOMY[family]:
        raise ValueError(f"unknown {family} category: {category}")
