"""Strict, explainable contracts for Phase 19 context compilation.

The compiler is intentionally downstream-only: it receives a Phase 16 task and
a Phase 18 resolution result, rehydrates only their canonical references, and
never performs retrieval, authority resolution, or canonical writes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


COMPILER_SCHEMA_VERSION = 1
COMPILER_VERSION = "context-compiler-v2"
COMPILATION_STATUSES = frozenset(
    {
        "SUCCESS",
        "DEGRADED",
        "EMPTY",
        "INSUFFICIENT_BUDGET",
        "STALE_INPUT",
        "INVALID_INPUT",
        "SCOPE_ERROR",
        "FAILED",
    }
)
COMPILER_MODES = frozenset({"OFF", "SHADOW"})
ESTIMATION_MODES = frozenset({"EXACT", "PROVIDER_ESTIMATE", "CONSERVATIVE_ESTIMATE"})
COMPRESSION_MODES = frozenset({"FULL", "STRUCTURED", "EXTRACTIVE", "METADATA_ONLY", "OMIT"})
CONTEXT_ROLES = frozenset(
    {
        "TASK",
        "CURRENT_STATE",
        "DECISION",
        "REQUIREMENT",
        "CONSTRAINT",
        "PREFERENCE",
        "LESSON",
        "IMPLEMENTATION_FACT",
        "IMPLEMENTATION_GAP",
        "OPEN_LOOP",
        "CONFLICT",
        "HISTORICAL_CONTEXT",
        "SUPPORTING_EVIDENCE",
    }
)
PRIORITY_TIERS = frozenset({0, 1, 2, 3, 4, 5})
SELECTION_REASONS = frozenset(
    {
        "task_identity",
        "mandatory_safety_constraint",
        "mandatory_requirement",
        "mandatory_blocking_issue",
        "critical_authoritative_context",
        "profile_relevant_context",
        "supporting_context",
        "optional_context",
    }
)
OMISSION_REASONS = frozenset(
    {
        "budget_exhausted",
        "profile_budget_exhausted",
        "profile_item_limit",
        "mandatory_overflow",
        "redundant_exact_duplicate",
        "historical_not_requested",
        "ineligible_lifecycle",
        "sensitive_content_detected",
        "upstream_invariant_violation",
        "invalid_reference",
        "compression_not_safe",
        "compiler_off",
    }
)


class CompilerContractError(ValueError):
    """A caller supplied an invalid, unsafe or incoherent compilation contract."""


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompilerContractError(f"{field} must be a non-empty string")
    return value.strip()


def _unique(values: tuple[str, ...] | list[str], field: str) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        raise CompilerContractError(f"{field} must be a sequence")
    normalized = tuple(_string(value, field) for value in values)
    if len(normalized) != len(set(normalized)):
        raise CompilerContractError(f"{field} must not contain duplicates")
    return tuple(sorted(normalized))


@dataclass(frozen=True)
class BudgetContract:
    """Caller-owned maximum allocation, never a target fill level."""

    max_context_tokens: int
    minimum_headroom_tokens: int = 64
    hard_byte_limit: int = 24_000
    estimation_mode: str = "CONSERVATIVE_ESTIMATE"
    mandatory_overflow_policy: str = "FAIL_VISIBLE"
    allow_optional_omission: bool = True

    def __post_init__(self) -> None:
        for field, value in (
            ("max_context_tokens", self.max_context_tokens),
            ("minimum_headroom_tokens", self.minimum_headroom_tokens),
            ("hard_byte_limit", self.hard_byte_limit),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CompilerContractError(f"budget.{field} must be a non-negative integer")
        if self.max_context_tokens <= 0:
            raise CompilerContractError("budget.max_context_tokens must be positive")
        if self.minimum_headroom_tokens >= self.max_context_tokens:
            raise CompilerContractError("budget.minimum_headroom_tokens must be below max_context_tokens")
        if self.hard_byte_limit <= 0:
            raise CompilerContractError("budget.hard_byte_limit must be positive")
        if self.estimation_mode not in ESTIMATION_MODES:
            raise CompilerContractError(f"Unsupported estimation mode: {self.estimation_mode}")
        if self.mandatory_overflow_policy != "FAIL_VISIBLE":
            raise CompilerContractError("Only FAIL_VISIBLE mandatory overflow is supported")
        if not isinstance(self.allow_optional_omission, bool):
            raise CompilerContractError("budget.allow_optional_omission must be boolean")

    @property
    def usable_tokens(self) -> int:
        return self.max_context_tokens - self.minimum_headroom_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_context_tokens": self.max_context_tokens,
            "minimum_headroom_tokens": self.minimum_headroom_tokens,
            "usable_tokens": self.usable_tokens,
            "hard_byte_limit": self.hard_byte_limit,
            "estimation_mode": self.estimation_mode,
            "mandatory_overflow_policy": self.mandatory_overflow_policy,
            "allow_optional_omission": self.allow_optional_omission,
        }


@dataclass(frozen=True)
class CompilationOptions:
    """Trusted caller policy; neither task text nor a resolution may elevate it."""

    mode: str = "SHADOW"
    allow_history: bool = False
    cache_enabled: bool = True

    def __post_init__(self) -> None:
        if self.mode not in COMPILER_MODES:
            raise CompilerContractError(f"Unsupported compiler mode: {self.mode}")
        if not isinstance(self.allow_history, bool) or not isinstance(self.cache_enabled, bool):
            raise CompilerContractError("compiler options must be boolean where declared")


@dataclass(frozen=True)
class CompilationRequest:
    """Immutable request boundary for one V2 compilation."""

    task_state: Any
    resolution_result: Any
    budget: BudgetContract
    compiler_profile: Optional[str] = None

    def __post_init__(self) -> None:
        if self.task_state is None or self.resolution_result is None:
            raise CompilerContractError("task_state and resolution_result are required")
        if self.compiler_profile is not None:
            _string(self.compiler_profile, "compiler_profile")


@dataclass(frozen=True)
class TokenEstimate:
    count: int
    mode: str
    adapter: str
    version: str
    byte_count: int

    def __post_init__(self) -> None:
        if isinstance(self.count, bool) or not isinstance(self.count, int) or self.count < 0:
            raise CompilerContractError("token estimate count must be a non-negative integer")
        if self.mode not in ESTIMATION_MODES:
            raise CompilerContractError(f"Unsupported token estimate mode: {self.mode}")
        _string(self.adapter, "token estimator adapter")
        _string(self.version, "token estimator version")
        if isinstance(self.byte_count, bool) or not isinstance(self.byte_count, int) or self.byte_count < 0:
            raise CompilerContractError("token estimate byte_count must be a non-negative integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "mode": self.mode,
            "adapter": self.adapter,
            "version": self.version,
            "byte_count": self.byte_count,
        }


@dataclass(frozen=True)
class UtilityProfile:
    """Explainable classification, deliberately not a hidden scalar score."""

    candidate_id: str
    role: str
    tier: int
    mandatory: bool
    task_fit: str
    epistemic_status: str
    specificity: str
    redundancy_group: Optional[str]
    estimated_cost: TokenEstimate

    def __post_init__(self) -> None:
        _string(self.candidate_id, "utility.candidate_id")
        if self.role not in CONTEXT_ROLES:
            raise CompilerContractError(f"Unsupported context role: {self.role}")
        if self.tier not in PRIORITY_TIERS:
            raise CompilerContractError(f"Unsupported priority tier: {self.tier}")
        if not isinstance(self.mandatory, bool):
            raise CompilerContractError("utility.mandatory must be boolean")
        _string(self.task_fit, "utility.task_fit")
        _string(self.epistemic_status, "utility.epistemic_status")
        _string(self.specificity, "utility.specificity")
        if self.redundancy_group is not None:
            _string(self.redundancy_group, "utility.redundancy_group")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "role": self.role,
            "tier": self.tier,
            "mandatory": self.mandatory,
            "task_fit": self.task_fit,
            "epistemic_status": self.epistemic_status,
            "specificity": self.specificity,
            "redundancy_group": self.redundancy_group,
            "estimated_cost": self.estimated_cost.to_dict(),
        }


@dataclass(frozen=True)
class ContextItem:
    """One selected model-facing entry with its canonical provenance."""

    candidate_id: str
    source_type: str
    project_id: Optional[str]
    canonical_ref: Mapping[str, Any]
    role: str
    tier: int
    epistemic_status: str
    compression_mode: str
    selection_reason: str
    rendered_text: str
    token_estimate: TokenEstimate

    def __post_init__(self) -> None:
        _string(self.candidate_id, "context_item.candidate_id")
        _string(self.source_type, "context_item.source_type")
        if self.project_id is not None:
            _string(self.project_id, "context_item.project_id")
        if not isinstance(self.canonical_ref, Mapping) or not self.canonical_ref:
            raise CompilerContractError("context_item.canonical_ref is required")
        if self.role not in CONTEXT_ROLES or self.tier not in PRIORITY_TIERS:
            raise CompilerContractError("context item role or tier is invalid")
        _string(self.epistemic_status, "context_item.epistemic_status")
        if self.compression_mode not in COMPRESSION_MODES - {"OMIT"}:
            raise CompilerContractError("selected context item cannot use OMIT")
        if self.selection_reason not in SELECTION_REASONS:
            raise CompilerContractError("context item selection reason is invalid")
        _string(self.rendered_text, "context_item.rendered_text")

    def manifest_dict(self) -> dict[str, Any]:
        """A content-free representation suitable for ledgers and telemetry."""
        return {
            "candidate_id": self.candidate_id,
            "source_type": self.source_type,
            "project_id": self.project_id,
            "canonical_ref": dict(sorted(self.canonical_ref.items())),
            "role": self.role,
            "tier": self.tier,
            "epistemic_status": self.epistemic_status,
            "compression_mode": self.compression_mode,
            "selection_reason": self.selection_reason,
            "token_estimate": self.token_estimate.to_dict(),
        }


@dataclass(frozen=True)
class OmittedItem:
    candidate_id: str
    reason: str
    role: Optional[str] = None
    tier: Optional[int] = None

    def __post_init__(self) -> None:
        _string(self.candidate_id, "omission.candidate_id")
        if self.reason not in OMISSION_REASONS:
            raise CompilerContractError(f"Unsupported omission reason: {self.reason}")
        if self.role is not None and self.role not in CONTEXT_ROLES:
            raise CompilerContractError("omission role is invalid")
        if self.tier is not None and self.tier not in PRIORITY_TIERS:
            raise CompilerContractError("omission tier is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {"candidate_id": self.candidate_id, "reason": self.reason, "role": self.role, "tier": self.tier}


@dataclass(frozen=True)
class ContextSection:
    name: str
    item_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _string(self.name, "section.name")
        object.__setattr__(self, "item_ids", _unique(self.item_ids, "section.item_ids"))

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "item_ids": list(self.item_ids)}


@dataclass(frozen=True)
class ContextBundle:
    """In-memory compiled context plus a content-free machine manifest."""

    status: str
    compilation_id: str
    task_id: Optional[str]
    resolution_id: Optional[str]
    input_revisions: Mapping[str, Any]
    compiler_version: str
    compiler_profile: str
    budget: Mapping[str, Any]
    selected: tuple[ContextItem, ...] = ()
    omitted: tuple[OmittedItem, ...] = ()
    sections: tuple[ContextSection, ...] = ()
    warnings: tuple[str, ...] = ()
    rendered_context: str = ""
    error: Optional[str] = None
    telemetry: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in COMPILATION_STATUSES:
            raise CompilerContractError(f"Unsupported compilation status: {self.status}")
        _string(self.compilation_id, "compilation_id")
        _string(self.compiler_version, "compiler_version")
        _string(self.compiler_profile, "compiler_profile")
        if self.task_id is not None:
            _string(self.task_id, "bundle.task_id")
        if self.resolution_id is not None:
            _string(self.resolution_id, "bundle.resolution_id")
        if not isinstance(self.input_revisions, Mapping) or not isinstance(self.budget, Mapping):
            raise CompilerContractError("bundle revisions and budget must be mappings")
        ids = tuple(item.candidate_id for item in self.selected)
        if len(ids) != len(set(ids)):
            raise CompilerContractError("selected context items must be deduplicated")
        omitted = tuple(item.candidate_id for item in self.omitted)
        if len(omitted) != len(set(omitted)) or set(ids) & set(omitted):
            raise CompilerContractError("selection and omission ledgers must be disjoint")
        object.__setattr__(self, "warnings", _unique(self.warnings, "bundle.warnings"))
        if self.error is not None:
            _string(self.error, "bundle.error")

    def manifest_dict(self) -> dict[str, Any]:
        """Content-free audit output; safe to persist or include in telemetry."""
        return {
            "schema_version": COMPILER_SCHEMA_VERSION,
            "status": self.status,
            "compilation_id": self.compilation_id,
            "task_id": self.task_id,
            "resolution_id": self.resolution_id,
            "input_revisions": dict(self.input_revisions),
            "compiler_version": self.compiler_version,
            "compiler_profile": self.compiler_profile,
            "budget": dict(self.budget),
            "selected": [item.manifest_dict() for item in self.selected],
            "omitted": [item.to_dict() for item in self.omitted],
            "sections": [section.to_dict() for section in self.sections],
            "warnings": list(self.warnings),
            "error": self.error,
            "telemetry": dict(self.telemetry),
        }

    def to_dict(self) -> dict[str, Any]:
        """Explicit model-facing output. Only this form carries selected text."""
        payload = self.manifest_dict()
        payload["selected"] = [
            {**item.manifest_dict(), "rendered_text": item.rendered_text} for item in self.selected
        ]
        payload["rendered_context"] = self.rendered_context
        return payload
