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
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from memory_scope import GLOBAL_SCOPE, infer_memory_scope, scoped_fingerprint
from memory_store import MemoryStore, MemoryStoreConflict, MemoryStoreCorrupt, no_change


class TruthError(RuntimeError):
    """Base error with a stable machine-readable code."""

    code = "MEMORY_TRUTH_FAILED"


class TruthInputError(TruthError):
    code = "MEMORY_TRUTH_INVALID"


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


_SECRET = re.compile(r"(?i)(api[_-]?key|secret|password|token|private[_-]?key)\s*[:=]")
_ALLOWED_STATUS = {"active", "resolved", "superseded"}
_ALLOWED_SCOPE = {GLOBAL_SCOPE, "project"}


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
        candidate = cls(
            candidate_id=str(value.get("candidate_id") or "").strip(),
            content=str(value.get("content") or "").strip(),
            memory_type=str(value.get("memory_type", value.get("type", "")) or "").strip().lower(),
            scope=str(value.get("scope") or GLOBAL_SCOPE).strip().lower(),
            project_id=str(value.get("project_id") or "").strip(),
            project=str(value.get("project") or "").strip(),
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

    def _validate_candidate(self, candidate: TruthCandidate) -> Optional[TruthDecision]:
        if _SECRET.search(candidate.content):
            return TruthDecision(candidate.candidate_id, TruthAction.REJECT.value, "SECRET_CONTENT", evidence_refs=candidate.evidence_refs)
        if candidate.commitment != "COMMITTED":
            return TruthDecision(candidate.candidate_id, TruthAction.REVIEW_REQUIRED.value, "UNCOMMITTED_CANDIDATE", evidence_refs=candidate.evidence_refs)
        if candidate.scope == "project" and not candidate.project_id:
            return TruthDecision(candidate.candidate_id, TruthAction.REJECT.value, "SCOPE_UNRESOLVED", evidence_refs=candidate.evidence_refs)
        if candidate.operation in {TruthAction.SUPERSEDE_EXISTING.value, TruthAction.RESOLVE_EXISTING.value, TruthAction.CONFIRM_EXISTING.value} and not candidate.target_memory_id:
            return TruthDecision(candidate.candidate_id, TruthAction.REVIEW_REQUIRED.value, "LIFECYCLE_TARGET_UNKNOWN", evidence_refs=candidate.evidence_refs)
        return None

    def _evaluate_one(self, candidate: TruthCandidate, memories: list[Mapping[str, Any]], revision: int) -> TruthDecision:
        invalid = self._validate_candidate(candidate)
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
    def _new_record(candidate: TruthCandidate, memory_id: str) -> dict[str, Any]:
        timestamp = candidate.occurred_at or _utc_now()
        fingerprint = candidate.dedup_fingerprint or scoped_fingerprint(candidate.content, candidate.scope, candidate.project_id, candidate.memory_type)
        return {
            "memory_id": memory_id,
            "id": -1,
            "source_id": f"truth:{candidate.candidate_id}",
            "type": candidate.memory_type or "observation",
            "content": candidate.content,
            "confidence": candidate.confidence,
            "source": "extraction-v2",
            "timestamp": timestamp,
            "related_notes": [],
            "section": "",
            "issues": [],
            "quality_score": candidate.confidence,
            "novelty": 1.0,
            "is_approved": True,
            "status": "active",
            "resolved_at": "",
            "resolved_by": "",
            "resolution_note": "",
            "superseded_by": "",
            "supersession_note": "",
            "dedup_fingerprint": fingerprint,
            "scope": candidate.scope,
            "project": candidate.project or candidate.project_id,
            "project_label": candidate.project or candidate.project_id,
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
    ) -> TruthResult:
        """Evaluate a batch and optionally persist only safe typed effects."""
        try:
            normalized = tuple(candidate if isinstance(candidate, TruthCandidate) else TruthCandidate.from_mapping(candidate) for candidate in candidates)
        except TruthError as exc:
            return TruthResult(TruthStatus.INVALID_INPUT.value, None, None, error_code=exc.code)
        if not normalized:
            try:
                revision = self.store.revision()
            except MemoryStoreCorrupt:
                return TruthResult(TruthStatus.FAILED.value, None, None, error_code="MEMORY_STORE_CORRUPT")
            return TruthResult(TruthStatus.EMPTY.value, revision, revision)

        def transact(latest: dict[str, Any]):
            revision = int(latest["revision"])
            memories = [memory for memory in latest.get("validated_memory", []) if isinstance(memory, Mapping)]
            decisions = [self._evaluate_one(candidate, memories, revision) for candidate in normalized]
            if not commit:
                return decisions
            mutated = False
            seen_fingerprints = {
                (*_memory_scope(memory), str(memory.get("dedup_fingerprint") or ""))
                for memory in memories
            }
            for index, (decision, candidate) in enumerate(zip(decisions, normalized)):
                if decision.action == TruthAction.SUPERSEDE_EXISTING.value:
                    target = self._find_by_id(memories, decision.target_memory_id or "")
                    if target is None:
                        continue
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
                    record = self._new_record(candidate, memory_id)
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
            if not mutated:
                return no_change((decisions, False))
            return decisions, True

        try:
            if commit:
                payload, persisted = self.store.transact(transact, expected_revision=expected_revision)
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
