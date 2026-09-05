"""Stable, content-free contracts for PRE-08 retrieval decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional


RETRIEVAL_DECISION_SCHEMA_VERSION = 1
DECISION_STATUSES = frozenset(
    {"SUCCESS", "DEGRADED", "EMPTY", "STALE_INPUT", "SCOPE_ERROR", "FAILED"}
)
DECISION_MODES = frozenset({"OFF", "SHADOW"})
NEED_PRIORITIES = {"critical": 0, "high": 1, "normal": 2}


class RetrievalDecisionContractError(ValueError):
    """Raised when a decision contract is malformed."""


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RetrievalDecisionContractError(f"{name} must be a non-empty string")
    return value.strip()


def _unique(values: tuple[str, ...] | list[str], name: str) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        raise RetrievalDecisionContractError(f"{name} must be a sequence")
    normalized = tuple(_string(value, name) for value in values)
    if len(normalized) != len(set(normalized)):
        raise RetrievalDecisionContractError(f"{name} must not contain duplicates")
    return tuple(sorted(normalized))


@dataclass(frozen=True)
class DecisionOptions:
    """Local tuning knobs that cannot widen Router scope or authority."""

    mode: str = "SHADOW"
    max_selected: int = 20
    allow_history: bool = False

    def __post_init__(self) -> None:
        if self.mode not in DECISION_MODES:
            raise RetrievalDecisionContractError(f"Unsupported decision mode: {self.mode}")
        if isinstance(self.max_selected, bool) or not isinstance(self.max_selected, int) or self.max_selected < 0:
            raise RetrievalDecisionContractError("max_selected must be a non-negative integer")
        if not isinstance(self.allow_history, bool):
            raise RetrievalDecisionContractError("allow_history must be boolean")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Need:
    """One coarse context need; it is a ranking hint, not an authority claim."""

    need_id: str
    kind: str
    priority: str = "normal"
    domain: Optional[str] = None

    def __post_init__(self) -> None:
        _string(self.need_id, "need.need_id")
        _string(self.kind, "need.kind")
        if self.priority not in NEED_PRIORITIES:
            raise RetrievalDecisionContractError(f"Unsupported need priority: {self.priority}")
        if self.domain is not None:
            _string(self.domain, "need.domain")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NeedPlan:
    """Deterministic task-derived context need plan."""

    needs: tuple[Need, ...] = ()

    def __post_init__(self) -> None:
        ids = tuple(need.need_id for need in self.needs)
        if len(ids) != len(set(ids)):
            raise RetrievalDecisionContractError("NeedPlan IDs must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": RETRIEVAL_DECISION_SCHEMA_VERSION, "needs": [n.to_dict() for n in self.needs]}


@dataclass(frozen=True)
class SelectedCandidate:
    """A content-free candidate selected for a task need."""

    candidate_id: str
    source_type: str
    project_id: Optional[str]
    content_type: str
    lifecycle: str
    canonical_ref: Mapping[str, Any]
    needs: tuple[str, ...]
    channels: tuple[str, ...]
    decision_score: float
    retrieval_score: float
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _string(self.candidate_id, "candidate_id")
        _string(self.source_type, "source_type")
        _string(self.content_type, "content_type")
        _string(self.lifecycle, "lifecycle")
        if self.project_id is not None:
            _string(self.project_id, "project_id")
        if not isinstance(self.canonical_ref, Mapping) or not self.canonical_ref:
            raise RetrievalDecisionContractError("canonical_ref must be a non-empty mapping")
        object.__setattr__(self, "needs", _unique(self.needs, "candidate.needs"))
        object.__setattr__(self, "channels", _unique(self.channels, "candidate.channels"))
        object.__setattr__(self, "reason_codes", _unique(self.reason_codes, "candidate.reason_codes"))
        for value, name in ((self.decision_score, "decision_score"), (self.retrieval_score, "retrieval_score")):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise RetrievalDecisionContractError(f"{name} must be numeric")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "source_type": self.source_type,
            "project_id": self.project_id,
            "content_type": self.content_type,
            "lifecycle": self.lifecycle,
            "canonical_ref": dict(sorted(self.canonical_ref.items())),
            "needs": list(self.needs),
            "channels": list(self.channels),
            "decision_score": float(self.decision_score),
            "retrieval_score": float(self.retrieval_score),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class DecisionResult:
    """Machine-safe decision output; memory text is intentionally absent."""

    status: str
    policy_version: str
    input_revisions: Mapping[str, Any]
    need_plan: NeedPlan
    selected: tuple[SelectedCandidate, ...] = ()
    omitted: Mapping[str, str] = field(default_factory=dict)
    degraded_reasons: tuple[str, ...] = ()
    error: Optional[str] = None
    telemetry: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in DECISION_STATUSES:
            raise RetrievalDecisionContractError(f"Unsupported decision status: {self.status}")
        _string(self.policy_version, "policy_version")
        if not isinstance(self.input_revisions, Mapping):
            raise RetrievalDecisionContractError("input_revisions must be a mapping")
        ids = tuple(item.candidate_id for item in self.selected)
        if len(ids) != len(set(ids)):
            raise RetrievalDecisionContractError("selected candidates must be unique")
        object.__setattr__(self, "degraded_reasons", _unique(self.degraded_reasons, "degraded_reasons"))
        if self.error is not None:
            _string(self.error, "error")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RETRIEVAL_DECISION_SCHEMA_VERSION,
            "status": self.status,
            "policy_version": self.policy_version,
            "input_revisions": dict(self.input_revisions),
            "need_plan": self.need_plan.to_dict(),
            "selected": [item.to_dict() for item in self.selected],
            "omitted": dict(sorted(self.omitted.items())),
            "degraded_reasons": list(self.degraded_reasons),
            "error": self.error,
            "telemetry": dict(self.telemetry),
        }
