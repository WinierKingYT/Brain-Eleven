"""Small, strict value objects shared by the IG01-C evaluator.

These contracts intentionally contain no production types.  A provider or
algorithm must first translate its output into primitive mappings before the
evaluator can inspect it.  Reports use only identifiers, counts and hashes;
prompt, transcript and memory content never appear in evaluator output.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


EVALUATOR_VERSION = "1.0.0"
REPORT_SCHEMA_VERSION = 1

# The seven absolute-zero gates are fixed by IG01-A.  The two near-zero gates
# require an explicit review record for every positive event.
HARD_ZERO_GATES = (
    "wrong_project_leakage",
    "forbidden_leakage",
    "assistant_as_user_commitment",
    "cross_project_target",
    "superseded_leakage",
    "resolved_leakage",
    "lifecycle_cycle",
)
NEAR_ZERO_GATES = {
    "false_supersession": 0.01,
    "false_commitment": 0.01,
}
ALL_GATES = HARD_ZERO_GATES + tuple(NEAR_ZERO_GATES)


class EvaluationContractError(ValueError):
    """Raised when evaluator input or output violates the frozen contract."""


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationContractError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise EvaluationContractError(f"{field} must be finite")
    return result


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvaluationContractError(f"{field} must be a non-negative integer")
    return value


@dataclass(frozen=True)
class MetricValue:
    """One auditable metric with explicit denominator and applicability."""

    value: float | None
    numerator: float
    denominator: float
    not_applicable: bool = False
    empty_selection: bool = False

    def __post_init__(self) -> None:
        if self.value is not None:
            object.__setattr__(self, "value", _finite(self.value, "metric value"))
        object.__setattr__(self, "numerator", _finite(self.numerator, "metric numerator"))
        object.__setattr__(self, "denominator", _finite(self.denominator, "metric denominator"))
        if self.numerator < 0 or self.denominator < 0:
            raise EvaluationContractError("metric numerator and denominator must be non-negative")
        if self.not_applicable and self.value is not None:
            raise EvaluationContractError("not_applicable metrics must have a null value")
        if not self.not_applicable and self.value is None:
            raise EvaluationContractError("applicable metrics must have a numeric value")
        if self.empty_selection and self.denominator != 0:
            raise EvaluationContractError("empty_selection requires a zero denominator")

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "not_applicable": self.not_applicable,
            "empty_selection": self.empty_selection,
        }


@dataclass(frozen=True)
class SafetyEvent:
    """A content-free hard-gate event requiring deterministic review."""

    gate: str
    case_id: str
    detail_code: str
    review_required: bool = False

    def __post_init__(self) -> None:
        for field in ("gate", "case_id", "detail_code"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise EvaluationContractError(f"{field} must be a non-empty string")
        if self.gate not in ALL_GATES and self.gate not in {"secret_leakage", "authority_violation"}:
            raise EvaluationContractError(f"unknown safety gate: {self.gate}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "case_id": self.case_id,
            "detail_code": self.detail_code,
            "review_required": self.review_required,
        }
