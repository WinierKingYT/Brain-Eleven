#!/usr/bin/env python3
"""Deterministic, role-aware extraction candidates for PRE-04.

The extractor consumes ephemeral ``EvidenceMessage`` objects and returns
reviewable candidates.  It does not resolve existing memory IDs, mutate
lifecycle, write StateStore/MemoryStore, or treat model/assistant prose as a
user commitment.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional, Sequence

from capture_safety import evaluate_capture
from evidence import EvidenceBatch, EvidenceMessage, EvidenceTime


EXTRACTION_SCHEMA_VERSION = 1
EXTRACTOR_VERSION = "extraction-v2-deterministic"


class Commitment(str, Enum):
    COMMITTED = "COMMITTED"
    PROPOSED = "PROPOSED"
    HYPOTHETICAL = "HYPOTHETICAL"
    QUESTION = "QUESTION"
    NEGATED = "NEGATED"
    QUOTED = "QUOTED"
    OBSERVED = "OBSERVED"
    UNCERTAIN = "UNCERTAIN"


class CandidateKind(str, Enum):
    NEW_MEMORY = "NEW_MEMORY"
    STATE_MUTATION = "STATE_MUTATION"
    QUARANTINE = "QUARANTINE"


class MemoryType(str, Enum):
    DECISION = "decision"
    LESSON = "lesson"
    PREFERENCE = "preference"
    OBSERVATION = "observation"
    OPEN_LOOP = "open_loop"


class StateOperation(str, Enum):
    ADD_BLOCKER = "ADD_BLOCKER"
    RESOLVE_BLOCKER = "RESOLVE_BLOCKER"
    SET_CURRENT_PHASE = "SET_CURRENT_PHASE"
    ADD_WORK_ITEM = "ADD_WORK_ITEM"
    SET_OBJECTIVE = "SET_OBJECTIVE"


@dataclass(frozen=True)
class ExtractedBase:
    candidate_id: str
    candidate_type: str
    project_id: Optional[str]
    commitment: str
    occurred_at: Optional[EvidenceTime]
    confidence: float
    evidence_refs: tuple[str, ...]
    extractor_version: str = EXTRACTOR_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NewMemoryCandidate(ExtractedBase):
    memory_type: str = MemoryType.OBSERVATION.value
    scope: str = "unresolved"
    content: str = ""


@dataclass(frozen=True)
class StateMutationProposal(ExtractedBase):
    operation: str = StateOperation.ADD_WORK_ITEM.value
    text: str = ""


@dataclass(frozen=True)
class QuarantineCandidate(ExtractedBase):
    reason: str = ""
    content_hash: str = ""


@dataclass(frozen=True)
class ExtractionEnvelope:
    candidates: tuple[NewMemoryCandidate | StateMutationProposal, ...]
    quarantined: tuple[QuarantineCandidate, ...]
    extractor_version: str = EXTRACTOR_VERSION
    schema_version: int = EXTRACTION_SCHEMA_VERSION

    def to_dict(self, *, include_content: bool = True) -> dict[str, Any]:
        def render(candidate: Any) -> dict[str, Any]:
            payload = candidate.to_dict()
            payload["evidence_refs"] = list(payload["evidence_refs"])
            if payload.get("occurred_at") is not None:
                payload["occurred_at"] = dict(payload["occurred_at"])
            if not include_content:
                payload.pop("content", None)
                payload.pop("text", None)
            return payload

        return {
            "schema_version": self.schema_version,
            "extractor_version": self.extractor_version,
            "candidates": [render(item) for item in self.candidates],
            "quarantined": [render(item) for item in self.quarantined],
        }


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？])\s+|\s*;\s*|\s+\b(?:ama|fakat|ancak|but|however)\s+", re.IGNORECASE)
_QUESTION = re.compile(r"\?|\b(?:should we|could we|shall we|do we|what if|kullansak|yapalım mı|geçelim mi|mi|mı|mu|mü)\b", re.IGNORECASE)
_HYPOTHETICAL = re.compile(r"\b(?:maybe|perhaps|might|could|we could|we might|consider|let'?s consider|belki|olabilir|kullanabiliriz|düşünebiliriz|düşünelim)\b", re.IGNORECASE)
_QUOTE = re.compile(r"(?:^|\s)[\"'“‘].*[\"'”’](?:$|\s)|\b(?:quoted|quote|alıntı|alıntıdaki|blogda|dokümanda)\b", re.IGNORECASE | re.DOTALL)
_EXPLICIT_CORRECTION = re.compile(r"\b(?:no|hayır|yanlış|değil|instead|yerine)\b", re.IGNORECASE)
_DECISION = re.compile(r"\b(?:decid(?:e|ed|ing)|decision|will use|we use|using|chosen|adopt|kullanacağız|kullanıyoruz|kullanılacak|seçtik|karar verdik|tercih ettik|uygulayacağız)\b", re.IGNORECASE)
_LESSON = re.compile(r"\b(?:learned|lesson|taught us|öğrendik|ders|sonuç|göstere|anladık)\b", re.IGNORECASE)
_PREFERENCE = re.compile(r"\b(?:prefer|preference|favorite|tercih ederim|seviyorum|istemiyorum)\b", re.IGNORECASE)
_CURRENT = re.compile(r"\b(?:currently|right now|still|blocked|blocker|failing|fails|in progress|active|şu anda|hâlâ|engelliyor|blokaj|fail|çalışmıyor|devam ediyor|aktif)\b", re.IGNORECASE)
_RESOLVED = re.compile(r"\b(?:resolved|fixed|closed|unblocked|çözüldü|kapatıldı|düzeldi|giderildi)\b", re.IGNORECASE)
_PHASE = re.compile(r"\b(?:phase|faz|aşama)\s*[- ]?(\d+(?:[A-Za-z])?)\b", re.IGNORECASE)


def _candidate_id(message: EvidenceMessage, index: int, kind: str) -> str:
    raw = "|".join((message.record.evidence_id, str(index), kind))
    return "cand_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _content_hash(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _segments(content: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT.split(content) if part.strip()]


def _classify_commitment(content: str, role: str) -> Commitment:
    if _QUOTE.search(content):
        return Commitment.QUOTED
    if _QUESTION.search(content):
        return Commitment.QUESTION
    if _HYPOTHETICAL.search(content):
        return Commitment.HYPOTHETICAL
    if role in {"assistant", "tool", "system"}:
        return Commitment.PROPOSED
    if _EXPLICIT_CORRECTION.search(content) and not _DECISION.search(content):
        return Commitment.NEGATED
    if _DECISION.search(content) or re.search(r"\b(?:tamam|evet),?\s+.+\b(?:kullan|yap|geç)\w*", content, re.IGNORECASE):
        return Commitment.COMMITTED
    if _CURRENT.search(content):
        return Commitment.OBSERVED
    return Commitment.UNCERTAIN


def _base(message: EvidenceMessage, index: int, kind: str, commitment: Commitment, confidence: float) -> dict[str, Any]:
    return {
        "candidate_id": _candidate_id(message, index, kind),
        "candidate_type": kind,
        "project_id": message.record.project_id,
        "commitment": commitment.value,
        "occurred_at": message.record.occurred_at,
        "confidence": confidence,
        "evidence_refs": (message.record.evidence_id,),
    }


def _state_operation(content: str) -> Optional[str]:
    if _RESOLVED.search(content) and re.search(r"\b(?:blocker|engelle|blokaj|deployment|deploy)\b", content, re.IGNORECASE):
        return StateOperation.RESOLVE_BLOCKER.value
    if _CURRENT.search(content) and re.search(r"\b(?:blocker|blocked|fail|failing|çalışmıyor|hata|error|test)\b", content, re.IGNORECASE):
        return StateOperation.ADD_BLOCKER.value
    if _PHASE.search(content) and re.search(r"\b(?:current|şu anda|aktif|doing|yapıyoruz|üzerindeyiz)\b", content, re.IGNORECASE):
        return StateOperation.SET_CURRENT_PHASE.value
    return None


def _memory_type(content: str) -> str:
    if _DECISION.search(content):
        return MemoryType.DECISION.value
    if _LESSON.search(content):
        return MemoryType.LESSON.value
    if _PREFERENCE.search(content):
        return MemoryType.PREFERENCE.value
    return MemoryType.OBSERVATION.value


class DeterministicExtractor:
    """Extract safe candidate proposals from a role-aware evidence batch."""

    def extract(self, batch: EvidenceBatch) -> ExtractionEnvelope:
        accepted: list[NewMemoryCandidate | StateMutationProposal] = []
        quarantined: list[QuarantineCandidate] = []
        for message in batch.messages:
            for index, content in enumerate(_segments(message.content)):
                if len(content.strip()) < 3:
                    continue
                commitment = _classify_commitment(content, message.record.role)
                base = _base(message, index, CandidateKind.NEW_MEMORY.value, commitment, 0.97)
                safety = evaluate_capture(content)
                if not safety.accepted:
                    quarantined.append(
                        QuarantineCandidate(
                            **_base(message, index, CandidateKind.QUARANTINE.value, commitment, 0.0),
                            reason=safety.reason,
                            content_hash=_content_hash(content),
                        )
                    )
                    continue
                if message.record.project_id is None:
                    quarantined.append(
                        QuarantineCandidate(
                            **_base(message, index, CandidateKind.QUARANTINE.value, commitment, 0.0),
                            reason="SCOPE_UNRESOLVED",
                            content_hash=_content_hash(content),
                        )
                    )
                    continue
                if commitment in {
                    Commitment.PROPOSED,
                    Commitment.HYPOTHETICAL,
                    Commitment.QUESTION,
                    Commitment.QUOTED,
                    Commitment.NEGATED,
                    Commitment.UNCERTAIN,
                }:
                    quarantined.append(
                        QuarantineCandidate(
                            **_base(message, index, CandidateKind.QUARANTINE.value, commitment, 0.0),
                            reason={
                                Commitment.PROPOSED: "ASSISTANT_PROPOSAL",
                                Commitment.HYPOTHETICAL: "HYPOTHETICAL_NOT_COMMITMENT",
                                Commitment.QUESTION: "QUESTION_NOT_COMMITMENT",
                                Commitment.QUOTED: "QUOTED_CONTENT",
                                Commitment.NEGATED: "NEGATED_CLAIM",
                                Commitment.UNCERTAIN: "LOW_EVIDENCE_COMMITMENT",
                            }[commitment],
                            content_hash=_content_hash(content),
                        )
                    )
                    continue
                if _EXPLICIT_CORRECTION.search(content) and _DECISION.search(content):
                    # PRE-04 cannot safely identify the prior canonical memory;
                    # PRE-06 may turn this explicit correction into a mutation.
                    quarantined.append(
                        QuarantineCandidate(
                            **_base(message, index, CandidateKind.QUARANTINE.value, commitment, 0.0),
                            reason="LIFECYCLE_TARGET_UNKNOWN",
                            content_hash=_content_hash(content),
                        )
                    )
                operation = _state_operation(content)
                if operation is not None:
                    accepted.append(
                        StateMutationProposal(
                            **_base(message, index, CandidateKind.STATE_MUTATION.value, commitment, 0.94),
                            operation=operation,
                            text=content,
                        )
                    )
                    continue
                scope = "project" if message.record.project_id else "unresolved"
                accepted.append(
                    NewMemoryCandidate(
                        **base,
                        memory_type=_memory_type(content),
                        scope=scope,
                        content=content,
                    )
                )
        return ExtractionEnvelope(candidates=tuple(accepted), quarantined=tuple(quarantined))


def extract(batch: EvidenceBatch) -> ExtractionEnvelope:
    """Convenience entry point for the deterministic PRE-04 provider."""
    return DeterministicExtractor().extract(batch)
