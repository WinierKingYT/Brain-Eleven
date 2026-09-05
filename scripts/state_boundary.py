#!/usr/bin/env python3
"""Route extraction state proposals through the typed StateStore boundary.

PRE-07 deliberately keeps evidence, memory, and state authorities separate.
This module is the small adapter between PRE-04 extraction output and the
existing :class:`state_store.StateService`; it never writes MemoryStore and
never auto-registers a project.  A proposal is only canonicalized when the
caller explicitly requests ``commit=True`` and supplies trusted provenance.
"""

from __future__ import annotations

import re
import sys
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from extraction import NewMemoryCandidate, StateMutationProposal, StateOperation
from brain_eleven.projects.registry import ProjectRegistryError
from state_store import (
    StateError,
    StateProjectArchived,
    StateProjectUnknown,
    StateSchemaError,
    StateService,
    StateStoreConflict,
    StateStoreCorrupt,
    StateTransitionError,
)


BOUNDARY_SCHEMA_VERSION = 1
BOUNDARY_VERSION = "state-boundary-v1"
_PHASE = re.compile(r"\b(?:phase|faz|aşama)\s*[- ]?(\d+(?:[A-Za-z])?)\b", re.IGNORECASE)
_ALLOWED_COMMITMENTS = frozenset({"COMMITTED", "OBSERVED"})
_TRUSTED_SOURCE_TYPES = frozenset({"user", "system", "tool"})


class BoundaryStatus(str, Enum):
    SUCCESS = "SUCCESS"
    DRY_RUN = "DRY_RUN"
    SKIPPED = "SKIPPED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    SCOPE_ERROR = "SCOPE_ERROR"
    STALE_INPUT = "STALE_INPUT"
    FAILED = "FAILED"


@dataclass(frozen=True)
class BoundaryResult:
    """Content-safe result for one proposed state mutation."""

    status: str
    reason_code: str
    candidate_id: Optional[str] = None
    project_id: Optional[str] = None
    operation: Optional[str] = None
    record_id: Optional[str] = None
    revision_before: Optional[int] = None
    revision_after: Optional[int] = None
    canonical_write: bool = False
    boundary_version: str = BOUNDARY_VERSION
    schema_version: int = BOUNDARY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _value(candidate: Any, name: str, default: Any = None) -> Any:
    if isinstance(candidate, Mapping):
        return candidate.get(name, default)
    return getattr(candidate, name, default)


def _candidate_identity(candidate: Any) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    candidate_id = _value(candidate, "candidate_id")
    candidate_type = _value(candidate, "candidate_type")
    project_id = _value(candidate, "project_id")
    operation = _value(candidate, "operation")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ValueError("candidate_id is required")
    if not isinstance(candidate_type, str) or not candidate_type.strip():
        raise ValueError("candidate_type is required")
    if project_id is not None and (not isinstance(project_id, str) or not project_id.strip()):
        raise ValueError("project_id must be a non-empty string when present")
    return candidate_id.strip(), candidate_type.strip(), project_id.strip() if project_id else None, operation


def _source(candidate_id: str, source: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    if source is None:
        raise ValueError("source is required for canonical state mutation")
    if not isinstance(source, Mapping):
        raise ValueError("source must be an object")
    source_type = source.get("type")
    reference = source.get("reference", candidate_id)
    if source_type not in _TRUSTED_SOURCE_TYPES:
        raise ValueError("untrusted provenance cannot create canonical state")
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError("source.reference is required")
    return {"type": source_type, "reference": reference.strip()}


def _error_result(
    status: BoundaryStatus,
    reason_code: str,
    *,
    candidate_id: Optional[str] = None,
    project_id: Optional[str] = None,
    operation: Optional[str] = None,
    record_id: Optional[str] = None,
    before: Optional[int] = None,
) -> BoundaryResult:
    return BoundaryResult(
        status=status.value,
        reason_code=reason_code,
        candidate_id=candidate_id,
        project_id=project_id,
        operation=operation,
        record_id=record_id,
        revision_before=before,
    )


class StateBoundary:
    """Apply only safe, typed operational proposals to the current project."""

    def __init__(self, vault_path: str | Path):
        self.vault_path = Path(vault_path).expanduser()
        self.service = StateService(self.vault_path)

    @staticmethod
    def classify(candidate: Any) -> BoundaryResult:
        """Explain the authority route without performing filesystem I/O."""
        try:
            candidate_id, candidate_type, project_id, operation = _candidate_identity(candidate)
        except ValueError:
            return _error_result(BoundaryStatus.FAILED, "INVALID_CANDIDATE")
        if candidate_type == "NEW_MEMORY":
            reason = "OPEN_LOOP_TO_MEMORY" if _value(candidate, "memory_type") == "open_loop" else "MEMORY_TO_MEMORYSTORE"
            return _error_result(
                BoundaryStatus.SKIPPED,
                reason,
                candidate_id=candidate_id,
                project_id=project_id,
            )
        if candidate_type != "STATE_MUTATION":
            return _error_result(
                BoundaryStatus.FAILED,
                "UNSUPPORTED_CANDIDATE_TYPE",
                candidate_id=candidate_id,
                project_id=project_id,
                operation=operation,
            )
        return _error_result(
            BoundaryStatus.DRY_RUN,
            "STATE_PROPOSAL_READY",
            candidate_id=candidate_id,
            project_id=project_id,
            operation=operation,
        )

    def apply(
        self,
        candidate: StateMutationProposal | Mapping[str, Any] | NewMemoryCandidate,
        *,
        expected_revision: int,
        source: Optional[Mapping[str, Any]] = None,
        commit: bool = False,
        target_id: Optional[str] = None,
        severity: str = "MEDIUM",
        now: Optional[str] = None,
    ) -> BoundaryResult:
        """Validate and optionally apply one proposal.

        ``commit=False`` is the default and performs no canonical write.  A
        resolve operation needs an explicit target ID; the boundary never
        guesses from free text.
        """
        try:
            candidate_id, candidate_type, project_id, operation = _candidate_identity(candidate)
        except ValueError:
            return _error_result(BoundaryStatus.FAILED, "INVALID_CANDIDATE")
        if candidate_type == "NEW_MEMORY":
            return self.classify(candidate)
        if candidate_type != "STATE_MUTATION":
            return _error_result(BoundaryStatus.FAILED, "UNSUPPORTED_CANDIDATE_TYPE", candidate_id=candidate_id)
        if not project_id:
            return _error_result(BoundaryStatus.SCOPE_ERROR, "PROJECT_UNRESOLVED", candidate_id=candidate_id, operation=operation)
        commitment = _value(candidate, "commitment")
        if commitment not in _ALLOWED_COMMITMENTS:
            return _error_result(
                BoundaryStatus.REVIEW_REQUIRED,
                "UNTRUSTED_COMMITMENT",
                candidate_id=candidate_id,
                project_id=project_id,
                operation=operation,
            )
        canonical_source = None
        if commit:
            try:
                canonical_source = _source(candidate_id, source)
            except ValueError:
                return _error_result(
                    BoundaryStatus.REVIEW_REQUIRED,
                    "INVALID_PROVENANCE",
                    candidate_id=candidate_id,
                    project_id=project_id,
                    operation=operation,
                )
        try:
            before = self.service.store.project_revision(project_id)
        except StateStoreCorrupt:
            return _error_result(BoundaryStatus.FAILED, "STATE_CORRUPT", candidate_id=candidate_id, project_id=project_id, operation=operation)
        except (StateError, OSError):
            before = None
        if before is None:
            try:
                record = self.service.registry.get(project_id)
            except ProjectRegistryError:
                return _error_result(BoundaryStatus.FAILED, "PROJECT_REGISTRY_UNAVAILABLE", candidate_id=candidate_id, project_id=project_id, operation=operation)
            if record is None:
                reason = "PROJECT_UNKNOWN"
            elif record.get("status") == "archived":
                reason = "PROJECT_ARCHIVED"
            else:
                reason = "STATE_NOT_INITIALIZED"
            status = BoundaryStatus.SCOPE_ERROR if reason in {"PROJECT_UNKNOWN", "PROJECT_ARCHIVED"} else BoundaryStatus.FAILED
            return _error_result(status, reason, candidate_id=candidate_id, project_id=project_id, operation=operation)
        if not commit:
            return BoundaryResult(
                status=BoundaryStatus.DRY_RUN.value,
                reason_code="VALIDATED_NO_WRITE",
                candidate_id=candidate_id,
                project_id=project_id,
                operation=operation,
                revision_before=before,
            )

        text = _value(candidate, "text", "")
        if not isinstance(text, str) or not text.strip():
            return _error_result(BoundaryStatus.FAILED, "TEXT_REQUIRED", candidate_id=candidate_id, project_id=project_id, operation=operation, before=before)
        try:
            result: dict[str, Any]
            if operation == StateOperation.ADD_BLOCKER.value:
                result = self.service.add_blocker(project_id, text=text, severity=severity, expected_revision=expected_revision, source=canonical_source, now=now)
            elif operation == StateOperation.RESOLVE_BLOCKER.value:
                resolved_id = target_id or _value(candidate, "blocker_id") or _value(candidate, "target_id")
                if not resolved_id:
                    return _error_result(BoundaryStatus.REVIEW_REQUIRED, "LIFECYCLE_TARGET_REQUIRED", candidate_id=candidate_id, project_id=project_id, operation=operation, before=before)
                result = self.service.resolve_blocker(project_id, blocker_id=resolved_id, expected_revision=expected_revision, source=canonical_source, now=now)
            elif operation == StateOperation.ADD_WORK_ITEM.value:
                result = self.service.add_work_item(project_id, text=text, expected_revision=expected_revision, source=canonical_source, now=now)
            elif operation == StateOperation.SET_OBJECTIVE.value:
                result = self.service.set_current_objective(project_id, text=text, expected_revision=expected_revision, source=canonical_source, now=now)
            elif operation == StateOperation.SET_CURRENT_PHASE.value:
                phase = _PHASE.search(text)
                if not phase:
                    return _error_result(BoundaryStatus.REVIEW_REQUIRED, "PHASE_TARGET_REQUIRED", candidate_id=candidate_id, project_id=project_id, operation=operation, before=before)
                result = self.service.set_current_milestone(project_id, phase_id="phase-" + phase.group(1).lower(), title=text, expected_revision=expected_revision, source=canonical_source, now=now)
            elif operation == StateOperation.ADD_REQUIREMENT.value:
                result = self.service.add_requirement(project_id, text=text, expected_revision=expected_revision, source=canonical_source, now=now)
            elif operation == StateOperation.RESOLVE_REQUIREMENT.value:
                resolved_id = target_id or _value(candidate, "requirement_id") or _value(candidate, "target_id")
                if not resolved_id:
                    return _error_result(BoundaryStatus.REVIEW_REQUIRED, "LIFECYCLE_TARGET_REQUIRED", candidate_id=candidate_id, project_id=project_id, operation=operation, before=before)
                result = self.service.resolve_requirement(project_id, requirement_id=resolved_id, expected_revision=expected_revision, source=canonical_source, now=now)
            else:
                return _error_result(BoundaryStatus.FAILED, "UNSUPPORTED_STATE_OPERATION", candidate_id=candidate_id, project_id=project_id, operation=operation, before=before)
        except StateStoreConflict:
            return _error_result(BoundaryStatus.STALE_INPUT, "STATE_REVISION_CONFLICT", candidate_id=candidate_id, project_id=project_id, operation=operation, before=before)
        except StateProjectUnknown:
            return _error_result(BoundaryStatus.SCOPE_ERROR, "PROJECT_UNKNOWN", candidate_id=candidate_id, project_id=project_id, operation=operation, before=before)
        except StateProjectArchived:
            return _error_result(BoundaryStatus.SCOPE_ERROR, "PROJECT_ARCHIVED", candidate_id=candidate_id, project_id=project_id, operation=operation, before=before)
        except StateTransitionError:
            return _error_result(BoundaryStatus.FAILED, "INVALID_TRANSITION", candidate_id=candidate_id, project_id=project_id, operation=operation, before=before)
        except StateSchemaError:
            return _error_result(BoundaryStatus.FAILED, "INVALID_STATE_SCHEMA", candidate_id=candidate_id, project_id=project_id, operation=operation, before=before)
        except StateError:
            return _error_result(BoundaryStatus.FAILED, "STATE_MUTATION_FAILED", candidate_id=candidate_id, project_id=project_id, operation=operation, before=before)
        return BoundaryResult(
            status=BoundaryStatus.SUCCESS.value,
            reason_code="STATE_MUTATION_COMMITTED",
            candidate_id=candidate_id,
            project_id=project_id,
            operation=operation,
            record_id=result.get("id") if isinstance(result, Mapping) else None,
            revision_before=before,
            revision_after=before + 1,
            canonical_write=True,
        )

    def apply_batch(
        self,
        candidates: list[Any] | tuple[Any, ...],
        *,
        project_id: str,
        source: Optional[Mapping[str, Any]] = None,
        commit: bool = False,
        severity: str = "MEDIUM",
        now: Optional[str] = None,
    ) -> tuple[BoundaryResult, ...]:
        """Route all candidates while carrying the latest revision forward."""
        revision = self.service.store.project_revision(project_id)
        if revision is None:
            return tuple(self.apply(item, expected_revision=0, source=source, commit=commit, severity=severity, now=now) for item in candidates)
        results: list[BoundaryResult] = []
        for item in candidates:
            item_project = _value(item, "project_id")
            if item_project != project_id:
                results.append(_error_result(BoundaryStatus.SCOPE_ERROR, "WRONG_PROJECT_PROPOSAL", candidate_id=_value(item, "candidate_id"), project_id=item_project))
                continue
            outcome = self.apply(item, expected_revision=revision, source=source, commit=commit, severity=severity, now=now)
            results.append(outcome)
            if outcome.status == BoundaryStatus.SUCCESS.value and outcome.revision_after is not None:
                revision = outcome.revision_after
        return tuple(results)
