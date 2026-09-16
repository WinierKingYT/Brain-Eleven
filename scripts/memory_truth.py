#!/usr/bin/env python3
"""Metadata-first truth and lifecycle decisions for extracted candidates.

This module is deliberately narrower than semantic contradiction resolution.
It consumes structured candidates, never treats free prose as authority, and
uses the canonical MemoryStore transaction boundary for accepted lifecycle
mutations and explicitly enabled new-memory commits.
"""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from brain_eleven._legacy import load_legacy_module
from brain_eleven.memory import GLOBAL_SCOPE, infer_memory_scope, scoped_fingerprint
from brain_eleven.memory import MemoryStore, MemoryStoreConflict, MemoryStoreCorrupt, no_change
from brain_eleven.projects.registry import ProjectRegistry, ProjectRegistryError


_capture_safety = load_legacy_module("capture_safety", "capture_safety.py")
evaluate_capture = _capture_safety.evaluate_capture


class TruthError(RuntimeError):
    """Base error with a stable machine-readable code."""

    code = "MEMORY_TRUTH_FAILED"


class TruthInputError(TruthError):
    code = "MEMORY_TRUTH_INVALID"


class _TruthReplayMismatch(TruthInputError):
    code = "OPERATION_REPLAY_MISMATCH"


class _TruthProvenanceError(TruthInputError):
    code = "INVALID_PROVENANCE"


class _TruthApprovalError(TruthInputError):
    code = "INVALID_APPROVAL"


class TruthCorruptError(TruthError):
    code = "MEMORY_TRUTH_CORRUPT"


class TruthAction(str, Enum):
    NEW = "NEW"
    DUPLICATE = "DUPLICATE"
    CONFIRM_EXISTING = "CONFIRM_EXISTING"
    SUPERSEDE_EXISTING = "SUPERSEDE_EXISTING"
    RESOLVE_EXISTING = "RESOLVE_EXISTING"
    CONFLICT = "CONFLICT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REJECT = "REJECT"


class TruthStatus(str, Enum):
    SUCCESS = "SUCCESS"
    DEGRADED = "DEGRADED"
    EMPTY = "EMPTY"
    STALE_INPUT = "STALE_INPUT"
    INVALID_INPUT = "INVALID_INPUT"
    SCOPE_ERROR = "SCOPE_ERROR"
    FAILED = "FAILED"


_ALLOWED_STATUS = {"active", "resolved", "superseded"}
_ALLOWED_SCOPE = {GLOBAL_SCOPE, "project"}
_ALLOWED_PROVENANCE_SOURCES = frozenset({"user", "worker", "review", "extraction-v2"})
_LEGACY_REQUEST_FIELDS = (
    "candidate_id",
    "content",
    "memory_type",
    "scope",
    "project_id",
    "project",
    "dedup_fingerprint",
    "claim_key",
    "commitment",
    "confidence",
    "evidence_refs",
    "occurred_at",
    "operation",
    "target_memory_id",
    "successor_memory_id",
    "resolved_by",
    "note",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_memory_id() -> str:
    return "mem_" + uuid.uuid4().hex[:26]


@dataclass(frozen=True)
class TruthCandidate:
    """Structured extraction output accepted by the truth boundary."""

    candidate_id: str
    content: str
    memory_type: str = ""
    scope: str = GLOBAL_SCOPE
    project_id: str = ""
    project: str = ""
    dedup_fingerprint: str = ""
    claim_key: str = ""
    commitment: str = "COMMITTED"
    confidence: float = 0.0
    evidence_refs: tuple[str, ...] = ()
    occurred_at: Optional[str] = None
    operation: str = "NEW"
    target_memory_id: str = ""
    successor_memory_id: str = ""
    resolved_by: str = "extraction-v2"
    note: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TruthCandidate":
        if not isinstance(value, Mapping):
            raise TruthInputError("candidate must be an object")
        refs = value.get("evidence_refs", ())
        if isinstance(refs, str):
            refs = (refs,)
        if not isinstance(refs, (list, tuple)):
            raise TruthInputError("evidence_refs must be a list")
        try:
            confidence = float(value.get("confidence", 0.0))
        except (TypeError, ValueError) as exc:
            raise TruthInputError("confidence must be numeric") from exc
        project_label = str(value.get("project") or "").strip()
        if not project_label:
            project_label = str(value.get("project_label") or "").strip()
        candidate = cls(
            candidate_id=str(value.get("candidate_id") or "").strip(),
            content=str(value.get("content") or "").strip(),
            memory_type=str(value.get("memory_type", value.get("type", "")) or "").strip().lower(),
            scope=str(value.get("scope") or GLOBAL_SCOPE).strip().lower(),
            project_id=str(value.get("project_id") or "").strip(),
            project=project_label,
            dedup_fingerprint=str(value.get("dedup_fingerprint") or "").strip(),
            claim_key=str(value.get("claim_key") or "").strip(),
            commitment=str(value.get("commitment") or "COMMITTED").strip().upper(),
            confidence=confidence,
            evidence_refs=tuple(str(ref).strip() for ref in refs if str(ref).strip()),
            occurred_at=str(value.get("occurred_at") or "").strip() or None,
            operation=str(value.get("operation") or "NEW").strip().upper(),
            target_memory_id=str(value.get("target_memory_id") or "").strip(),
            successor_memory_id=str(value.get("successor_memory_id") or "").strip(),
            resolved_by=str(value.get("resolved_by") or "extraction-v2").strip(),
            note=str(value.get("note") or "").strip(),
        )
        if not candidate.candidate_id or not candidate.content:
            raise TruthInputError("candidate_id and content are required")
        if candidate.scope not in _ALLOWED_SCOPE:
            raise TruthInputError("unsupported candidate scope")
        if candidate.scope == "project" and not candidate.project_id:
            raise TruthInputError("project-scoped candidate requires project_id")
        if not 0.0 <= candidate.confidence <= 1.0:
            raise TruthInputError("confidence must be between zero and one")
        if candidate.operation not in {action.value for action in TruthAction}:
            raise TruthInputError("unsupported truth operation")
        return candidate


@dataclass(frozen=True)
class _CandidateEnvelope:
    """Private mapping metadata kept outside the historical candidate shape."""

    candidate: TruthCandidate
    source: str
    is_approved: bool
    has_source: bool = False
    has_approval: bool = False


def legacy_request_projection(candidate: TruthCandidate) -> dict[str, Any]:
    """Return the exact pre-W-24 request projection in stable field order."""
    return {field_name: getattr(candidate, field_name) for field_name in _LEGACY_REQUEST_FIELDS}


def _normalize_candidate_envelope(
    value: TruthCandidate | Mapping[str, Any],
    *,
    operation_id: Optional[str],
) -> _CandidateEnvelope:
    """Normalize mapping-only provenance without changing ``TruthCandidate``."""
    if isinstance(value, TruthCandidate):
        candidate = value
        mapping: Optional[Mapping[str, Any]] = None
    else:
        if not isinstance(value, Mapping):
            raise TruthInputError("candidate must be an object")
        mapping = value
        candidate = TruthCandidate.from_mapping(value)

    has_source = mapping is not None and "source" in mapping
    if has_source:
        raw_source = mapping.get("source")
        if not isinstance(raw_source, str) or not raw_source.strip():
            raise _TruthProvenanceError("source must be a bounded provenance label")
        source = raw_source.strip().lower()
        if source not in _ALLOWED_PROVENANCE_SOURCES:
            raise _TruthProvenanceError("source must be a bounded provenance label")
    else:
        # Existing worker payloads have no mapping metadata.  Their operation
        # identity is the only compatibility signal available at this layer.
        source = "worker" if operation_id else "user"

    has_approval = mapping is not None and "is_approved" in mapping
    if has_approval:
        raw_approval = mapping.get("is_approved")
        if not isinstance(raw_approval, bool):
            raise _TruthApprovalError("is_approved must be boolean")
        is_approved = raw_approval
    else:
        is_approved = candidate.commitment == "COMMITTED"

    return _CandidateEnvelope(
        candidate=candidate,
        source=source,
        is_approved=is_approved,
        has_source=has_source,
        has_approval=has_approval,
    )


def _capture_rejection_reason(content: str) -> Optional[str]:
    """Map the shared policy's content-free reason to truth compatibility codes."""
    result = evaluate_capture(content)
    if result.accepted:
        return None
    return {
        "potential_secret": "SECRET_CONTENT",
        "payload_too_large": "CAPTURE_TOO_LARGE",
        "too_many_lines": "CAPTURE_TOO_MANY_LINES",
        "transcript_like": "CAPTURE_TRANSCRIPT_LIKE",
    }.get(result.reason, "CAPTURE_SAFETY_REJECTED")


@dataclass(frozen=True)
class TruthDecision:
    candidate_id: str
    action: str
    reason_code: str
    target_memory_id: Optional[str] = None
    successor_memory_id: Optional[str] = None
    source_memory_revision: Optional[int] = None
    produced_memory_revision: Optional[int] = None
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["evidence_refs"] = list(self.evidence_refs)
        return result


@dataclass(frozen=True)
class TruthResult:
    status: str
    source_memory_revision: Optional[int]
    produced_memory_revision: Optional[int]
    decisions: tuple[TruthDecision, ...] = ()
    error_code: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_memory_revision": self.source_memory_revision,
            "produced_memory_revision": self.produced_memory_revision,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "error_code": self.error_code,
        }


def _memory_id(memory: Mapping[str, Any]) -> str:
    return str(memory.get("memory_id") or memory.get("id") or "").strip()


def _memory_scope(memory: Mapping[str, Any]) -> tuple[str, str]:
    try:
        scope, _, project_id = infer_memory_scope(memory)
    except (KeyError, TypeError, ValueError):
        scope = str(memory.get("scope") or GLOBAL_SCOPE)
        project_id = str(memory.get("project_id") or "")
    return scope, project_id


def _same_scope(candidate: TruthCandidate, memory: Mapping[str, Any]) -> bool:
    scope, project_id = _memory_scope(memory)
    return scope == candidate.scope and (scope != "project" or project_id == candidate.project_id)


class MemoryTruthEngine:
    """Evaluate structured candidates and optionally commit safe effects."""

    def __init__(self, vault_path: str | Path):
        self.store = MemoryStore(vault_path)

    @staticmethod
    def _fingerprint(candidate: TruthCandidate) -> str:
        if candidate.dedup_fingerprint:
            return candidate.dedup_fingerprint
        return scoped_fingerprint(candidate.content, candidate.scope, candidate.project_id, candidate.memory_type)

    @staticmethod
    def _find_by_id(memories: Iterable[Mapping[str, Any]], memory_id: str) -> Optional[Mapping[str, Any]]:
        for memory in memories:
            if _memory_id(memory) == memory_id:
                return memory
        return None

    @staticmethod
    def _decision(candidate: TruthCandidate, action: str, reason: str) -> TruthDecision:
        return TruthDecision(
            candidate.candidate_id,
            action,
            reason,
            evidence_refs=candidate.evidence_refs,
        )

    def _preflight(
        self,
        envelopes: Sequence[_CandidateEnvelope],
    ) -> tuple[list[_CandidateEnvelope], list[Optional[TruthDecision]]]:
        """Run safety and project authority checks before loading the store."""
        resolved = list(envelopes)
        decisions: list[Optional[TruthDecision]] = [None] * len(envelopes)
        registry: Optional[ProjectRegistry] = None

        for index, envelope in enumerate(envelopes):
            candidate = envelope.candidate
            reason = _capture_rejection_reason(candidate.content)
            if reason is None and candidate.note:
                reason = _capture_rejection_reason(candidate.note)
            if reason is not None:
                decisions[index] = self._decision(candidate, TruthAction.REJECT.value, reason)
                continue

            if candidate.scope == GLOBAL_SCOPE:
                if candidate.project_id or candidate.project:
                    decisions[index] = self._decision(
                        candidate,
                        TruthAction.REJECT.value,
                        "GLOBAL_PROJECT_METADATA",
                    )
                continue

            if not candidate.project_id:
                decisions[index] = self._decision(
                    candidate,
                    TruthAction.REJECT.value,
                    "SCOPE_UNRESOLVED",
                )
                continue

            if registry is None:
                registry = ProjectRegistry(self.store.vault_path)
            try:
                project = registry.get(candidate.project_id)
                if project is None:
                    decisions[index] = self._decision(
                        candidate,
                        TruthAction.REJECT.value,
                        "PROJECT_UNREGISTERED",
                    )
                    continue
                if project.get("status") == "archived":
                    decisions[index] = self._decision(
                        candidate,
                        TruthAction.REJECT.value,
                        "PROJECT_ARCHIVED",
                    )
                    continue
                if project.get("status") != "active" or not project.get("proactive_capture"):
                    decisions[index] = self._decision(
                        candidate,
                        TruthAction.REJECT.value,
                        "PROJECT_CAPTURE_DISABLED",
                    )
                    continue
                label = project.get("project_label")
                if not isinstance(label, str) or not label.strip():
                    raise ProjectRegistryError("Project registry label is unavailable")
                # The registry owns the display label and opaque ID.  The
                # caller's label is never used to select or widen a project.
                resolved[index] = replace(
                    envelope,
                    candidate=replace(
                        candidate,
                        project_id=str(project["project_id"]),
                        project=label.strip(),
                    ),
                )
            except (ProjectRegistryError, OSError, TypeError, KeyError):
                decisions[index] = self._decision(
                    candidate,
                    TruthAction.REJECT.value,
                    "PROJECT_REGISTRY_UNAVAILABLE",
                )
        return resolved, decisions

    def _validate_candidate(
        self,
        candidate: TruthCandidate,
        envelope: Optional[_CandidateEnvelope] = None,
    ) -> Optional[TruthDecision]:
        envelope = envelope or _CandidateEnvelope(
            candidate=candidate,
            source="user",
            is_approved=candidate.commitment == "COMMITTED",
        )
        reason = _capture_rejection_reason(candidate.content)
        if reason is not None:
            return self._decision(candidate, TruthAction.REJECT.value, reason)
        if candidate.note:
            reason = _capture_rejection_reason(candidate.note)
            if reason is not None:
                return self._decision(candidate, TruthAction.REJECT.value, reason)
        if envelope.has_approval and not envelope.is_approved:
            return self._decision(candidate, TruthAction.REVIEW_REQUIRED.value, "UNAPPROVED_CANDIDATE")
        if candidate.commitment != "COMMITTED":
            return self._decision(candidate, TruthAction.REVIEW_REQUIRED.value, "UNCOMMITTED_CANDIDATE")
        if not envelope.is_approved:
            return self._decision(candidate, TruthAction.REVIEW_REQUIRED.value, "UNAPPROVED_CANDIDATE")
        if candidate.scope == "project" and not candidate.project_id:
            return self._decision(candidate, TruthAction.REJECT.value, "SCOPE_UNRESOLVED")
        if candidate.operation in {TruthAction.SUPERSEDE_EXISTING.value, TruthAction.RESOLVE_EXISTING.value, TruthAction.CONFIRM_EXISTING.value} and not candidate.target_memory_id:
            return self._decision(candidate, TruthAction.REVIEW_REQUIRED.value, "LIFECYCLE_TARGET_UNKNOWN")
        return None

    def _evaluate_one(
        self,
        candidate: TruthCandidate,
        memories: list[Mapping[str, Any]],
        revision: int,
        envelope: Optional[_CandidateEnvelope] = None,
    ) -> TruthDecision:
        invalid = self._validate_candidate(candidate, envelope)
        if invalid is not None:
            return TruthDecision(
                invalid.candidate_id,
                invalid.action,
                invalid.reason_code,
                source_memory_revision=revision,
                evidence_refs=candidate.evidence_refs,
            )
        target = self._find_by_id(memories, candidate.target_memory_id) if candidate.target_memory_id else None
        if candidate.operation != TruthAction.NEW.value:
            if target is None:
                return TruthDecision(candidate.candidate_id, TruthAction.REVIEW_REQUIRED.value, "LIFECYCLE_TARGET_UNKNOWN", source_memory_revision=revision, evidence_refs=candidate.evidence_refs)
            if not _same_scope(candidate, target):
                return TruthDecision(candidate.candidate_id, TruthAction.REVIEW_REQUIRED.value, "SCOPE_MISMATCH", target_memory_id=candidate.target_memory_id, source_memory_revision=revision, evidence_refs=candidate.evidence_refs)
            status = str(target.get("status") or "active").lower()
            if status not in _ALLOWED_STATUS:
                return TruthDecision(candidate.candidate_id, TruthAction.REVIEW_REQUIRED.value, "UNKNOWN_LIFECYCLE", target_memory_id=candidate.target_memory_id, source_memory_revision=revision, evidence_refs=candidate.evidence_refs)
            if candidate.operation == TruthAction.SUPERSEDE_EXISTING.value:
                successor_id = candidate.successor_memory_id or _new_memory_id()
                if status != "active":
                    return TruthDecision(candidate.candidate_id, TruthAction.REVIEW_REQUIRED.value, "TARGET_NOT_ACTIVE", target_memory_id=candidate.target_memory_id, successor_memory_id=successor_id, source_memory_revision=revision, evidence_refs=candidate.evidence_refs)
                if successor_id == candidate.target_memory_id or self._find_by_id(memories, successor_id) is not None:
                    return TruthDecision(candidate.candidate_id, TruthAction.REVIEW_REQUIRED.value, "SUPERSESSION_CYCLE_OR_DUPLICATE", target_memory_id=candidate.target_memory_id, successor_memory_id=successor_id, source_memory_revision=revision, evidence_refs=candidate.evidence_refs)
                return TruthDecision(candidate.candidate_id, TruthAction.SUPERSEDE_EXISTING.value, "EXPLICIT_SUPERSESSION", target_memory_id=candidate.target_memory_id, successor_memory_id=successor_id, source_memory_revision=revision, evidence_refs=candidate.evidence_refs)
            action = candidate.operation
            if action == TruthAction.CONFIRM_EXISTING.value:
                reason = "EXPLICIT_CONFIRMATION"
            elif status != "active":
                return TruthDecision(candidate.candidate_id, TruthAction.REVIEW_REQUIRED.value, "TARGET_NOT_ACTIVE", target_memory_id=candidate.target_memory_id, source_memory_revision=revision, evidence_refs=candidate.evidence_refs)
            else:
                reason = "EXPLICIT_LIFECYCLE_MUTATION"
            return TruthDecision(candidate.candidate_id, action, reason, target_memory_id=candidate.target_memory_id, source_memory_revision=revision, evidence_refs=candidate.evidence_refs)

        fingerprint = self._fingerprint(candidate)
        for memory in memories:
            if not _same_scope(candidate, memory):
                continue
            if str(memory.get("dedup_fingerprint") or "") == fingerprint:
                action = TruthAction.CONFIRM_EXISTING.value if candidate.note.upper() == "CONFIRM" else TruthAction.DUPLICATE.value
                return TruthDecision(candidate.candidate_id, action, "EXACT_SCOPED_FINGERPRINT", target_memory_id=_memory_id(memory), source_memory_revision=revision, evidence_refs=candidate.evidence_refs)
            if candidate.claim_key and str(memory.get("claim_key") or "") == candidate.claim_key and str(memory.get("status") or "active") == "active":
                return TruthDecision(candidate.candidate_id, TruthAction.CONFLICT.value, "ACTIVE_CLAIM_KEY_CONFLICT", target_memory_id=_memory_id(memory), source_memory_revision=revision, evidence_refs=candidate.evidence_refs)
        return TruthDecision(candidate.candidate_id, TruthAction.NEW.value, "NO_SCOPED_MATCH", source_memory_revision=revision, evidence_refs=candidate.evidence_refs)

    @staticmethod
    def _new_record(
        candidate: TruthCandidate,
        memory_id: str,
        envelope: Optional[_CandidateEnvelope] = None,
    ) -> dict[str, Any]:
        timestamp = candidate.occurred_at or _utc_now()
        fingerprint = candidate.dedup_fingerprint or scoped_fingerprint(candidate.content, candidate.scope, candidate.project_id, candidate.memory_type)
        source = envelope.source if envelope is not None else "extraction-v2"
        is_approved = envelope.is_approved if envelope is not None else candidate.commitment == "COMMITTED"
        return {
            "memory_id": memory_id,
            "id": -1,
            "source_id": f"truth:{candidate.candidate_id}",
            "type": candidate.memory_type or "observation",
            "content": candidate.content,
            "confidence": candidate.confidence,
            "source": source,
            "timestamp": timestamp,
            "related_notes": [],
            "section": "",
            "issues": [],
            "quality_score": candidate.confidence,
            "novelty": 1.0,
            "is_approved": is_approved,
            "status": "active",
            "resolved_at": "",
            "resolved_by": "",
            "resolution_note": "",
            "superseded_by": "",
            "supersession_note": "",
            "dedup_fingerprint": fingerprint,
            "scope": candidate.scope,
            "project": candidate.project if candidate.scope == "project" else "",
            "project_label": candidate.project if candidate.scope == "project" else "",
            "project_id": candidate.project_id,
            "claim_key": candidate.claim_key,
        }

    def process(
        self,
        candidates: Sequence[TruthCandidate | Mapping[str, Any]],
        *,
        expected_revision: Optional[int] = None,
        commit: bool = False,
        commit_new: bool = False,
        operation_id: Optional[str] = None,
    ) -> TruthResult:
        """Evaluate a batch and optionally persist only safe typed effects."""
        if operation_id is not None:
            from brain_eleven.operations import operation
            try:
                with operation(operation_id):
                    pass
            except ValueError:
                return TruthResult(TruthStatus.INVALID_INPUT.value, None, None, error_code="INVALID_OPERATION_ID")
        from brain_eleven.runtime.storage import identity
        try:
            envelopes = tuple(
                _normalize_candidate_envelope(candidate, operation_id=operation_id)
                for candidate in candidates
            )
            legacy_candidates = tuple(envelope.candidate for envelope in envelopes)
            envelopes, preflight_decisions = self._preflight(envelopes)
            normalized = tuple(envelope.candidate for envelope in envelopes)
            request_hash = identity(
                "request_",
                [legacy_request_projection(candidate) for candidate in legacy_candidates],
            )
            provenance_hash = identity(
                "provenance_",
                [[envelope.source, envelope.is_approved] for envelope in envelopes],
            )
        except TruthError as exc:
            return TruthResult(TruthStatus.INVALID_INPUT.value, None, None, error_code=exc.code)
        if not normalized:
            try:
                revision = self.store.revision()
            except MemoryStoreCorrupt:
                return TruthResult(TruthStatus.FAILED.value, None, None, error_code="MEMORY_STORE_CORRUPT")
            return TruthResult(TruthStatus.EMPTY.value, revision, revision)

        if all(decision is not None for decision in preflight_decisions):
            unavailable = any(
                decision is not None
                and decision.reason_code == "PROJECT_REGISTRY_UNAVAILABLE"
                for decision in preflight_decisions
            )
            status = TruthStatus.SCOPE_ERROR.value if unavailable else (
                TruthStatus.DEGRADED.value if commit else TruthStatus.SUCCESS.value
            )
            error_code = "PROJECT_REGISTRY_UNAVAILABLE" if unavailable else None
            return TruthResult(
                status,
                None,
                None,
                tuple(preflight_decisions),
                error_code=error_code,
            )

        def transact(latest: dict[str, Any]):
            revision = int(latest["revision"])
            if operation_id and commit:
                if latest.get("schema_version") != 3:
                    raise TruthInputError("Runtime receipt migration required")
                prior = latest.get("operation_receipts", {}).get(operation_id)
                if prior is not None:
                    if prior.get("request_hash") != request_hash:
                        raise _TruthReplayMismatch("Operation identity mismatch")
                    metadata_present = any(
                        envelope.has_source or envelope.has_approval
                        for envelope in envelopes
                    )
                    prior_provenance = prior.get("provenance_hash")
                    if prior_provenance is None:
                        if metadata_present:
                            raise _TruthReplayMismatch("Operation provenance identity mismatch")
                    elif prior_provenance != provenance_hash:
                        raise _TruthReplayMismatch("Operation provenance identity mismatch")
                    return no_change(([TruthDecision(**item) for item in prior["decisions"]], False))
            if commit and expected_revision is not None and expected_revision != revision:
                raise MemoryStoreConflict(expected_revision, revision)
            memories = [memory for memory in latest.get("validated_memory", []) if isinstance(memory, Mapping)]
            decisions = []
            for index, envelope in enumerate(envelopes):
                decision = preflight_decisions[index]
                if decision is None:
                    decision = self._evaluate_one(
                        envelope.candidate,
                        memories,
                        revision,
                        envelope,
                    )
                elif decision.reason_code != "PROJECT_REGISTRY_UNAVAILABLE":
                    decision = replace(decision, source_memory_revision=revision)
                decisions.append(decision)
            if not commit:
                return decisions
            mutated = False
            seen_fingerprints = {
                (*_memory_scope(memory), str(memory.get("dedup_fingerprint") or ""))
                for memory in memories
            }
            for index, (decision, envelope) in enumerate(zip(decisions, envelopes)):
                candidate = envelope.candidate
                if decision.action == TruthAction.SUPERSEDE_EXISTING.value:
                    target = self._find_by_id(memories, decision.target_memory_id or "")
                    if target is None:
                        continue
                    successor = self._new_record(candidate, decision.successor_memory_id, envelope)
                    latest.setdefault("validated_memory", []).append(successor)
                    memories.append(successor)
                    target["status"] = "superseded"
                    target["resolved_at"] = _utc_now()
                    target["resolved_by"] = candidate.resolved_by
                    target["superseded_by"] = decision.successor_memory_id or ""
                    target["supersession_note"] = candidate.note
                    mutated = True
                elif decision.action == TruthAction.RESOLVE_EXISTING.value:
                    target = self._find_by_id(memories, decision.target_memory_id or "")
                    if target is None:
                        continue
                    target["status"] = "resolved"
                    target["resolved_at"] = _utc_now()
                    target["resolved_by"] = candidate.resolved_by
                    target["resolution_note"] = candidate.note
                    mutated = True
                elif decision.action == TruthAction.NEW.value and commit_new:
                    fingerprint = self._fingerprint(candidate)
                    fingerprint_key = (candidate.scope, candidate.project_id if candidate.scope == "project" else "", fingerprint)
                    if fingerprint_key in seen_fingerprints:
                        existing = next(
                            (
                                memory
                                for memory in memories
                                if _same_scope(candidate, memory)
                                and str(memory.get("dedup_fingerprint") or "") == fingerprint
                            ),
                            None,
                        )
                        decisions[index] = TruthDecision(
                            candidate.candidate_id,
                            TruthAction.DUPLICATE.value,
                            "EXACT_SCOPED_FINGERPRINT",
                            target_memory_id=_memory_id(existing) if existing else None,
                            source_memory_revision=decision.source_memory_revision,
                            evidence_refs=candidate.evidence_refs,
                        )
                        continue
                    memory_id = candidate.successor_memory_id or _new_memory_id()
                    record = self._new_record(candidate, memory_id, envelope)
                    latest.setdefault("validated_memory", []).append(record)
                    memories.append(record)
                    seen_fingerprints.add(fingerprint_key)
                    decisions[index] = TruthDecision(
                        candidate.candidate_id,
                        TruthAction.NEW.value,
                        decision.reason_code,
                        successor_memory_id=memory_id,
                        source_memory_revision=decision.source_memory_revision,
                        evidence_refs=candidate.evidence_refs,
                    )
                    mutated = True
            if operation_id and all(item.action not in {"REJECT", "REVIEW_REQUIRED", "CONFLICT"} for item in decisions):
                latest["operation_receipts"][operation_id] = {
                    "request_hash": request_hash,
                    "provenance_hash": provenance_hash,
                    "decisions": [asdict(item) for item in decisions],
                }
                mutated = True
            if not mutated:
                return no_change((decisions, False))
            return decisions, True

        try:
            if commit:
                payload, persisted = self.store.transact(transact)
                decisions, mutated = payload
                status = TruthStatus.SUCCESS.value
                if any(decision.action in {TruthAction.CONFLICT.value, TruthAction.REVIEW_REQUIRED.value, TruthAction.REJECT.value} for decision in decisions):
                    status = TruthStatus.DEGRADED.value
                source_revision = int(persisted["revision"]) - 1 if mutated else int(persisted["revision"])
                return TruthResult(status, source_revision, int(persisted["revision"]), tuple(decisions))
            snapshot = self.store.load()
            revision = int(snapshot["revision"])
            decisions = transact(snapshot)
            return TruthResult(TruthStatus.SUCCESS.value, revision, revision, tuple(decisions))
        except MemoryStoreConflict:
            return TruthResult(TruthStatus.STALE_INPUT.value, None, None, error_code="MEMORY_STORE_CONFLICT")
        except MemoryStoreCorrupt:
            return TruthResult(TruthStatus.FAILED.value, None, None, error_code="MEMORY_STORE_CORRUPT")
        except TruthError as exc:
            return TruthResult(TruthStatus.INVALID_INPUT.value, None, None, error_code=exc.code)
        except (OSError, ValueError, TypeError):
            return TruthResult(TruthStatus.FAILED.value, None, None, error_code="MEMORY_TRUTH_FAILED")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate structured memory truth candidates")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--candidates", required=True, help="JSON array of structured candidates")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--commit-new", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        payload = json.loads(Path(arguments.candidates).read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise TruthInputError("candidate file must contain an array")
        result = MemoryTruthEngine(arguments.vault).process(payload, commit=arguments.commit, commit_new=arguments.commit_new)
    except (OSError, json.JSONDecodeError, TruthError) as exc:
        code = exc.code if isinstance(exc, TruthError) else "MEMORY_TRUTH_INVALID"
        print(json.dumps({"status": TruthStatus.INVALID_INPUT.value, "error_code": code}))
        return 2
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {TruthStatus.SUCCESS.value, TruthStatus.DEGRADED.value, TruthStatus.EMPTY.value} else 2


if __name__ == "__main__":
    raise SystemExit(main())
