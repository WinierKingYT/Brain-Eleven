"""Content-free, deterministic retrieval metrics."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Mapping, Any

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

def metric_summary(selected: Iterable[str], required: Iterable[str], acceptable: Iterable[str], mandatory: Iterable[str], *, k: int, token_counts: Mapping[str, int] | None = None) -> MetricResult:
    ids = tuple(selected)
    if len(ids) > k: raise ValueError("provider returned more than K ranked IDs")
    if len(ids) != len(set(ids)): raise ValueError("selected IDs must be unique")
    req, useful, must = set(required), set(acceptable), set(mandatory)
    relevant = req | useful; n = len(ids); hit = len(set(ids) & relevant)
    precision = (hit / n) if n else (1.0 if not relevant else 0.0)
    recall = (len(set(ids) & req) / len(req)) if req else None
    f1 = (2 * precision * recall / (precision + recall)) if recall is not None and precision and recall else (0.0 if recall is not None else None)
    mrr = next((1.0 / (i + 1) for i, item in enumerate(ids) if item in relevant), 0.0)
    mandatory_recall = (len(set(ids) & must) / len(must)) if must else None
    noise = len(set(ids) - relevant) / max(n, 1)
    if token_counts is None: waste = "unavailable"
    else:
        total = sum(token_counts.get(x, 0) for x in ids); bad = sum(token_counts.get(x, 0) for x in set(ids) - relevant)
        waste = bad / total if total else 0.0
    return MetricResult(precision, recall, f1, mrr, mandatory_recall, noise, waste, n)
