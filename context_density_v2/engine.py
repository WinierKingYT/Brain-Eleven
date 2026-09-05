"""Deterministic PRE-09 diversity, coverage, and density engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .models import DensityOptions, DensityResult, DensitySelectedCandidate


POLICY_VERSION = "context-density-v2-policy-v1"


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _revisions(result: Any) -> Mapping[str, Any]:
    value = _get(result, "input_revisions", {})
    return value if isinstance(value, Mapping) else {}


def _number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def _tokens(candidate: Any) -> int:
    reference = _get(candidate, "canonical_ref", {})
    value = _get(candidate, "estimated_tokens", None)
    if value is None and isinstance(reference, Mapping):
        value = reference.get("estimated_tokens", reference.get("token_cost", 1))
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 1
    return value


def _group(candidate: Any) -> str:
    reference = _get(candidate, "canonical_ref", {})
    if isinstance(reference, Mapping):
        for key in ("redundancy_group", "dedup_fingerprint", "claim_key", "content_hash"):
            value = reference.get(key)
            if isinstance(value, str) and value:
                return value
    return str(_get(candidate, "candidate_id", ""))


def _need_priorities(result: Any) -> dict[str, int]:
    plan = _get(result, "need_plan", None)
    needs = _get(plan, "needs", ()) or ()
    priorities = {"critical": 0, "high": 1, "normal": 2}
    return {str(_get(need, "need_id", "")): priorities.get(str(_get(need, "priority", "normal")), 2) for need in needs}


def _selected(candidate: Any, reason_codes: tuple[str, ...]) -> DensitySelectedCandidate:
    needs = tuple(str(item) for item in (_get(candidate, "needs", ()) or ()))
    score = _number(_get(candidate, "decision_score", _get(candidate, "retrieval_score", 0.0)))
    return DensitySelectedCandidate(
        candidate_id=str(_get(candidate, "candidate_id", "")),
        source_type=str(_get(candidate, "source_type", "unknown")),
        project_id=_get(candidate, "project_id", None),
        content_type=str(_get(candidate, "content_type", "unknown")),
        lifecycle=str(_get(candidate, "lifecycle", "ACTIVE")),
        canonical_ref=dict(_get(candidate, "canonical_ref", {})),
        needs=needs,
        redundancy_group=_group(candidate),
        estimated_tokens=_tokens(candidate),
        selection_score=round(max(0.0, min(1.0, score)), 6),
        reason_codes=reason_codes,
    )


@dataclass(frozen=True)
class _Candidate:
    source: Any
    needs: tuple[str, ...]
    group: str
    score: float
    tokens: int


class ContextDensityEngine:
    """Apply bounded, deterministic diversity after PRE-08 selection."""

    def __init__(self, policy_version: str = POLICY_VERSION):
        self.policy_version = policy_version

    def _error(self, status: str, reason: str, result: Any) -> DensityResult:
        return DensityResult(
            status=status,
            policy_version=self.policy_version,
            input_revisions=dict(_revisions(result)),
            error=reason,
        )

    def _metrics(self, selected: tuple[DensitySelectedCandidate, ...], input_count: int, priorities: Mapping[str, int]) -> tuple[dict[str, Any], dict[str, tuple[str, ...]]]:
        coverage: dict[str, list[str]] = {need_id: [] for need_id in priorities}
        for item in selected:
            for need_id in item.needs:
                if need_id in coverage:
                    coverage[need_id].append(item.candidate_id)
        required = [need_id for need_id, priority in priorities.items() if priority == 0]
        covered_required = sum(bool(coverage[need_id]) for need_id in required)
        total_tokens = sum(item.estimated_tokens for item in selected)
        useful_tokens = sum(item.estimated_tokens for item in selected if item.needs)
        unique_groups = len({item.redundancy_group for item in selected})
        critical_recall = covered_required / len(required) if required else 1.0
        useful_density = useful_tokens / total_tokens if total_tokens else 1.0
        metrics = {
            "input_candidates": input_count,
            "selected_candidates": len(selected),
            "selected_redundancy_groups": unique_groups,
            "redundancy_rate": round((len(selected) - unique_groups) / len(selected), 6) if selected else 0.0,
            "estimated_tokens": total_tokens,
            "useful_tokens": useful_tokens,
            "context_waste_ratio": round(1.0 - useful_density, 6),
            "useful_context_density": round(useful_density, 6),
            "critical_need_count": len(required),
            "covered_critical_needs": covered_required,
            "critical_need_recall": round(critical_recall, 6),
        }
        return metrics, {key: tuple(sorted(value)) for key, value in coverage.items()}

    def select(self, decision_result: Any, *, options: Optional[DensityOptions] = None) -> DensityResult:
        """Return a content-free diverse selection without changing canonical state."""
        options = options or DensityOptions()
        status = str(_get(decision_result, "status", ""))
        if status in {"STALE_INPUT", "SCOPE_ERROR", "FAILED", "INVALID_INPUT"}:
            return self._error(status if status in {"STALE_INPUT", "SCOPE_ERROR"} else "FAILED", "DECISION_INPUT_UNAVAILABLE", decision_result)
        if not isinstance(_get(decision_result, "input_revisions", {}), Mapping):
            return self._error("INVALID_INPUT", "DECISION_REVISIONS_REQUIRED", decision_result)
        candidates = tuple(_get(decision_result, "selected", ()) or ())
        priorities = _need_priorities(decision_result)
        if options.mode == "OFF":
            return DensityResult(
                status="EMPTY", policy_version=self.policy_version, input_revisions=dict(_revisions(decision_result)),
                metrics={"input_candidates": len(candidates), "selected_candidates": 0},
                telemetry={"mode": "OFF", "selected": 0},
            )
        if not candidates:
            return DensityResult(
                status="EMPTY", policy_version=self.policy_version, input_revisions=dict(_revisions(decision_result)),
                metrics={"input_candidates": 0, "selected_candidates": 0, "critical_need_recall": 1.0 if not priorities else 0.0},
                need_coverage={need_id: () for need_id in priorities},
                telemetry={"mode": options.mode, "selected": 0},
            )

        normalized = []
        seen: set[str] = set()
        omitted: dict[str, str] = {}
        for candidate in candidates:
            candidate_id = str(_get(candidate, "candidate_id", ""))
            if not candidate_id or candidate_id in seen:
                if candidate_id:
                    omitted[candidate_id] = "DUPLICATE_CANDIDATE"
                continue
            seen.add(candidate_id)
            needs = tuple(str(item) for item in (_get(candidate, "needs", ()) or ()))
            normalized.append(_Candidate(candidate, needs, _group(candidate), _number(_get(candidate, "decision_score", 0.0)), _tokens(candidate)))

        mandatory = [item for item in normalized if any(priorities.get(need_id, 2) == 0 for need_id in item.needs)]
        if len(mandatory) > options.max_selected:
            return self._error("FAILED", "MANDATORY_CONTEXT_UNSATISFIED", decision_result)

        mandatory.sort(key=lambda item: (-item.score, item.group, str(_get(item.source, "candidate_id", ""))))
        optional = [item for item in normalized if item not in mandatory]
        optional.sort(key=lambda item: (-item.score, item.group, str(_get(item.source, "candidate_id", ""))))
        chosen: list[_Candidate] = []
        groups: set[str] = set()
        covered: set[str] = set()
        for item in mandatory:
            chosen.append(item)
            groups.add(item.group)
            covered.update(item.needs)
        for item in optional:
            candidate_id = str(_get(item.source, "candidate_id", ""))
            if len(chosen) >= options.max_selected:
                omitted[candidate_id] = "DENSITY_BUDGET"
                continue
            adds_need = bool(set(item.needs) - covered)
            if item.group in groups and not adds_need:
                omitted[candidate_id] = "REDUNDANT_CONTEXT"
                continue
            chosen.append(item)
            groups.add(item.group)
            covered.update(item.needs)

        result_selected = tuple(
            _selected(item.source, ("MANDATORY_NEED",) if item in mandatory else ("DIVERSITY_SELECTED",)) for item in chosen
        )
        metrics, coverage = self._metrics(result_selected, len(normalized), priorities)
        degraded = ("REDUNDANT_CONTEXT_OMITTED",) if any(reason == "REDUNDANT_CONTEXT" for reason in omitted.values()) else ()
        result_status = "DEGRADED" if degraded else "SUCCESS"
        return DensityResult(
            status=result_status,
            policy_version=self.policy_version,
            input_revisions=dict(_revisions(decision_result)),
            selected=result_selected,
            omitted=omitted,
            metrics=metrics,
            need_coverage=coverage,
            degraded_reasons=degraded,
            telemetry={
                "mode": options.mode,
                "input_candidates": len(normalized),
                "selected": len(result_selected),
                "omitted": len(omitted),
                "diversity_lambda": float(options.diversity_lambda),
            },
        )
