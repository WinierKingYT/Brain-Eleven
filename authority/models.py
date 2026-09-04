"""Content-safe contracts for Phase 18 authority resolution.

Authority is deliberately distinct from retrieval.  These models never carry
memory or state text and therefore remain safe for caches, telemetry, reports,
and command-line output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


AUTHORITY_SCHEMA_VERSION = 1
AUTHORITY_STATUSES = frozenset(
    {"SUCCESS", "DEGRADED", "EMPTY", "STALE_INPUT", "INVALID_INPUT", "SCOPE_ERROR", "FAILED"}
)
AUTHORITY_MODES = frozenset({"OFF", "SHADOW"})
SCOPE_MODES = frozenset({"CURRENT_PROJECT", "GLOBAL_ONLY", "SELECTED_PROJECTS"})
HISTORY_MODES = frozenset({"ACTIVE_ONLY", "ACTIVE_PLUS_RELEVANT_HISTORY", "HISTORY_ONLY"})
RESOLUTION_STATUSES = frozenset(
    {
        "AUTHORITATIVE",
        "SUPPORTING",
        "HISTORICAL",
        "SUPERSEDED",
        "CONTESTED",
        "UNRESOLVED",
        "IMPLEMENTATION_GAP",
        "INAPPLICABLE",
        "INVALID",
    }
)
RESOLUTION_ACTIONS = frozenset(
    {
        "ACCEPT_SINGLE",
        "PREFER",
        "KEEP_BOTH",
        "KEEP_BOTH_TEMPORAL",
        "KEEP_BOTH_SCOPED",
        "MARK_IMPLEMENTATION_GAP",
        "MARK_CONTESTED",
        "REQUIRES_CLARIFICATION",
        "ABSTAIN",
        "INVALID",
    }
)


class AuthorityContractError(ValueError):
    """Raised for an incoherent caller-facing authority contract."""


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuthorityContractError(f"{field} must be a non-empty string")
    return value.strip()


def _unique_strings(values: tuple[str, ...] | list[str], field: str) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        raise AuthorityContractError(f"{field} must be a sequence")
    normalized = tuple(_string(value, field) for value in values)
    if len(normalized) != len(set(normalized)):
        raise AuthorityContractError(f"{field} must not contain duplicates")
    return tuple(sorted(normalized))


@dataclass(frozen=True)
class AuthorityOptions:
    """Trusted policy; task text and RouterResult cannot grant permissions."""

    scope_mode: str = "CURRENT_PROJECT"
    selected_project_ids: tuple[str, ...] = ()
    include_global: bool = True
    history_mode: str = "ACTIVE_ONLY"
    mode: str = "SHADOW"

    def __post_init__(self) -> None:
        if self.scope_mode not in SCOPE_MODES:
            raise AuthorityContractError(f"Unsupported scope_mode: {self.scope_mode}")
        if self.history_mode not in HISTORY_MODES:
            raise AuthorityContractError(f"Unsupported history_mode: {self.history_mode}")
        if self.mode not in AUTHORITY_MODES:
            raise AuthorityContractError(f"Unsupported authority mode: {self.mode}")
        if not isinstance(self.include_global, bool):
            raise AuthorityContractError("include_global must be boolean")
        selected = _unique_strings(self.selected_project_ids, "selected_project_ids")
        if self.scope_mode == "SELECTED_PROJECTS" and not selected:
            raise AuthorityContractError("SELECTED_PROJECTS requires selected_project_ids")
        if self.scope_mode != "SELECTED_PROJECTS" and selected:
            raise AuthorityContractError("selected_project_ids require SELECTED_PROJECTS")
        object.__setattr__(self, "selected_project_ids", selected)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope_mode": self.scope_mode,
            "selected_project_ids": list(self.selected_project_ids),
            "include_global": self.include_global,
            "history_mode": self.history_mode,
            "mode": self.mode,
        }


@dataclass(frozen=True)
class ClaimEnvelope:
    """A metadata-only claim representation; it contains no source text."""

    candidate_id: str
    claim_class: str
    project_id: Optional[str]
    scope: str
    lifecycle: str
    provenance: str
    dedup_fingerprint: Optional[str] = None
    superseded_by: Optional[str] = None
    state_kind: Optional[str] = None

    def __post_init__(self) -> None:
        _string(self.candidate_id, "claim.candidate_id")
        _string(self.claim_class, "claim.claim_class")
        _string(self.scope, "claim.scope")
        _string(self.lifecycle, "claim.lifecycle")
        _string(self.provenance, "claim.provenance")
        if self.project_id is not None:
            _string(self.project_id, "claim.project_id")
        if self.dedup_fingerprint is not None:
            _string(self.dedup_fingerprint, "claim.dedup_fingerprint")
        if self.superseded_by is not None:
            _string(self.superseded_by, "claim.superseded_by")
        if self.state_kind is not None:
            _string(self.state_kind, "claim.state_kind")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "claim_class": self.claim_class,
            "project_id": self.project_id,
            "scope": self.scope,
            "lifecycle": self.lifecycle,
            "provenance": self.provenance,
            "dedup_fingerprint": self.dedup_fingerprint,
            "superseded_by": self.superseded_by,
            "state_kind": self.state_kind,
        }


@dataclass(frozen=True)
class ResolutionCandidate:
    """One Router candidate after authority assessment, without content."""

    candidate_id: str
    source_type: str
    project_id: Optional[str]
    canonical_ref: Mapping[str, Any]
    claim: ClaimEnvelope
    status: str
    action: str
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _string(self.candidate_id, "resolution.candidate_id")
        _string(self.source_type, "resolution.source_type")
        if self.project_id is not None:
            _string(self.project_id, "resolution.project_id")
        if not isinstance(self.canonical_ref, Mapping) or not self.canonical_ref:
            raise AuthorityContractError("resolution.canonical_ref must be a non-empty mapping")
        if self.status not in RESOLUTION_STATUSES:
            raise AuthorityContractError(f"Unsupported resolution status: {self.status}")
        if self.action not in RESOLUTION_ACTIONS:
            raise AuthorityContractError(f"Unsupported resolution action: {self.action}")
        object.__setattr__(self, "reason_codes", _unique_strings(self.reason_codes, "resolution.reason_codes"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "source_type": self.source_type,
            "project_id": self.project_id,
            "canonical_ref": dict(sorted(self.canonical_ref.items())),
            "claim": self.claim.to_dict(),
            "status": self.status,
            "action": self.action,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class ConflictSet:
    """A deterministic group of explicitly comparable candidates."""

    conflict_id: str
    kind: str
    candidate_ids: tuple[str, ...]
    action: str
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _string(self.conflict_id, "conflict.conflict_id")
        _string(self.kind, "conflict.kind")
        object.__setattr__(self, "candidate_ids", _unique_strings(self.candidate_ids, "conflict.candidate_ids"))
        if len(self.candidate_ids) < 2:
            raise AuthorityContractError("ConflictSet requires at least two candidates")
        if self.action not in RESOLUTION_ACTIONS:
            raise AuthorityContractError(f"Unsupported conflict action: {self.action}")
        object.__setattr__(self, "reason_codes", _unique_strings(self.reason_codes, "conflict.reason_codes"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "kind": self.kind,
            "candidate_ids": list(self.candidate_ids),
            "action": self.action,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class ExplanationEntry:
    """Privacy-safe audit entry for one deterministic policy decision."""

    subject_ids: tuple[str, ...]
    code: str
    action: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_ids", _unique_strings(self.subject_ids, "ledger.subject_ids"))
        _string(self.code, "ledger.code")
        if self.action not in RESOLUTION_ACTIONS:
            raise AuthorityContractError(f"Unsupported ledger action: {self.action}")

    def to_dict(self) -> dict[str, Any]:
        return {"subject_ids": list(self.subject_ids), "code": self.code, "action": self.action}


@dataclass(frozen=True)
class ResolutionResult:
    """The read-only Phase 18 result contract."""

    status: str
    policy_version: str
    input_revisions: Mapping[str, Any]
    candidates: tuple[ResolutionCandidate, ...] = ()
    conflict_sets: tuple[ConflictSet, ...] = ()
    ledger: tuple[ExplanationEntry, ...] = ()
    degraded_reasons: tuple[str, ...] = ()
    error: Optional[str] = None
    telemetry: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in AUTHORITY_STATUSES:
            raise AuthorityContractError(f"Unsupported authority status: {self.status}")
        _string(self.policy_version, "policy_version")
        if not isinstance(self.input_revisions, Mapping):
            raise AuthorityContractError("input_revisions must be a mapping")
        candidate_ids = tuple(candidate.candidate_id for candidate in self.candidates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise AuthorityContractError("Resolution candidates must be deduplicated")
        object.__setattr__(self, "degraded_reasons", _unique_strings(self.degraded_reasons, "degraded_reasons"))
        if self.error is not None:
            _string(self.error, "error")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": AUTHORITY_SCHEMA_VERSION,
            "status": self.status,
            "policy_version": self.policy_version,
            "input_revisions": dict(self.input_revisions),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "conflict_sets": [conflict.to_dict() for conflict in self.conflict_sets],
            "ledger": [entry.to_dict() for entry in self.ledger],
            "degraded_reasons": list(self.degraded_reasons),
            "error": self.error,
            "telemetry": dict(self.telemetry),
        }
