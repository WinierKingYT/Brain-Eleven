"""Proposal-only semantic extraction primitives for IG-03.

This module deliberately stops at a validated proposition.  Providers receive
only prefiltered evidence and can return structured proposals, but the module
does not import or expose MemoryStore, StateStore or lifecycle writers.  A
caller must perform a separate, trusted authority decision before any
canonical effect is possible.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
import hashlib
import math
import re
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence

from brain_eleven._legacy import load_legacy_module


SEMANTIC_SCHEMA_VERSION = "ig01-a-proposition-v1"
SEMANTIC_EXTRACTOR_VERSION = "ig03-semantic-proposal-v1"

_ALLOWED_FIELDS = frozenset(
    {
        "candidate_id",
        "project_id",
        "claim_type",
        "subject",
        "predicate",
        "value",
        "commitment",
        "temporal_scope",
        "source_role",
        "evidence_refs",
        "confidence_components",
        "correction_clues",
        "target_clues",
        "schema_version",
    }
)
_ROLES = frozenset({"user", "assistant", "tool", "system", "unknown"})
_COMMITMENTS = frozenset(
    {
        "committed",
        "proposed",
        "hypothetical",
        "question",
        "negated",
        "quoted",
        "observed",
        "uncertain",
        "explicit",
        "implicit",
        "none",
        "no_commitment",
    }
)
_NON_COMMITMENTS = frozenset(
    {"proposed", "hypothetical", "question", "negated", "quoted", "uncertain", "none", "no_commitment"}
)
_RESERVED_NESTED_KEYS = frozenset(
    {
        "canonical_commit",
        "write_memory",
        "write_state",
        "lifecycle_operation",
        "memory_store",
        "state_store",
        "prompt",
        "transcript",
        "raw_prompt",
        "raw_transcript",
        "content",
        "text",
        "token",
        "tokens",
        "secret",
        "password",
        "credential",
        "api_key",
    }
)
_METADATA_FIELDS = frozenset(
    {"requested_schema_version", "project_bound", "provider_revision", "availability_code"}
)
_REVIEW_FIELDS = frozenset({"case_hash", "reason_code"})
_CASE_HASH = re.compile(r"sha256:[0-9a-f]{64}")
_REASON_CODE = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_QUESTION = re.compile(r"\?|\b(?:should we|could we|shall we|what if|kullansak|yapalım mı|geçelim mi)\b", re.I)
_HYPOTHETICAL = re.compile(r"\b(?:maybe|perhaps|might|could|we could|we might|consider|belki|olabilir|kullanabiliriz)\b", re.I)
_QUOTE = re.compile(r"(?:^|\s)[\"'“‘].*[\"'”’](?:$|\s)|\b(?:quoted|quote|alıntı|dokümanda)\b", re.I | re.S)


class SemanticStatus(str, Enum):
    MEASURED = "MEASURED"
    FILTERED = "FILTERED"
    SEMANTIC_UNAVAILABLE = "SEMANTIC_UNAVAILABLE"
    INVALID_OUTPUT = "INVALID_OUTPUT"


class PropositionValidationError(ValueError):
    """Raised when a provider result cannot be represented safely."""


@dataclass(frozen=True)
class PrefilterResult:
    """Content-free decision made before a provider sees evidence."""

    allowed: bool
    reason_code: str = ""
    content_hash: str = ""
    content_length: int = 0
    evidence_flags: tuple[str, ...] = ()

    @property
    def allowed_to_model(self) -> bool:
        """Compatibility spelling used by provider callers."""

        return self.allowed

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SemanticProposition:
    """The IG01-A projection of one model or baseline proposal."""

    candidate_id: str
    project_id: Optional[str]
    claim_type: str
    subject: Optional[str]
    predicate: Optional[str]
    value: Any
    commitment: str
    temporal_scope: Optional[Mapping[str, Any]]
    source_role: str
    evidence_refs: tuple[str, ...]
    confidence_components: Mapping[str, float]
    correction_clues: Optional[Mapping[str, Any]]
    target_clues: Optional[Mapping[str, Any]]
    schema_version: str = SEMANTIC_SCHEMA_VERSION

    @property
    def confidence(self) -> Optional[float]:
        """Return the mean component confidence when components are present."""

        if not self.confidence_components:
            return None
        return round(sum(self.confidence_components.values()) / len(self.confidence_components), 6)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_refs"] = list(self.evidence_refs)
        payload["confidence_components"] = dict(self.confidence_components)
        return payload

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "SemanticProposition":
        return build_proposition(payload)


@dataclass(frozen=True)
class ValidationResult:
    """Deterministic validation outcome; safe proposals may require review."""

    valid: bool
    canonical_eligible: bool
    review_required: bool
    reason_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderResult:
    """Content-free provider outcome and validated proposal collection."""

    status: str
    provider_id: str
    model: str
    propositions: tuple[SemanticProposition, ...] = ()
    review_records: tuple[Mapping[str, Any], ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    error_code: Optional[str] = None
    elapsed_ms: Optional[float] = None
    schema_version: str = SEMANTIC_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status not in {item.value for item in SemanticStatus}:
            raise ValueError("unknown semantic provider status")
        if not isinstance(self.provider_id, str) or not self.provider_id.strip() or not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("provider_id and model are required")
        if self.schema_version != SEMANTIC_SCHEMA_VERSION:
            raise ValueError("unsupported provider schema_version")
        if self.error_code is not None and (not isinstance(self.error_code, str) or not self.error_code.strip()):
            raise ValueError("error_code must be a non-empty string or null")
        if self.elapsed_ms is not None and (isinstance(self.elapsed_ms, bool) or not isinstance(self.elapsed_ms, (int, float)) or not math.isfinite(float(self.elapsed_ms)) or self.elapsed_ms < 0):
            raise ValueError("elapsed_ms must be finite and non-negative")
        for record in self.review_records:
            if not isinstance(record, Mapping):
                raise ValueError("review records must be mappings")
            if set(record) - _REVIEW_FIELDS:
                raise ValueError("review records contain unknown fields")
            if not isinstance(record.get("case_hash"), str) or not _CASE_HASH.fullmatch(record["case_hash"]):
                raise ValueError("review records require a content hash")
            if not isinstance(record.get("reason_code"), str) or not _REASON_CODE.fullmatch(record["reason_code"]):
                raise ValueError("review records require a bounded reason code")
            _check_nested(record, field_name="review_record")
        if not isinstance(self.metadata, Mapping):
            raise ValueError("provider metadata must be a mapping")
        if set(self.metadata) - _METADATA_FIELDS:
            raise ValueError("provider metadata contains unknown fields")
        for key, value in self.metadata.items():
            if key in {"project_bound"}:
                if not isinstance(value, bool):
                    raise ValueError("metadata.project_bound must be boolean")
            elif not isinstance(value, str) or not value.strip():
                raise ValueError(f"metadata.{key} must be a non-empty string")
        _check_nested(self.metadata, field_name="metadata")
        if any(not isinstance(item, SemanticProposition) for item in self.propositions):
            raise ValueError("provider propositions must be SemanticProposition objects")
        identities = [item.candidate_id for item in self.propositions]
        if len(identities) != len(set(identities)):
            raise ValueError("provider propositions must not contain duplicate candidate IDs")
        for item in self.propositions:
            try:
                build_proposition(item.to_dict())
            except PropositionValidationError as error:
                raise ValueError("provider result contains an invalid proposition") from error

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "provider_id": self.provider_id,
            "model": self.model,
            "propositions": [item.to_dict() for item in self.propositions],
            "review_records": [dict(item) for item in self.review_records],
            "metadata": dict(self.metadata),
            "error_code": self.error_code,
            "elapsed_ms": self.elapsed_ms,
            "schema_version": self.schema_version,
        }


def _message_fields(message: Any) -> tuple[str, str, Optional[str], str, Any]:
    record = getattr(message, "record", message)
    content = getattr(message, "content", None)
    if content is None and isinstance(message, Mapping):
        content = message.get("content", "")
    role = getattr(record, "role", None)
    if role is None and isinstance(record, Mapping):
        role = record.get("role", "unknown")
    project_id = getattr(record, "project_id", None)
    if project_id is None and isinstance(record, Mapping):
        project_id = record.get("project_id")
    evidence_id = getattr(record, "evidence_id", None)
    if evidence_id is None and isinstance(record, Mapping):
        evidence_id = record.get("evidence_id")
    occurred_at = getattr(record, "occurred_at", None)
    if occurred_at is None and isinstance(record, Mapping):
        occurred_at = record.get("occurred_at")
    if not isinstance(content, str):
        raise PropositionValidationError("message content must be text")
    return content, str(role or "unknown").lower(), project_id, str(evidence_id or ""), occurred_at


def _hash_content(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _temporal_scope(occurred_at: Any) -> Optional[dict[str, Any]]:
    if occurred_at is None:
        return None
    if hasattr(occurred_at, "value") and hasattr(occurred_at, "precision"):
        return {"start": str(occurred_at.value), "precision": str(occurred_at.precision)}
    if isinstance(occurred_at, Mapping):
        if "start" in occurred_at or "end" in occurred_at:
            return dict(occurred_at)
        if "value" in occurred_at:
            return {"start": occurred_at["value"], "precision": occurred_at.get("precision", "unknown")}
    raise PropositionValidationError("occurred_at has an unsupported shape")


def _check_nested(value: Any, *, depth: int = 0, field_name: str = "value") -> None:
    """Reject nested authority/content keys before a proposal is accepted."""

    if depth > 3:
        raise PropositionValidationError(f"{field_name} exceeds maximum nesting depth")
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str) or not key.strip():
                raise PropositionValidationError(f"{field_name} keys must be non-empty strings")
            if key.strip().lower() in _RESERVED_NESTED_KEYS:
                raise PropositionValidationError(f"reserved nested field: {key}")
            _check_nested(child, depth=depth + 1, field_name=f"{field_name}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _check_nested(child, depth=depth + 1, field_name=f"{field_name}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise PropositionValidationError(f"{field_name} contains a non-finite number")
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise PropositionValidationError(f"{field_name} contains an unsupported value")


class DeterministicSafetyPrefilter:
    """Screen secrets, transcript-like payloads and quoted material pre-model."""

    def __init__(self) -> None:
        self._capture_safety = load_legacy_module("capture_safety", "capture_safety.py")

    def evaluate(self, content: str) -> PrefilterResult:
        if not isinstance(content, str):
            raise PropositionValidationError("prefilter content must be text")
        result = self._capture_safety.evaluate_capture(content)
        reason = result.reason
        flags: list[str] = []
        if _QUESTION.search(content):
            flags.append("question")
        if _HYPOTHETICAL.search(content):
            flags.append("hypothetical")
        if _QUOTE.search(content):
            flags.append("quoted")
        if result.accepted and "quoted" in flags:
            reason = "quoted_material"
        return PrefilterResult(
            allowed=not reason,
            reason_code=reason,
            content_hash=_hash_content(content),
            content_length=len(content),
            evidence_flags=tuple(flags),
        )


def _string_or_none(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise PropositionValidationError(f"{field_name} must be a non-empty string or null")
    return value.strip()


def _mapping_or_none(value: Any, field_name: str) -> Optional[Mapping[str, Any]]:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise PropositionValidationError(f"{field_name} must be an object or null")
    return dict(value)


def build_proposition(payload: Mapping[str, Any]) -> SemanticProposition:
    """Strictly map provider JSON to the frozen IG01-A proposition schema."""

    if not isinstance(payload, Mapping):
        raise PropositionValidationError("proposition must be an object")
    unknown = set(payload) - _ALLOWED_FIELDS
    if unknown:
        raise PropositionValidationError("unknown proposition fields: " + ",".join(sorted(map(str, unknown))))
    required = _ALLOWED_FIELDS - {"subject", "predicate", "value", "temporal_scope", "correction_clues", "target_clues"}
    missing = sorted(field_name for field_name in required if field_name not in payload)
    if missing:
        raise PropositionValidationError("missing proposition fields: " + ",".join(missing))
    candidate_id = _string_or_none(payload.get("candidate_id"), "candidate_id")
    claim_type = _string_or_none(payload.get("claim_type"), "claim_type")
    if candidate_id is None or claim_type is None:
        raise PropositionValidationError("candidate_id and claim_type are required")
    project_id = _string_or_none(payload.get("project_id"), "project_id")
    role = _string_or_none(payload.get("source_role"), "source_role")
    if role is None or role.lower() not in _ROLES:
        raise PropositionValidationError("source_role is unsupported")
    commitment = _string_or_none(payload.get("commitment"), "commitment")
    if commitment is None or commitment.lower() not in _COMMITMENTS:
        raise PropositionValidationError("commitment is unsupported")
    refs = payload.get("evidence_refs")
    if isinstance(refs, (str, bytes)) or not isinstance(refs, Sequence) or not refs:
        raise PropositionValidationError("evidence_refs must be a non-empty list")
    evidence_refs_list: list[str] = []
    for item in refs:
        reference = _string_or_none(item, "evidence_refs item")
        if reference is None:
            raise PropositionValidationError("evidence_refs items must be non-empty strings")
        evidence_refs_list.append(reference)
    evidence_refs = tuple(evidence_refs_list)
    if len(evidence_refs) != len(set(evidence_refs)):
        raise PropositionValidationError("evidence_refs must not contain duplicates")
    components = payload.get("confidence_components")
    if not isinstance(components, Mapping) or not components:
        raise PropositionValidationError("confidence_components must be a non-empty object")
    normalized_components: dict[str, float] = {}
    for key, value in components.items():
        if not isinstance(key, str) or not key.strip():
            raise PropositionValidationError("confidence component names must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise PropositionValidationError("confidence components must be finite numbers")
        if not 0 <= float(value) <= 1:
            raise PropositionValidationError("confidence components must be in [0, 1]")
        normalized_components[key.strip()] = float(value)
    schema_version = _string_or_none(payload.get("schema_version"), "schema_version")
    if schema_version != SEMANTIC_SCHEMA_VERSION:
        raise PropositionValidationError("unsupported proposition schema_version")
    temporal = _mapping_or_none(payload.get("temporal_scope"), "temporal_scope")
    if temporal is not None:
        unknown_temporal = set(temporal) - {"start", "end", "precision"}
        if unknown_temporal:
            raise PropositionValidationError("unknown temporal fields: " + ",".join(sorted(map(str, unknown_temporal))))
        for key in ("start", "end"):
            if key in temporal and not isinstance(temporal[key], str):
                raise PropositionValidationError("temporal boundaries must be strings")
        if temporal.get("start") and temporal.get("end"):
            try:
                start = datetime.fromisoformat(str(temporal["start"]).replace("Z", "+00:00"))
                end = datetime.fromisoformat(str(temporal["end"]).replace("Z", "+00:00"))
            except ValueError as error:
                raise PropositionValidationError("temporal boundaries must be ISO-8601") from error
            if start.tzinfo is None or end.tzinfo is None or end < start:
                raise PropositionValidationError("temporal scope is inconsistent")
    correction = _mapping_or_none(payload.get("correction_clues"), "correction_clues")
    if correction is not None:
        unknown_correction = set(correction) - {"explicit", "old_value", "new_value", "claim_key", "reason"}
        if unknown_correction:
            raise PropositionValidationError("unknown correction fields: " + ",".join(sorted(map(str, unknown_correction))))
        if "explicit" in correction and not isinstance(correction["explicit"], bool):
            raise PropositionValidationError("correction.explicit must be boolean")
        for key in {"old_value", "new_value", "claim_key", "reason"} & set(correction):
            if not isinstance(correction[key], str) or not correction[key].strip():
                raise PropositionValidationError(f"correction.{key} must be a non-empty string")
    target = _mapping_or_none(payload.get("target_clues"), "target_clues")
    if target is not None:
        unknown_target = set(target) - {"named_id", "claim_key", "lineage_id", "reference_kind"}
        if unknown_target:
            raise PropositionValidationError("unknown target fields: " + ",".join(sorted(map(str, unknown_target))))
        for key in {"named_id", "claim_key", "lineage_id", "reference_kind"} & set(target):
            if not isinstance(target[key], str) or not target[key].strip():
                raise PropositionValidationError(f"target.{key} must be a non-empty string")
    _check_nested(payload.get("value"), field_name="value")
    _check_nested(temporal, field_name="temporal_scope")
    _check_nested(correction, field_name="correction_clues")
    _check_nested(target, field_name="target_clues")
    return SemanticProposition(
        candidate_id=candidate_id,
        project_id=project_id,
        claim_type=claim_type,
        subject=_string_or_none(payload.get("subject"), "subject"),
        predicate=_string_or_none(payload.get("predicate"), "predicate"),
        value=payload.get("value"),
        commitment=commitment,
        temporal_scope=temporal,
        source_role=role.lower(),
        evidence_refs=evidence_refs,
        confidence_components=normalized_components,
        correction_clues=correction,
        target_clues=target,
        schema_version=schema_version,
    )


def validate_proposition(
    proposition: SemanticProposition | Mapping[str, Any],
    *,
    evidence_flags: Sequence[str] = (),
) -> ValidationResult:
    """Apply deterministic role, commitment and scope gates."""

    try:
        # Re-serialize dataclass instances through the strict builder as well;
        # callers can otherwise construct an unsafe object without validation.
        item = build_proposition(proposition.to_dict() if isinstance(proposition, SemanticProposition) else proposition)
    except PropositionValidationError:
        return ValidationResult(False, False, True, "INVALID_PROPOSITION")
    commitment = item.commitment.lower()
    role = item.source_role.lower()
    flags = {str(flag).strip().lower() for flag in evidence_flags}
    if role in {"assistant", "tool", "system"} and commitment in {"committed", "explicit", "implicit"}:
        return ValidationResult(False, False, True, "NON_USER_COMMITMENT")
    if role == "unknown" and commitment in {"committed", "explicit", "implicit"}:
        return ValidationResult(False, False, True, "UNKNOWN_SOURCE_ROLE")
    if commitment in _NON_COMMITMENTS and commitment in {"question", "hypothetical"}:
        return ValidationResult(True, False, True, "NON_COMMITMENT")
    if "question" in flags and commitment in {"committed", "explicit", "implicit"}:
        return ValidationResult(False, False, True, "QUESTION_COMMITMENT")
    if "hypothetical" in flags and commitment in {"committed", "explicit", "implicit"}:
        return ValidationResult(False, False, True, "HYPOTHETICAL_COMMITMENT")
    if "quoted" in flags and commitment in {"committed", "explicit", "implicit"}:
        return ValidationResult(False, False, True, "QUOTED_COMMITMENT")
    if _QUESTION.search(str(item.value or "")) and commitment in {"committed", "explicit", "implicit"}:
        return ValidationResult(False, False, True, "QUESTION_COMMITMENT")
    if _HYPOTHETICAL.search(str(item.value or "")) and commitment in {"committed", "explicit", "implicit"}:
        return ValidationResult(False, False, True, "HYPOTHETICAL_COMMITMENT")
    if _QUOTE.search(str(item.value or "")) and commitment in {"committed", "explicit", "implicit"}:
        return ValidationResult(False, False, True, "QUOTED_COMMITMENT")
    if item.project_id is None:
        return ValidationResult(True, False, True, "SCOPE_UNRESOLVED")
    canonical = role == "user" and commitment in {"committed", "explicit", "implicit"}
    return ValidationResult(True, canonical, not canonical, "VALIDATED" if canonical else "REVIEW_REQUIRED")


def require_valid_proposition(
    proposition: SemanticProposition | Mapping[str, Any],
    *,
    evidence_flags: Sequence[str] = (),
) -> SemanticProposition:
    """Return a parsed proposition or raise on any unsafe provider output."""

    item = build_proposition(proposition.to_dict() if isinstance(proposition, SemanticProposition) else proposition)
    result = validate_proposition(item, evidence_flags=evidence_flags)
    if not result.valid:
        raise PropositionValidationError(result.reason_code)
    return item


class SemanticProvider(Protocol):
    provider_id: str
    model: str

    def extract(
        self,
        message: Any,
        *,
        project_id: Optional[str] = None,
        schema_version: str = SEMANTIC_SCHEMA_VERSION,
    ) -> ProviderResult:
        ...


def _record_review(case: str, reason: str) -> dict[str, str]:
    return {"case_hash": _hash_content(case), "reason_code": reason}


class UnavailableProvider:
    """Explicit provider slot for an unavailable local or stronger model."""

    def __init__(self, provider_id: str, model: str, reason: str = "provider_not_configured") -> None:
        self.provider_id = provider_id
        self.model = model
        self.reason = reason
        self.provider_revision = "unavailable-provider-v1"

    def extract(
        self,
        message: Any,
        *,
        project_id: Optional[str] = None,
        schema_version: str = SEMANTIC_SCHEMA_VERSION,
    ) -> ProviderResult:
        content, _, _, _, _ = _message_fields(message)
        return ProviderResult(
            status=SemanticStatus.SEMANTIC_UNAVAILABLE.value,
            provider_id=self.provider_id,
            model=self.model,
            review_records=(_record_review(content, self.reason),),
            metadata={
                "requested_schema_version": schema_version,
                "project_bound": project_id is not None,
                "provider_revision": self.provider_revision,
                "availability_code": self.reason,
            },
            error_code=self.reason,
        )


class CallableSemanticProvider:
    """Adapter for a configured model callable; output remains proposal-only."""

    def __init__(
        self,
        provider_id: str,
        model: str,
        call: Callable[[str], Any],
        provider_revision: str = "callable-adapter-v1",
    ) -> None:
        self.provider_id = provider_id
        self.model = model
        self._call = call
        self.provider_revision = provider_revision
        self.prefilter = DeterministicSafetyPrefilter()

    def extract(
        self,
        message: Any,
        *,
        project_id: Optional[str] = None,
        schema_version: str = SEMANTIC_SCHEMA_VERSION,
    ) -> ProviderResult:
        content, role, message_project_id, evidence_id, occurred_at = _message_fields(message)
        trusted_project_id = project_id if project_id is not None else message_project_id
        if schema_version != SEMANTIC_SCHEMA_VERSION:
            return ProviderResult(
                status=SemanticStatus.INVALID_OUTPUT.value,
                provider_id=self.provider_id,
                model=self.model,
                error_code="UNSUPPORTED_SCHEMA_VERSION",
                review_records=(_record_review(content, "UNSUPPORTED_SCHEMA_VERSION"),),
                metadata={
                    "requested_schema_version": schema_version,
                    "project_bound": trusted_project_id is not None,
                    "provider_revision": self.provider_revision,
                    "availability_code": "invalid_schema",
                },
            )
        prefilter = self.prefilter.evaluate(content)
        if not prefilter.allowed:
            return ProviderResult(
                status=SemanticStatus.FILTERED.value,
                provider_id=self.provider_id,
                model=self.model,
                review_records=(_record_review(content, prefilter.reason_code),),
                error_code=prefilter.reason_code,
                metadata={
                    "requested_schema_version": schema_version,
                    "project_bound": trusted_project_id is not None,
                    "provider_revision": self.provider_revision,
                    "availability_code": "filtered",
                },
            )
        try:
            raw = self._call(content)
            rows = raw.get("propositions", raw.get("candidates", [])) if isinstance(raw, Mapping) else raw
            if isinstance(rows, Mapping) or isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
                raise PropositionValidationError("provider propositions must be a list")
            propositions: list[SemanticProposition] = []
            reviews: list[Mapping[str, Any]] = []
            for row in rows:
                if not isinstance(row, Mapping):
                    raise PropositionValidationError("provider proposition must be an object")
                enriched = dict(row)
                # These fields are evidence authority, never model authority.
                enriched["project_id"] = trusted_project_id
                enriched["source_role"] = role
                enriched["evidence_refs"] = [evidence_id or prefilter.content_hash]
                enriched.setdefault("temporal_scope", None)
                enriched.setdefault("correction_clues", None)
                enriched.setdefault("target_clues", None)
                enriched["schema_version"] = schema_version
                proposition = build_proposition(enriched)
                validation = validate_proposition(proposition, evidence_flags=prefilter.evidence_flags)
                if validation.valid:
                    propositions.append(proposition)
                else:
                    reviews.append(_record_review(content, validation.reason_code))
            return ProviderResult(
                status=SemanticStatus.MEASURED.value,
                provider_id=self.provider_id,
                model=self.model,
                propositions=tuple(propositions),
                review_records=tuple(reviews),
                metadata={
                    "requested_schema_version": schema_version,
                    "project_bound": trusted_project_id is not None,
                    "provider_revision": self.provider_revision,
                    "availability_code": "available",
                },
            )
        except (PropositionValidationError, TypeError, ValueError, KeyError) as error:
            return ProviderResult(
                status=SemanticStatus.INVALID_OUTPUT.value,
                provider_id=self.provider_id,
                model=self.model,
                review_records=(_record_review(content, "INVALID_OUTPUT"),),
                error_code=type(error).__name__,
                metadata={
                    "requested_schema_version": schema_version,
                    "project_bound": trusted_project_id is not None,
                    "provider_revision": self.provider_revision,
                    "availability_code": "invalid_output",
                },
            )


class DeterministicRegexProvider:
    """IG-03 control provider derived from the existing deterministic rules."""

    provider_id = "deterministic-regex-baseline"
    model = "scripts.extraction:" + SEMANTIC_EXTRACTOR_VERSION

    def __init__(self) -> None:
        self.prefilter = DeterministicSafetyPrefilter()
        self._extraction = load_legacy_module("extraction", "extraction.py")

    def extract(
        self,
        message: Any,
        *,
        project_id: Optional[str] = None,
        schema_version: str = SEMANTIC_SCHEMA_VERSION,
    ) -> ProviderResult:
        content, role, message_project_id, evidence_id, occurred_at = _message_fields(message)
        trusted_project_id = project_id if project_id is not None else message_project_id
        if schema_version != SEMANTIC_SCHEMA_VERSION:
            return ProviderResult(
                status=SemanticStatus.INVALID_OUTPUT.value,
                provider_id=self.provider_id,
                model=self.model,
                error_code="UNSUPPORTED_SCHEMA_VERSION",
                review_records=(_record_review(content, "UNSUPPORTED_SCHEMA_VERSION"),),
                metadata={
                    "requested_schema_version": schema_version,
                    "project_bound": trusted_project_id is not None,
                    "provider_revision": SEMANTIC_EXTRACTOR_VERSION,
                    "availability_code": "invalid_schema",
                },
            )
        prefilter = self.prefilter.evaluate(content)
        if not prefilter.allowed:
            return ProviderResult(
                status=SemanticStatus.FILTERED.value,
                provider_id=self.provider_id,
                model=self.model,
                review_records=(_record_review(content, prefilter.reason_code),),
                error_code=prefilter.reason_code,
                metadata={
                    "requested_schema_version": schema_version,
                    "project_bound": trusted_project_id is not None,
                    "provider_revision": SEMANTIC_EXTRACTOR_VERSION,
                    "availability_code": "filtered",
                },
            )
        commitment = self._extraction._classify_commitment(content, role).value.lower()
        if commitment == "committed":
            claim_type = self._extraction._memory_type(content)
        elif commitment == "observed":
            claim_type = "observation"
        else:
            claim_type = "observation"
        candidate = SemanticProposition(
            candidate_id="cand_" + hashlib.sha256((evidence_id + content).encode("utf-8")).hexdigest()[:32],
            project_id=trusted_project_id,
            claim_type=claim_type,
            subject=claim_type,
            predicate="asserts",
            value=content,
            commitment=commitment,
            temporal_scope=_temporal_scope(occurred_at),
            source_role=role,
            evidence_refs=(evidence_id or prefilter.content_hash,),
            confidence_components={"deterministic_classification": 1.0},
            correction_clues=None,
            target_clues=None,
            schema_version=schema_version,
        )
        result = validate_proposition(candidate, evidence_flags=prefilter.evidence_flags)
        if not result.valid:
            return ProviderResult(
                status=SemanticStatus.MEASURED.value,
                provider_id=self.provider_id,
                model=self.model,
                review_records=(_record_review(content, result.reason_code),),
                metadata={
                    "requested_schema_version": schema_version,
                    "project_bound": trusted_project_id is not None,
                    "provider_revision": SEMANTIC_EXTRACTOR_VERSION,
                    "availability_code": "available",
                },
            )
        return ProviderResult(
            status=SemanticStatus.MEASURED.value,
            provider_id=self.provider_id,
            model=self.model,
            propositions=(candidate,),
            review_records=(() if result.canonical_eligible else (_record_review(content, result.reason_code),)),
            metadata={
                "requested_schema_version": schema_version,
                "project_bound": trusted_project_id is not None,
                "provider_revision": SEMANTIC_EXTRACTOR_VERSION,
                "availability_code": "available",
            },
        )


def extract_with_provider(provider: SemanticProvider, message: Any, **kwargs: Any) -> ProviderResult:
    """Common entry point used by tests and future benchmark adapters."""

    return provider.extract(message, **kwargs)


__all__ = [
    "SEMANTIC_SCHEMA_VERSION",
    "SEMANTIC_EXTRACTOR_VERSION",
    "SemanticStatus",
    "PropositionValidationError",
    "PrefilterResult",
    "SemanticProposition",
    "ValidationResult",
    "ProviderResult",
    "DeterministicSafetyPrefilter",
    "build_proposition",
    "validate_proposition",
    "require_valid_proposition",
    "SemanticProvider",
    "UnavailableProvider",
    "CallableSemanticProvider",
    "DeterministicRegexProvider",
    "extract_with_provider",
]
