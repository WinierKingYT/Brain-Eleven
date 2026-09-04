"""Strict, deterministic synthetic expectations for Phase 19's hard invariants."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent
SIDECAR_PATH = ROOT / "expectation-sidecar.json"
PUBLIC_CATEGORIES = (
    ("tight_budget", 25), ("large_budget", 15), ("duplicate_heavy", 25),
    ("conflict_heavy", 20), ("current_state_heavy", 20), ("history_heavy", 15),
    ("requirement_heavy", 20), ("profile", 20), ("malicious_context", 20),
)
HOLDOUT_CATEGORIES = (
    ("tight_budget", 8), ("duplicate_heavy", 8), ("conflict_heavy", 6),
    ("current_state_heavy", 6), ("requirement_heavy", 6), ("malicious_context", 6),
)


class CompilerCorpusError(ValueError):
    pass


@dataclass(frozen=True)
class CompilerExpectation:
    case_id: str
    suite: str
    category: str
    budget: int
    expects_insufficient_budget: bool


def load_sidecar() -> Mapping[str, Any]:
    try:
        value = json.loads(SIDECAR_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompilerCorpusError(f"Cannot read compiler sidecar: {exc}") from exc
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version", "privacy", "public_case_count", "holdout_case_count", "categories", "holdout_categories"
    }:
        raise CompilerCorpusError("Compiler sidecar schema is invalid")
    if value["schema_version"] != 1 or value["privacy"] != "synthetic_only":
        raise CompilerCorpusError("Compiler sidecar is not public synthetic corpus v1")
    return value


def _build(suite: str, categories: tuple[tuple[str, int], ...]) -> tuple[CompilerExpectation, ...]:
    values = []
    budgets = (512, 1_024, 2_048, 4_096, 8_192)
    for category, count in categories:
        for index in range(1, count + 1):
            tight = category == "tight_budget"
            values.append(
                CompilerExpectation(
                    case_id=f"compiler_{suite}_{category}_{index:03d}", suite=suite, category=category,
                    budget=512 if tight else budgets[(index - 1) % len(budgets)], expects_insufficient_budget=tight,
                )
            )
    return tuple(values)


def expectations(suite: str = "smoke") -> tuple[CompilerExpectation, ...]:
    public = _build("public", PUBLIC_CATEGORIES)
    holdout = _build("holdout", HOLDOUT_CATEGORIES)
    if suite == "public":
        return public
    if suite == "holdout":
        return holdout
    if suite == "all":
        return public + holdout
    if suite == "smoke":
        return tuple(next(item for item in public if item.category == category) for category, _ in PUBLIC_CATEGORIES[:8])
    raise CompilerCorpusError(f"Unknown compiler suite: {suite}")


def validate_corpus() -> Mapping[str, int]:
    sidecar = load_sidecar()
    public, holdout = expectations("public"), expectations("holdout")
    if len(public) != sidecar["public_case_count"] or len(holdout) != sidecar["holdout_case_count"]:
        raise CompilerCorpusError("Compiler corpus count differs from sidecar")
    if {key: sum(item.category == key for item in public) for key, _ in PUBLIC_CATEGORIES} != dict(sidecar["categories"]):
        raise CompilerCorpusError("Compiler public category counts differ from sidecar")
    if {key: sum(item.category == key for item in holdout) for key, _ in HOLDOUT_CATEGORIES} != dict(sidecar["holdout_categories"]):
        raise CompilerCorpusError("Compiler holdout category counts differ from sidecar")
    return {"public": len(public), "holdout": len(holdout), "total": len(public) + len(holdout)}
