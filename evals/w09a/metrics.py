"""Content-free retrieval metrics for the W-09A evaluation boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


class MetricError(ValueError):
    """Raised when a provider result cannot be scored safely."""


@dataclass(frozen=True)
class MetricResult:
    precision: float | None
    recall: float | None
    f1: float | None
    mrr: float
    mandatory_recall: float | None
    noise_ratio: float
    token_waste: float | str
    selected_count: int


def _ids(values: Iterable[str], field: str, *, sorted_unique: bool = False) -> tuple[str, ...]:
    result = tuple(values)
    if any(not isinstance(value, str) or not value.strip() for value in result):
        raise MetricError(f"{field} contains an invalid identifier")
    if len(result) != len(set(result)):
        raise MetricError(f"{field} must be unique")
    if sorted_unique and result != tuple(sorted(result)):
        raise MetricError(f"{field} must be sorted")
    return result


def metric_summary(
    selected: Iterable[str],
    required: Iterable[str],
    acceptable: Iterable[str],
    mandatory: Iterable[str],
    *,
    k: int,
    token_counts: Mapping[str, int] | None = None,
) -> MetricResult:
    """Calculate the frozen W-09A formulas without inventing token data."""

    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise MetricError("K must be a positive integer")
    ids = _ids(selected, "selected")
    if len(ids) > k:
        raise MetricError("provider returned more than K ranked IDs")
    req = set(_ids(required, "required", sorted_unique=True))
    useful = set(_ids(acceptable, "acceptable", sorted_unique=True))
    must = set(_ids(mandatory, "mandatory", sorted_unique=True))
    if not must.issubset(req):
        raise MetricError("mandatory IDs must be a subset of required IDs")
    if req & useful:
        raise MetricError("required and acceptable IDs must be disjoint")
    relevant = req | useful
    selected_set = set(ids)
    count = len(ids)
    hit = len(selected_set & relevant)
    precision = hit / count if count else (1.0 if not relevant else 0.0)
    recall = len(selected_set & req) / len(req) if req else None
    if recall is None:
        f1 = None
    elif precision == 0.0 or recall == 0.0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    mrr = next((1.0 / (index + 1) for index, value in enumerate(ids) if value in relevant), 0.0)
    mandatory_recall = len(selected_set & must) / len(must) if must else None
    noise_ratio = len(selected_set - relevant) / max(count, 1)
    if token_counts is None:
        token_waste: float | str = "unavailable"
    else:
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in token_counts.values()):
            raise MetricError("token counts must be non-negative integers")
        total = sum(token_counts.get(value, 0) for value in ids)
        noise_tokens = sum(token_counts.get(value, 0) for value in selected_set - relevant)
        token_waste = noise_tokens / total if total else 0.0
    return MetricResult(precision, recall, f1, mrr, mandatory_recall, noise_ratio, token_waste, count)
