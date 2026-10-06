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
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

try:
    from scripts.capture_safety import evaluate_capture
    from scripts.evidence import EvidenceBatch, EvidenceMessage, EvidenceTime
except ModuleNotFoundError as exc:  # pragma: no cover - deployed copied-hook fallback
    if exc.name != "scripts":
        raise
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
    ADD_REQUIREMENT = "ADD_REQUIREMENT"
    RESOLVE_REQUIREMENT = "RESOLVE_REQUIREMENT"


@dataclass(frozen=True)
class ExtractedBase:
    candidate_id: str
    candidate_type: str
    project_id: Optional[str]
    commitment: str
    occurred_at: Optional[EvidenceTime]
    confidence: float
    evidence_refs: tuple[str, ...]
    confidence_components: Mapping[str, float] = field(default_factory=dict)
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
# A short user turn that only approves what the assistant just proposed.
_AFFIRMATION = re.compile(r"^\s*(?:tamam|evet|olur|onaylıyorum|onayladım|kabul(?:\s+ediyorum)?|anlaştık|uygun|"
                          r"(?:önerin[e]?\s+)?uyalım|ok(?:ay)?|yes|agreed|approved|sounds good|go ahead|lgtm)\b[\s.!,]*"
                          r"(?:(?:öyle|böyle|şöyle)?\s*(?:yapalım|yap|olsun)[\s.!]*)?$", re.IGNORECASE)
_AFFIRMATION_MAX = 40
_EXPLICIT_CORRECTION = re.compile(r"\b(?:no|hayır|yanlış|değil|instead|yerine)\b", re.IGNORECASE)
_DECISION = re.compile(r"\b(?:decid(?:e|ed|ing)|decision|will use|we use|using|chosen|adopt|kullanacağız|kullanıyoruz|kullanılacak|seçtik|karar verdik|tercih ettik|uygulayacağız|karar verildi|kararlaştırdık|anlaştık|bundan sonra|bundan böyle|artık\s+\w+(?:acağız|eceğiz|ıyoruz|iyoruz|uyoruz|üyoruz)|\w+m[ae]y[ae]c[ae][ğk][ıi]z)\b", re.IGNORECASE)
_LESSON = re.compile(r"\b(?:learned|lesson|taught us|öğrendik|ders|sonuç|göstere|anladık|fark ettik|meğer|dersimiz)\b", re.IGNORECASE)
_PREFERENCE = re.compile(r"\b(?:prefer|preference|favorite|tercih ederim|seviyorum|istemiyorum)\b", re.IGNORECASE)
_CURRENT = re.compile(r"\b(?:currently|right now|still|blocked|blocker|failing|fails|in progress|active|şu anda|hâlâ|engelliyor|blokaj|fail|çalışmıyor|devam ediyor|aktif|hata veriyor|bozuk|patlıyor)\b", re.IGNORECASE)
_RESOLVED = re.compile(r"\b(?:resolved|fixed|closed|unblocked|çözüldü|kapatıldı|düzeldi|giderildi)\b", re.IGNORECASE)
_PHASE = re.compile(r"\b(?:phase|faz|aşama)\s*[- ]?(\d+(?:[A-Za-z])?)\b", re.IGNORECASE)
_REQUIREMENT = re.compile(r"\b(?:requirement|requirements|required|must|gereksinim|zorunlu|olmalı|gerekir)\b", re.IGNORECASE)

# Tool, terminal and diff output pasted into a user turn: evidence the user is
# showing, never a commitment (2026-09-29: such segments had become canonical
# requirements, blockers, the milestone and "decision" memories).
_PASTED_OUTPUT = re.compile(
    r"\btool exec result\b|\bWall time \d|\[graphify\b|\\r\\n|>>> [A-Z]{3,}"
    r"|^(?:\s*\d{1,5}:[ \t][^\n]*\n){2}\s*\d{1,5}:[ \t]|^diff --git |^@@|^(?:\+\+\+|---) [ab]/|^PS [A-Za-z]:\\|^[A-Za-z]:\\[^\n]*> "
    r"|^={4,}\s.*\s={4,}$|[\w./\\-]+\.(?:md|py|ps1|json|jsonl|ya?ml|toml|txt|log):\d+[:-]"
    r"|^(?:Mode\s+Length|On branch |Your branch |Fast-forward$|Updating [0-9a-f]{7,}\.\.)"
    r"|\"(?:chunk_id|exit_code|wall_time_seconds|original_token_count)\"",
    re.MULTILINE,
)


# A long, structured document the owner pasted (a proposal, plan, handoff or
# article) is material to discuss, not the owner deciding: 2026-10-01 a pasted
# retrieval proposal became four "decision" memories. Dictated messages are long
# but have few lines, so they are not matched.
PASTED_DOCUMENT_MIN_CHARS = 1500
PASTED_DOCUMENT_MIN_LINES = 25
PASTED_DOCUMENT_MIN_HEADINGS = 5
_HEADING_LINE = re.compile(r"^\s*(?:#{1,6}\s|\d{1,2}[.)]\s|[-*•]\s|[A-Z][A-Z0-9]{3,}-\d+\b)")


def _pasted_document(content: str) -> bool:
    if len(content) < PASTED_DOCUMENT_MIN_CHARS:
        return False
    lines = [line for line in content.splitlines() if line.strip()]
    headings = sum(1 for line in lines if _HEADING_LINE.match(line))
    return len(lines) >= PASTED_DOCUMENT_MIN_LINES or headings >= PASTED_DOCUMENT_MIN_HEADINGS


def _candidate_id(message: EvidenceMessage, index: int, kind: str) -> str:
    raw = "|".join((message.record.evidence_id, str(index), kind))
    return "cand_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _content_hash(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


# Dictation fillers (the owner dictates in Turkish). Deliberately narrow and
# case-sensitive so "II", "III", "HMM" and approvals like "hı hı" survive:
# - at the start of a segment: "E,", "Ee,", "ııı", "Hmm," ...
# - inside a segment: lowercase "ee+", "ıı+", "hmm+" between spaces, and "e,"
#   only right after a word (a letter "e" in "d, e, f" or "fn(a, e)" stays).
_LEADING_FILLER = re.compile(r"^(?:(?:[Ee],|[Ee]e+[,.]?|ıı+[,.]?|[Hh]mm+[,.]?)\s+)+")
_INNER_FILLER = re.compile(r"(?<=\w) e,(?= )| (?:ee+|ıı+|hmm+)[,.]?(?= )")


def strip_dictation_fillers(content: str) -> str:
    return _INNER_FILLER.sub("", _LEADING_FILLER.sub("", content)).strip()


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
    if _CURRENT.search(content) or _RESOLVED.search(content) or _REQUIREMENT.search(content):
        return Commitment.OBSERVED
    return Commitment.UNCERTAIN


def _confirmed_proposals(messages: Sequence[EvidenceMessage]) -> dict[int, str]:
    """Map an assistant message position to the evidence id of the user turn that approved it."""
    confirmed = {}
    for position in range(len(messages) - 1):
        current, following = messages[position], messages[position + 1]
        reply = following.content.strip()
        if (current.record.role == "assistant" and following.record.role == "user"
                and len(reply) <= _AFFIRMATION_MAX and _AFFIRMATION.match(reply)):
            confirmed[position] = following.record.evidence_id
    return confirmed


def _confidence_components(message: EvidenceMessage, content: str, commitment: Commitment,
                           *, confirmed: bool = False) -> tuple[float, dict[str, float]]:
    """Derive transparent confidence from independent evidence signals."""
    role = "user" if confirmed else message.record.role
    commitment_signal = {
        Commitment.COMMITTED: 0.92,
        Commitment.OBSERVED: 0.68,
        Commitment.NEGATED: 0.35,
        Commitment.PROPOSED: 0.20,
        Commitment.HYPOTHETICAL: 0.18,
        Commitment.QUESTION: 0.12,
        Commitment.QUOTED: 0.12,
        Commitment.UNCERTAIN: 0.25,
    }[commitment]
    source_authority = {"user": 1.0, "summary": 0.7}.get(role, 0.25)
    classification = 0.90 if any(pattern.search(content) for pattern in (_DECISION, _LESSON, _PREFERENCE, _CURRENT, _REQUIREMENT)) else 0.55
    scope = 1.0 if message.record.project_id else 0.0
    temporal = 0.80 if message.record.occurred_at is not None else 0.55
    reference = 0.30 if _EXPLICIT_CORRECTION.search(content) else 0.85
    components = {
        "commitment": commitment_signal,
        "source_authority": source_authority,
        "classification": classification,
        "scope": scope,
        "temporal": temporal,
        "reference": reference,
    }
    confidence = round(
        commitment_signal * 0.30 + source_authority * 0.20 + classification * 0.20
        + scope * 0.15 + temporal * 0.10 + reference * 0.05,
        4,
    )
    return confidence, components


def _base(
    message: EvidenceMessage,
    index: int,
    kind: str,
    commitment: Commitment,
    confidence: float,
    confidence_components: Mapping[str, float],
) -> dict[str, Any]:
    return {
        "candidate_id": _candidate_id(message, index, kind),
        "candidate_type": kind,
        "project_id": message.record.project_id,
        "commitment": commitment.value,
        "occurred_at": message.record.occurred_at,
        "confidence": confidence,
        "evidence_refs": (message.record.evidence_id,),
        "confidence_components": dict(confidence_components),
    }


def _state_operation(content: str) -> Optional[str]:
    if _RESOLVED.search(content) and re.search(r"\b(?:blocker|engelle|blokaj|deployment|deploy)\b", content, re.IGNORECASE):
        return StateOperation.RESOLVE_BLOCKER.value
    if _CURRENT.search(content) and re.search(r"\b(?:blocker|blocked|fail|failing|çalışmıyor|hata|error|test)\b", content, re.IGNORECASE):
        return StateOperation.ADD_BLOCKER.value
    if _PHASE.search(content) and re.search(r"\b(?:current|şu anda|aktif|doing|yapıyoruz|üzerindeyiz)\b", content, re.IGNORECASE):
        return StateOperation.SET_CURRENT_PHASE.value
    if _RESOLVED.search(content) and _REQUIREMENT.search(content):
        return StateOperation.RESOLVE_REQUIREMENT.value
    if _REQUIREMENT.search(content):
        return StateOperation.ADD_REQUIREMENT.value
    return None


def _memory_type(content: str) -> str:
    if _DECISION.search(content):
        return MemoryType.DECISION.value
    if _LESSON.search(content):
        return MemoryType.LESSON.value
    if _PREFERENCE.search(content):
        return MemoryType.PREFERENCE.value
    return MemoryType.OBSERVATION.value


# Compact-summary sections whose bullets are outcomes worth remembering; the
# rest (request, files, all user messages, pending tasks, next step) are not.
# "4. Errors and fixes:", also "## 4. Errors and fixes:", "**4. Errors and fixes:**"
# and "4. **Errors and fixes**:" (review of PR #50).
_SUMMARY_SECTION = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\*\*)?\s*\d+\.\s*(?:\*\*)?([^:\n*]+?)(?:\*\*)?:\s*(?:\*\*)?\s*$",
                              re.MULTILINE)
_SUMMARY_KEEP = re.compile(r"errors?\s+and\s+fix|problem\s+solving|hatalar|problem\s+çözme", re.IGNORECASE)
_SUMMARY_BULLET = re.compile(r"^\s*[-*•]\s+(.*)$")
MIN_SUMMARY_FACT_CHARS = 30


def summary_facts(content: str) -> list[str]:
    """Bullets of the outcome sections of a compact summary, sub-lines joined."""
    facts: list[str] = []
    headings = list(_SUMMARY_SECTION.finditer(content))
    for number, heading in enumerate(headings):
        if not _SUMMARY_KEEP.search(heading.group(1)):
            continue
        end = headings[number + 1].start() if number + 1 < len(headings) else len(content)
        current: list[str] = []
        for line in content[heading.end():end].splitlines():
            bullet = _SUMMARY_BULLET.match(line)
            top_level = bullet is not None and len(line) - len(line.lstrip()) <= 3
            if top_level:
                if current:
                    facts.append(" ".join(current))
                current = [bullet.group(1).strip()]
            elif current and line.strip():
                current.append(line.strip().lstrip("-*• ").strip())
        if current:
            facts.append(" ".join(current))
    return [" ".join(fact.split()) for fact in facts if len(fact.strip()) >= MIN_SUMMARY_FACT_CHARS]


def _summary_candidates(message: EvidenceMessage) -> list[NewMemoryCandidate]:
    candidates = []
    for index, fact in enumerate(summary_facts(message.content)):
        if _PASTED_OUTPUT.search(fact) or not evaluate_capture(fact).accepted:
            continue
        confidence, components = _confidence_components(message, fact, Commitment.OBSERVED)
        candidates.append(
            NewMemoryCandidate(
                **_base(message, index, CandidateKind.NEW_MEMORY.value, Commitment.OBSERVED, confidence, components),
                memory_type=_memory_type(fact),
                scope="project" if message.record.project_id else "unresolved",
                content=fact,
            )
        )
    return candidates


class DeterministicExtractor:
    """Extract safe candidate proposals from a role-aware evidence batch."""

    def extract(self, batch: EvidenceBatch) -> ExtractionEnvelope:
        accepted: list[NewMemoryCandidate | StateMutationProposal] = []
        quarantined: list[QuarantineCandidate] = []
        confirmations = _confirmed_proposals(batch.messages)
        for position, message in enumerate(batch.messages):
            if message.record.role == "summary":
                # Owner decision 2026-09-30: session summaries are the main
                # source; only their outcome sections become candidates.
                accepted.extend(_summary_candidates(message))
                continue
            approver = confirmations.get(position)
            if position - 1 in confirmations:
                # The approval turn carries no fact of its own; it is evidence on the approved candidate.
                continue
            pasted_document = message.record.role == "user" and _pasted_document(message.content)
            for index, content in enumerate(_segments(message.content)):
                # Fillers are dropped from the text only; the segment index
                # (and so the candidate id) is unchanged.
                content = strip_dictation_fillers(content)
                if len(content.strip()) < 3:
                    continue
                commitment = _classify_commitment(content, message.record.role)
                # An assistant decision the user explicitly approved in the next
                # turn is the user's decision; anything else it said stays a proposal.
                confirmed = (approver is not None and commitment is Commitment.PROPOSED
                             and _classify_commitment(content, "user") is Commitment.COMMITTED)
                if confirmed:
                    commitment = Commitment.COMMITTED
                confidence, components = _confidence_components(message, content, commitment, confirmed=confirmed)
                base = _base(message, index, CandidateKind.NEW_MEMORY.value, commitment, confidence, components)
                if confirmed:
                    base["evidence_refs"] = (message.record.evidence_id, approver)
                if _PASTED_OUTPUT.search(content):
                    quarantined.append(
                        QuarantineCandidate(
                            **_base(message, index, CandidateKind.QUARANTINE.value, commitment, 0.0, components),
                            reason="PASTED_OUTPUT",
                            content_hash=_content_hash(content),
                        )
                    )
                    continue
                if pasted_document:
                    quarantined.append(
                        QuarantineCandidate(
                            **_base(message, index, CandidateKind.QUARANTINE.value, commitment, 0.0, components),
                            reason="USER_PASTED_DOCUMENT",
                            content_hash=_content_hash(content),
                        )
                    )
                    continue
                safety = evaluate_capture(content)
                if not safety.accepted:
                    quarantined.append(
                        QuarantineCandidate(
                            **_base(message, index, CandidateKind.QUARANTINE.value, commitment, 0.0, components),
                            reason=safety.reason,
                            content_hash=_content_hash(content),
                        )
                    )
                    continue
                if message.record.project_id is None:
                    quarantined.append(
                        QuarantineCandidate(
                            **_base(message, index, CandidateKind.QUARANTINE.value, commitment, 0.0, components),
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
                            **_base(message, index, CandidateKind.QUARANTINE.value, commitment, 0.0, components),
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
                            **_base(message, index, CandidateKind.QUARANTINE.value, commitment, 0.0, components),
                            reason="LIFECYCLE_TARGET_UNKNOWN",
                            content_hash=_content_hash(content),
                        )
                    )
                operation = _state_operation(content)
                if operation is not None:
                    accepted.append(
                        StateMutationProposal(
                            **_base(message, index, CandidateKind.STATE_MUTATION.value, commitment, confidence, components),
                            operation=operation,
                            text=content,
                        )
                    )
                    continue
                if message.record.role == "user" and commitment is not Commitment.COMMITTED:
                    # Owner decision 2026-09-30: from the owner's own messages
                    # only explicit decisions become memory; status remarks
                    # still reach state (above) but not memory.
                    quarantined.append(
                        QuarantineCandidate(
                            **_base(message, index, CandidateKind.QUARANTINE.value, commitment, 0.0, components),
                            reason="USER_NOT_DECISION",
                            content_hash=_content_hash(content),
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
