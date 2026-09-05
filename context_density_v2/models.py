"""Content-free PRE-09 diversity and context-density contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional


DENSITY_SCHEMA_VERSION = 1
DENSITY_STATUSES = frozenset({"SUCCESS", "DEGRADED", "EMPTY", "STALE_INPUT", "INVALID_INPUT", "SCOPE_ERROR", "FAILED"})
DENSITY_MODES = frozenset({"OFF", "SHADOW"})


class DensityContractError(ValueError):
    """Raised when a PRE-09 contract is malformed."""


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DensityContractError(f"{name} must be a non-empty string")
    return value.strip()


def _unique(values: tuple[str, ...] | list[str], name: str) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        raise DensityContractError(f"{name} must be a sequence")
    normalized = tuple(_string(value, name) for value in values)
    if len(normalized) != len(set(normalized)):
        raise DensityContractError(f"{name} must not contain duplicates")
    return tuple(sorted(normalized))


@dataclass(frozen=True)
class DensityOptions:
    """Trusted, bounded tuning controls for the post-selection layer."""

    mode: str = "SHADOW"
    max_selected: int = 20
    diversity_lambda: float = 0.75

    def __post_init__(self) -> None:
        if self.mode not in DENSITY_MODES:
            raise DensityContractError(f"Unsupported density mode: {self.mode}")
        if isinstance(self.max_selected, bool) or not isinstance(self.max_selected, int) or self.max_selected < 0:
            raise DensityContractError("max_selected must be a non-negative integer")
        if isinstance(self.diversity_lambda, bool) or not isinstance(self.diversity_lambda, (int, float)):
            raise DensityContractError("diversity_lambda must be numeric")
        if not 0.0 <= float(self.diversity_lambda) <= 1.0:
            raise DensityContractError("diversity_lambda must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DensitySelectedCandidate:
    """One content-free candidate after deterministic diversity selection."""

    candidate_id: str
    source_type: str
    project_id: Optional[str]
    content_type: str
    lifecycle: str
    canonical_ref: Mapping[str, Any]
    needs: tuple[str, ...]
    redundancy_group: str
    estimated_tokens: int
    selection_score: float
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _string(self.candidate_id, "candidate_id")
        _string(self.source_type, "source_type")
        _string(self.content_type, "content_type")
        _string(self.lifecycle, "lifecycle")
        _string(self.redundancy_group, "redundancy_group")
        if self.project_id is not None:
            _string(self.project_id, "project_id")
        if not isinstance(self.canonical_ref, Mapping) or not self.canonical_ref:
            raise DensityContractError("canonical_ref must be a non-empty mapping")
        object.__setattr__(self, "needs", _unique(self.needs, "candidate.needs"))
        object.__setattr__(self, "reason_codes", _unique(self.reason_codes, "candidate.reason_codes"))
        if isinstance(self.estimated_tokens, bool) or not isinstance(self.estimated_tokens, int) or self.estimated_tokens < 0:
            raise DensityContractError("estimated_tokens must be a non-negative integer")
        if isinstance(self.selection_score, bool) or not isinstance(self.selection_score, (int, float)):
            raise DensityContractError("selection_score must be numeric")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "source_type": self.source_type,
            "project_id": self.project_id,
            "content_type": self.content_type,
            "lifecycle": self.lifecycle,
            "canonical_ref": dict(sorted(self.canonical_ref.items())),
            "needs": list(self.needs),
            "redundancy_group": self.redundancy_group,
            "estimated_tokens": self.estimated_tokens,
            "selection_score": float(self.selection_score),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class DensityResult:
    """Machine-readable, content-free PRE-09 result and density metrics."""

    status: str
    policy_version: str
    input_revisions: Mapping[str, Any]
    selected: tuple[DensitySelectedCandidate, ...] = ()
    omitted: Mapping[str, str] = field(default_factory=dict)
    metrics: Mapping[str, Any] = field(default_factory=dict)
    need_coverage: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    degraded_reasons: tuple[str, ...] = ()
    error: Optional[str] = None
    telemetry: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in DENSITY_STATUSES:
            raise DensityContractError(f"Unsupported density status: {self.status}")
        _string(self.policy_version, "policy_version")
        if not isinstance(self.input_revisions, Mapping):
            raise DensityContractError("input_revisions must be a mapping")
        ids = tuple(item.candidate_id for item in self.selected)
        if len(ids) != len(set(ids)):
            raise DensityContractError("selected candidates must be unique")
        normalized_coverage = {
            _string(key, "need_coverage key"): _unique(value, "need_coverage values")
            for key, value in self.need_coverage.items()
        }
        object.__setattr__(self, "need_coverage", normalized_coverage)
        object.__setattr__(self, "degraded_reasons", _unique(self.degraded_reasons, "degraded_reasons"))
        if self.error is not None:
            _string(self.error, "error")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DENSITY_SCHEMA_VERSION,
            "status": self.status,
            "policy_version": self.policy_version,
            "input_revisions": dict(self.input_revisions),
            "selected": [item.to_dict() for item in self.selected],
            "omitted": dict(sorted(self.omitted.items())),
            "metrics": dict(self.metrics),
            "need_coverage": {key: list(value) for key, value in sorted(self.need_coverage.items())},
            "degraded_reasons": list(self.degraded_reasons),
            "error": self.error,
            "telemetry": dict(self.telemetry),
        }
