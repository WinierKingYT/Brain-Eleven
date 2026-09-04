"""Deterministic, production-independent context-selection metrics.

The evaluator consumes normalized provider results plus the synthetic fixture's
ground truth.  It never imports a production retriever, so an algorithm cannot
silently redefine the benchmark it is measured against.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .contracts import NormalizedEvaluationResult
from .schema import GoldenTask, VaultFixture


SUPPORTED = "supported"
PASS = "pass"
FAIL = "fail"
NOT_APPLICABLE = "not_applicable"
UNSUPPORTED = "unsupported"
_VALID_INVARIANT_STATES = frozenset({PASS, FAIL, NOT_APPLICABLE, UNSUPPORTED})


class EvaluationMetricError(ValueError):
    """Raised when a result cannot be compared safely to a golden task."""


@dataclass(frozen=True)
class CaseMetrics:
    """Deterministic measurements for one task/provider result pair."""

    task_id: str
    selected_count: int
    relevant_selected_count: int
    required_count: int
    required_selected_count: int
    useful_selected_count: int
    context_precision: float
    context_recall: Optional[float]
    wrong_project_selected_count: int
    wrong_project_leakage_count: int
    forbidden_context_count: int
    superseded_selected_count: int
    superseded_leakage_count: int
    resolved_selected_count: int
    resolved_leakage_count: int
    unlabeled_selection_count: int

    def as_dict(self) -> dict[str, Any]:
        """Return stable primitive values suitable for JSON reports."""

        return {
            "task_id": self.task_id,
            "selected_count": self.selected_count,
            "relevant_selected_count": self.relevant_selected_count,
            "required_count": self.required_count,
            "required_selected_count": self.required_selected_count,
            "useful_selected_count": self.useful_selected_count,
            "context_precision": self.context_precision,
            "context_recall": self.context_recall,
            "wrong_project_selected_count": self.wrong_project_selected_count,
            "wrong_project_leakage_count": self.wrong_project_leakage_count,
            "forbidden_context_count": self.forbidden_context_count,
            "superseded_selected_count": self.superseded_selected_count,
            "superseded_leakage_count": self.superseded_leakage_count,
            "resolved_selected_count": self.resolved_selected_count,
            "resolved_leakage_count": self.resolved_leakage_count,
            "unlabeled_selection_count": self.unlabeled_selection_count,
        }


@dataclass(frozen=True)
class CaseEvaluation:
    """Metrics and deterministic safety-gate outcomes for one golden task."""

    metrics: CaseMetrics
    invariants: Mapping[str, str]
    selected_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        normalized_invariants = dict(sorted(self.invariants.items()))
        invalid = {
            name: state
            for name, state in normalized_invariants.items()
            if state not in _VALID_INVARIANT_STATES
        }
        if invalid:
            raise EvaluationMetricError(f"invalid invariant states: {invalid}")
        object.__setattr__(self, "invariants", normalized_invariants)
        object.__setattr__(self, "selected_ids", tuple(self.selected_ids))

    @property
    def violations(self) -> tuple[str, ...]:
        """Return hard invariant names that failed for this case."""

        return tuple(name for name, state in self.invariants.items() if state == FAIL)

    @property
    def passed(self) -> bool:
        """Unsupported or inapplicable capabilities do not masquerade as passes."""

        return not self.violations

    def as_dict(self) -> dict[str, Any]:
        """Return an auditable, machine-readable per-case report."""

        return {
            "task_id": self.metrics.task_id,
            "selected_ids": list(self.selected_ids),
            "metrics": self.metrics.as_dict(),
            "invariants": dict(self.invariants),
            "violations": list(self.violations),
            "passed": self.passed,
        }


def _capability_is_supported(result: NormalizedEvaluationResult, capability: str) -> bool:
    return result.capabilities.get(capability) == SUPPORTED


def _invariant_state(
    *,
    applies: bool,
    supported: bool,
    violation_count: int,
) -> str:
    if not applies:
        return NOT_APPLICABLE
    if not supported:
        return UNSUPPORTED
    return FAIL if violation_count else PASS


def _validate_inputs(
    task: GoldenTask,
    fixture: VaultFixture,
    result: NormalizedEvaluationResult,
) -> None:
    if result.task_id != task.task_id:
        raise EvaluationMetricError(
            f"result task_id {result.task_id!r} does not match task {task.task_id!r}"
        )
    if result.project_id != task.project_id:
        raise EvaluationMetricError("result project_id does not match the golden task")
    if not isinstance(fixture, VaultFixture):
        raise EvaluationMetricError("fixture must be a VaultFixture")


def evaluate_selection(
    task: GoldenTask,
    fixture: VaultFixture,
    result: NormalizedEvaluationResult,
) -> CaseEvaluation:
    """Measure a normalized selection against deterministic fixture labels.

    Precision treats required and useful records as relevant.  If no context is
    selected, precision is ``0.0`` rather than an artificial perfect score;
    recall is ``None`` only when a task has no required context at all.
    """

    _validate_inputs(task, fixture, result)
    selected_items = result.selected_items
    selected_ids = tuple(item.id for item in selected_items)
    selected_id_set = frozenset(selected_ids)
    required_ids = frozenset(task.required)
    useful_ids = frozenset(task.useful)
    forbidden_ids = frozenset(task.forbidden)
    relevant_ids = required_ids | useful_ids

    required_selected = required_ids & selected_id_set
    useful_selected = useful_ids & selected_id_set
    relevant_selected = relevant_ids & selected_id_set
    mapped_items = tuple((item, fixture.memories.get(item.id)) for item in selected_items)
    # A synthetic vault can deliberately contain generated noise that is not a
    # golden label. It is irrelevant and therefore lowers precision, but is not
    # a malformed provider result or a hard safety violation.
    unlabeled_count = sum(memory is None for _, memory in mapped_items)
    # Scope and lifecycle safety are measured from the immutable fixture, not
    # from provider-supplied metadata. A provider must not be able to relabel
    # a foreign record as belonging to the current project and thereby hide a
    # leakage violation.
    foreign_count = sum(
        memory is not None
        and memory.project_id is not None
        and memory.project_id != task.project_id
        for _, memory in mapped_items
    )
    superseded_count = sum(
        memory is not None and memory.status == "superseded" for _, memory in mapped_items
    )
    resolved_count = sum(
        memory is not None and memory.status == "resolved" for _, memory in mapped_items
    )
    forbidden_count = len(forbidden_ids & selected_id_set)
    selected_count = len(selected_items)
    precision = len(relevant_selected) / selected_count if selected_count else 0.0
    recall = len(required_selected) / len(required_ids) if required_ids else None

    wrong_project_leakage = 0 if task.wrong_project_allowed else foreign_count
    superseded_leakage = 0 if task.inactive_allowed else superseded_count
    resolved_leakage = 0 if task.inactive_allowed else resolved_count
    metrics = CaseMetrics(
        task_id=task.task_id,
        selected_count=selected_count,
        relevant_selected_count=len(relevant_selected),
        required_count=len(required_ids),
        required_selected_count=len(required_selected),
        useful_selected_count=len(useful_selected),
        context_precision=precision,
        context_recall=recall,
        wrong_project_selected_count=foreign_count,
        wrong_project_leakage_count=wrong_project_leakage,
        forbidden_context_count=forbidden_count,
        superseded_selected_count=superseded_count,
        superseded_leakage_count=superseded_leakage,
        resolved_selected_count=resolved_count,
        resolved_leakage_count=resolved_leakage,
        unlabeled_selection_count=unlabeled_count,
    )
    invariants = {
        "forbidden_context": FAIL if forbidden_count else PASS,
        "wrong_project_leakage": _invariant_state(
            applies=not task.wrong_project_allowed,
            supported=_capability_is_supported(result, "scope_isolation"),
            violation_count=wrong_project_leakage,
        ),
        "superseded_lifecycle_leakage": _invariant_state(
            applies=not task.inactive_allowed,
            supported=_capability_is_supported(result, "lifecycle_filtering"),
            violation_count=superseded_leakage,
        ),
        "resolved_lifecycle_leakage": _invariant_state(
            applies=not task.inactive_allowed,
            supported=_capability_is_supported(result, "lifecycle_filtering"),
            violation_count=resolved_leakage,
        ),
    }
    return CaseEvaluation(metrics=metrics, invariants=invariants, selected_ids=selected_ids)
