"""Deterministic metadata-first authority and conflict rules."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional

from .adapters import AuthorityEvidenceError, EvidenceItem, EvidenceSnapshot
from .models import ClaimEnvelope, ConflictSet, ExplanationEntry, ResolutionCandidate


class AuthorityPolicyError(RuntimeError):
    """The canonical metadata contains an unresolvable integrity violation."""


def _conflict_id(kind: str, candidate_ids: Iterable[str]) -> str:
    payload = f"{kind}:{','.join(sorted(candidate_ids))}".encode("utf-8")
    return "conf_" + hashlib.sha256(payload).hexdigest()[:20]


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _memory_claim(item: EvidenceItem) -> ClaimEnvelope:
    record = item.record
    source = "DECLARED" if isinstance(record.get("source"), str) and record.get("source").strip() else "INCOMPLETE"
    fingerprint = record.get("dedup_fingerprint")
    return ClaimEnvelope(
        candidate_id=item.candidate.candidate_id,
        claim_class=f"MEMORY_{str(record.get('type', 'unknown')).upper()}",
        project_id=item.project_id,
        scope="project" if item.project_id else "global",
        lifecycle=str(record.get("status", "active")).casefold(),
        provenance=source,
        dedup_fingerprint=fingerprint if isinstance(fingerprint, str) and fingerprint else None,
        superseded_by=record.get("superseded_by") if isinstance(record.get("superseded_by"), str) and record.get("superseded_by") else None,
    )


def _state_claim(item: EvidenceItem) -> ClaimEnvelope:
    source = item.record.get("source")
    source_type = source.get("type") if isinstance(source, Mapping) else None
    provenance = f"STATE_{str(source_type).upper()}" if source_type in {"user", "system", "tool"} else "INCOMPLETE"
    return ClaimEnvelope(
        candidate_id=item.candidate.candidate_id,
        claim_class=f"TASK_STATE_{str(item.state_kind).upper()}",
        project_id=item.project_id,
        scope="project",
        lifecycle=str(item.record.get("status", "active")).casefold(),
        provenance=provenance,
        state_kind=item.state_kind,
    )


def normalize_claim(item: EvidenceItem) -> ClaimEnvelope:
    if item.candidate.source_type == "memory":
        return _memory_claim(item)
    if item.candidate.source_type == "state":
        return _state_claim(item)
    raise AuthorityEvidenceError(f"Unsupported evidence source: {item.candidate.source_type}")


def _base_candidate(item: EvidenceItem, claim: ClaimEnvelope) -> ResolutionCandidate:
    if item.candidate.source_type == "state":
        return ResolutionCandidate(
            candidate_id=item.candidate.candidate_id,
            source_type="state",
            project_id=item.project_id,
            canonical_ref=item.candidate.canonical_ref,
            claim=claim,
            status="AUTHORITATIVE",
            action="ACCEPT_SINGLE",
            reason_codes=("typed_current_state",),
        )
    lifecycle = claim.lifecycle
    if lifecycle == "superseded":
        status, action, code = "SUPERSEDED", "PREFER", "canonical_superseded"
    elif lifecycle == "resolved":
        status, action, code = "HISTORICAL", "KEEP_BOTH_TEMPORAL", "canonical_resolved"
    else:
        status, action, code = "SUPPORTING", "KEEP_BOTH", "active_metadata_only"
    if claim.provenance == "INCOMPLETE":
        code = "incomplete_provenance_no_preference"
    return ResolutionCandidate(
        candidate_id=item.candidate.candidate_id,
        source_type="memory",
        project_id=item.project_id,
        canonical_ref=item.candidate.canonical_ref,
        claim=claim,
        status=status,
        action=action,
        reason_codes=(code,),
    )


def _replace(
    candidates: dict[str, ResolutionCandidate],
    candidate_id: str,
    *,
    status: Optional[str] = None,
    action: Optional[str] = None,
    code: Optional[str] = None,
) -> None:
    current = candidates[candidate_id]
    codes = tuple(sorted(set(current.reason_codes + ((code,) if code else ()))))
    candidates[candidate_id] = replace(
        current,
        status=status or current.status,
        action=action or current.action,
        reason_codes=codes,
    )


def _memory_scope_key(item: EvidenceItem) -> tuple[str, Optional[str]]:
    return ("project", item.project_id) if item.project_id else ("global", None)


def _supersession_chain(records: Mapping[str, Mapping[str, Any]], start: str) -> tuple[str, ...]:
    visited: list[str] = []
    current = start
    while current:
        if current in visited:
            cycle = visited[visited.index(current) :] + [current]
            raise AuthorityPolicyError(f"Supersession cycle: {' -> '.join(cycle)}")
        visited.append(current)
        record = records.get(current)
        if record is None:
            return tuple(visited)
        successor = record.get("superseded_by")
        current = successor if isinstance(successor, str) and successor else ""
    return tuple(visited)


def resolve_metadata(snapshot: EvidenceSnapshot) -> tuple[
    tuple[ResolutionCandidate, ...], tuple[ConflictSet, ...], tuple[ExplanationEntry, ...]
]:
    """Resolve only explicit lifecycle, identity, scope, and reference facts."""
    claims = {item.candidate.candidate_id: normalize_claim(item) for item in snapshot.items}
    candidates = {item.candidate.candidate_id: _base_candidate(item, claims[item.candidate.candidate_id]) for item in snapshot.items}
    item_by_id = {item.candidate.candidate_id: item for item in snapshot.items}
    memory_items = [item for item in snapshot.items if item.candidate.source_type == "memory"]
    state_items = [item for item in snapshot.items if item.candidate.source_type == "state"]
    conflicts: list[ConflictSet] = []
    ledger: list[ExplanationEntry] = []

    # Explicit supersession is the only cross-record semantic relationship in V1.
    selected_memory_ids = {item.candidate.candidate_id for item in memory_items}
    for item in sorted(memory_items, key=lambda value: value.candidate.candidate_id):
        memory_id = item.candidate.candidate_id
        chain = _supersession_chain(snapshot.memory_records, memory_id)
        successor = claims[memory_id].superseded_by
        if successor:
            successor_record = snapshot.memory_records.get(successor)
            if successor_record is None:
                _replace(candidates, memory_id, status="INVALID", action="INVALID", code="dangling_supersession")
                ledger.append(ExplanationEntry((memory_id,), "dangling_supersession", "INVALID"))
                continue
            if _memory_scope_key(item) != (
                ("project", successor_record.get("project_id")) if successor_record.get("scope") == "project" else ("global", None)
            ):
                raise AuthorityPolicyError(f"Supersession crosses scope: {memory_id}")
            _replace(candidates, memory_id, status="SUPERSEDED", action="PREFER", code="explicit_supersession")
            if successor in selected_memory_ids:
                _replace(candidates, successor, status="AUTHORITATIVE", action="PREFER", code="explicit_supersession_successor")
                group = (memory_id, successor)
                conflicts.append(
                    ConflictSet(
                        _conflict_id("SUPERSESSION", group),
                        "SUPERSESSION",
                        group,
                        "PREFER",
                        ("explicit_supersession",),
                    )
                )
                ledger.append(ExplanationEntry(group, "explicit_supersession", "PREFER"))

    # Fingerprints identify exact duplicate semantics only within one scope.
    duplicate_groups: dict[tuple[tuple[str, Optional[str]], str], list[EvidenceItem]] = {}
    for item in memory_items:
        fingerprint = claims[item.candidate.candidate_id].dedup_fingerprint
        if fingerprint:
            duplicate_groups.setdefault((_memory_scope_key(item), fingerprint), []).append(item)
    for group in duplicate_groups.values():
        if len(group) < 2:
            continue
        ids = tuple(sorted(item.candidate.candidate_id for item in group))
        missing_timestamp = any(not _valid_timestamp(item.record.get("timestamp")) for item in group)
        incomplete_provenance = any(
            claims[item.candidate.candidate_id].provenance == "INCOMPLETE" for item in group
        )
        if missing_timestamp or incomplete_provenance:
            code = "duplicate_incomplete_metadata" if incomplete_provenance else "duplicate_missing_timestamp"
            for candidate_id in ids:
                _replace(candidates, candidate_id, status="UNRESOLVED", action="REQUIRES_CLARIFICATION", code=code)
            action = "REQUIRES_CLARIFICATION"
        else:
            winner = min(group, key=lambda item: (str(item.record["timestamp"]), item.candidate.candidate_id))
            _replace(candidates, winner.candidate.candidate_id, status="AUTHORITATIVE", action="PREFER", code="duplicate_canonical_identity")
            for candidate_id in ids:
                if candidate_id != winner.candidate.candidate_id:
                    _replace(candidates, candidate_id, status="SUPPORTING", action="PREFER", code="duplicate_canonical_identity")
            action, code = "PREFER", "duplicate_canonical_identity"
        conflicts.append(ConflictSet(_conflict_id("DUPLICATE", ids), "DUPLICATE", ids, action, (code,)))
        ledger.append(ExplanationEntry(ids, code, action))

    # Global and project claims coexist; metadata has no applicability override.
    globals_ = [item.candidate.candidate_id for item in memory_items if item.project_id is None]
    projects: dict[str, list[str]] = {}
    for item in memory_items + state_items:
        if item.project_id:
            projects.setdefault(item.project_id, []).append(item.candidate.candidate_id)
    if globals_:
        for project_id, project_candidates in sorted(projects.items()):
            ids = tuple(sorted(set(globals_ + project_candidates)))
            if len(ids) > 1:
                conflicts.append(
                    ConflictSet(_conflict_id(f"SCOPE:{project_id}", ids), "SCOPE_SEPARATION", ids, "KEEP_BOTH_SCOPED", ("global_project_not_comparable",))
                )
                ledger.append(ExplanationEntry(ids, "global_project_not_comparable", "KEEP_BOTH_SCOPED"))

    # A live blocker explicitly tied to historical memory is an implementation gap.
    selected_by_memory_id = {item.candidate.candidate_id: item for item in memory_items}
    for item in state_items:
        if item.state_kind != "blocker" or str(item.record.get("status", "")).upper() != "ACTIVE":
            continue
        memory_ref = item.record.get("memory_ref")
        referenced = selected_by_memory_id.get(memory_ref) if isinstance(memory_ref, str) else None
        if referenced is None:
            continue
        memory_resolution = candidates[referenced.candidate.candidate_id]
        if memory_resolution.status in {"HISTORICAL", "SUPERSEDED", "INVALID"}:
            ids = tuple(sorted((item.candidate.candidate_id, referenced.candidate.candidate_id)))
            for candidate_id in ids:
                _replace(candidates, candidate_id, status="IMPLEMENTATION_GAP", action="MARK_IMPLEMENTATION_GAP", code="active_blocker_references_historical_memory")
            conflicts.append(
                ConflictSet(
                    _conflict_id("IMPLEMENTATION_GAP", ids),
                    "IMPLEMENTATION_GAP",
                    ids,
                    "MARK_IMPLEMENTATION_GAP",
                    ("active_blocker_references_historical_memory",),
                )
            )
            ledger.append(ExplanationEntry(ids, "active_blocker_references_historical_memory", "MARK_IMPLEMENTATION_GAP"))

    return (
        tuple(sorted(candidates.values(), key=lambda candidate: candidate.candidate_id)),
        tuple(sorted(conflicts, key=lambda conflict: conflict.conflict_id)),
        tuple(sorted(ledger, key=lambda entry: (entry.subject_ids, entry.code, entry.action))),
    )
