"""Phase 19 compiler: constrained, deterministic, downstream-only context output."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Optional

from .adapters import CompilerEvidenceAdapter, CompilerEvidenceError, CompilerScopeError, CompilerStaleInput
from .cache import CompilerCache
from .config import CompilerConfig, CompilerConfigError
from .models import (
    COMPILER_VERSION,
    BudgetContract,
    CompilationOptions,
    CompilationRequest,
    ContextBundle,
    OmittedItem,
)
from .planner import choose, selection_reason
from .renderer import build_sections, context_item_from_draft, render_bundle, render_fragment, render_task
from .tokenizer import ConservativeTokenEstimator, TokenEstimator
from .utility import build_drafts, profile_from_input


class ContextCompilerV2:
    """Compile resolved candidates without changing V1, routing, or authority."""

    def __init__(self, vault_path: str | Path, *, estimator: Optional[TokenEstimator] = None):
        self.vault_path = Path(vault_path)
        self.evidence = CompilerEvidenceAdapter(self.vault_path)
        self.cache = CompilerCache(self.vault_path)
        self.estimator = estimator or ConservativeTokenEstimator()

    @staticmethod
    def _profile(request: CompilationRequest) -> str:
        return profile_from_input(request.task_state, request.resolution_result, request.compiler_profile)

    @staticmethod
    def _identifier(request: CompilationRequest, profile: str, policy_version: str) -> str:
        task_id = getattr(request.task_state.task, "task_id", "unknown")
        revisions = request.resolution_result.input_revisions
        payload = json.dumps(
            {
                "task": task_id,
                "revisions": revisions,
                "profile": profile,
                "budget": request.budget.to_dict(),
                "policy": policy_version,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return "ctx_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _result(
        status: str,
        compilation_id: str,
        profile: str,
        request: CompilationRequest,
        *,
        revisions: Optional[Mapping[str, Any]] = None,
        error: Optional[str] = None,
        warnings: tuple[str, ...] = (),
        telemetry: Optional[Mapping[str, Any]] = None,
        omitted: tuple[OmittedItem, ...] = (),
    ) -> ContextBundle:
        return ContextBundle(
            status=status,
            compilation_id=compilation_id,
            task_id=getattr(request.task_state.task, "task_id", None),
            resolution_id=request.resolution_result.telemetry.get("resolution_id") if isinstance(request.resolution_result.telemetry, Mapping) else None,
            input_revisions=dict(revisions or request.resolution_result.input_revisions),
            compiler_version=COMPILER_VERSION,
            compiler_profile=profile,
            budget=request.budget.to_dict(),
            omitted=omitted,
            warnings=warnings,
            error=error,
            telemetry=dict(telemetry or {}),
        )

    @staticmethod
    def _validate_upstream(request: CompilationRequest) -> None:
        result = request.resolution_result
        if result.status == "STALE_INPUT":
            raise CompilerStaleInput("ResolutionResult input is stale")
        if result.status not in {"SUCCESS", "DEGRADED", "EMPTY"}:
            raise CompilerEvidenceError(f"ResolutionResult cannot be compiled: {result.status}")
        mode = result.telemetry.get("mode") if isinstance(result.telemetry, Mapping) else None
        if mode not in {None, "SHADOW"}:
            raise CompilerEvidenceError("Compiler accepts only SHADOW authority output")

    @staticmethod
    def _cache_key(compilation_id: str) -> str:
        return f"compiler-v2:{compilation_id}"

    def compile(self, request: CompilationRequest, options: Optional[CompilationOptions] = None) -> ContextBundle:
        options = options or CompilationOptions()
        provisional_profile = "general"
        try:
            provisional_profile = self._profile(request)
            config = CompilerConfig.load(self.vault_path)
            compilation_id = self._identifier(request, provisional_profile, config.policy_version)
        except (CompilerConfigError, ValueError, TypeError) as exc:
            return self._result("FAILED", "ctx_invalid", provisional_profile, request, error=str(exc))
        if options.mode == "OFF" or config.default_mode == "OFF":
            return self._result(
                "EMPTY",
                compilation_id,
                provisional_profile,
                request,
                warnings=("compiler_off",),
                telemetry={"mode": "OFF", "cache_hit": False},
            )
        try:
            self._validate_upstream(request)
            snapshot = self.evidence.snapshot(request.task_state, request.resolution_result)
        except CompilerScopeError as exc:
            return self._result("SCOPE_ERROR", compilation_id, provisional_profile, request, error=str(exc))
        except CompilerStaleInput as exc:
            return self._result("STALE_INPUT", compilation_id, provisional_profile, request, error=str(exc))
        except CompilerEvidenceError as exc:
            return self._result("FAILED", compilation_id, provisional_profile, request, error=str(exc))
        except (AttributeError, TypeError, ValueError) as exc:
            return self._result("INVALID_INPUT", compilation_id, provisional_profile, request, error=str(exc))

        cache_hit = False
        if config.cache_enabled and options.cache_enabled:
            cache_hit = self.cache.load(self._cache_key(compilation_id), snapshot.revisions) is not None
        base_estimate = self.estimator.estimate(render_bundle(request.task_state, ()))
        if base_estimate.byte_count > request.budget.hard_byte_limit or base_estimate.count > request.budget.usable_tokens:
            return self._result(
                "INSUFFICIENT_BUDGET",
                compilation_id,
                provisional_profile,
                request,
                revisions=snapshot.revisions,
                error="Task identity exceeds the usable context budget",
                warnings=("mandatory_task_overflow",),
                telemetry={"mode": "SHADOW", "cache_hit": cache_hit, "base_tokens": base_estimate.count},
            )
        drafts = build_drafts(snapshot.candidates, provisional_profile, self.estimator, render_fragment)
        plan = choose(drafts, request.budget, allow_history=options.allow_history, base_cost=base_estimate.count)
        if plan.mandatory_cost > request.budget.usable_tokens:
            return self._result(
                "INSUFFICIENT_BUDGET",
                compilation_id,
                provisional_profile,
                request,
                revisions=snapshot.revisions,
                error="Mandatory context exceeds the usable context budget",
                warnings=("mandatory_context_not_silently_truncated",),
                omitted=plan.omitted,
                telemetry={
                    "mode": "SHADOW",
                    "cache_hit": cache_hit,
                    "base_tokens": base_estimate.count,
                    "mandatory_tokens": plan.mandatory_cost,
                },
            )

        selected_drafts = list(plan.selected)
        omissions = list(plan.omitted)
        # A bounded final pass removes only optional entries if renderer framing
        # expands more than the conservative per-item pre-estimates anticipated.
        for _ in range(config.max_rebalance_iterations + 1):
            selected_items = tuple(
                context_item_from_draft(draft, selection_reason(draft), draft.utility.estimated_cost)
                for draft in selected_drafts
            )
            rendered = render_bundle(request.task_state, selected_items)
            final_estimate = self.estimator.estimate(rendered)
            if final_estimate.count <= request.budget.usable_tokens and final_estimate.byte_count <= request.budget.hard_byte_limit:
                break
            optional = [draft for draft in selected_drafts if not draft.mandatory]
            if not optional:
                return self._result(
                    "INSUFFICIENT_BUDGET",
                    compilation_id,
                    provisional_profile,
                    request,
                    revisions=snapshot.revisions,
                    error="Rendered mandatory context exceeds budget; it was not truncated",
                    warnings=("mandatory_context_not_silently_truncated",),
                    omitted=tuple(sorted(omissions, key=lambda item: item.candidate_id)),
                    telemetry={"mode": "SHADOW", "cache_hit": cache_hit, "rendered_tokens": final_estimate.count},
                )
            remove = max(optional, key=lambda draft: (draft.tier, draft.utility.estimated_cost.count, draft.evidence.resolution.candidate_id))
            selected_drafts.remove(remove)
            omissions.append(OmittedItem(remove.evidence.resolution.candidate_id, "budget_exhausted", remove.role, remove.tier))
        else:
            return self._result(
                "FAILED",
                compilation_id,
                provisional_profile,
                request,
                revisions=snapshot.revisions,
                error="Bounded rebalance could not verify the final budget",
                omitted=tuple(sorted(omissions, key=lambda item: item.candidate_id)),
            )

        if not self.evidence.inputs_current(snapshot):
            return self._result(
                "STALE_INPUT",
                compilation_id,
                provisional_profile,
                request,
                revisions=snapshot.revisions,
                error="Canonical source changed during compilation",
            )
        warnings = tuple(
            sorted(
                {"contains_unresolved_context" if item.evidence.resolution.status in {"CONTESTED", "UNRESOLVED"} else ""
                 for item in selected_drafts}
                - {""}
            )
        )
        status = "EMPTY" if not selected_items else ("DEGRADED" if request.resolution_result.degraded_reasons else "SUCCESS")
        result = ContextBundle(
            status=status,
            compilation_id=compilation_id,
            task_id=request.task_state.task.task_id,
            resolution_id=request.resolution_result.telemetry.get("resolution_id") if isinstance(request.resolution_result.telemetry, Mapping) else None,
            input_revisions=snapshot.revisions,
            compiler_version=COMPILER_VERSION,
            compiler_profile=provisional_profile,
            budget={
                **request.budget.to_dict(),
                "estimated_tokens": final_estimate.count,
                "remaining_tokens": request.budget.max_context_tokens - final_estimate.count,
                "token_estimator": final_estimate.to_dict(),
            },
            selected=selected_items,
            omitted=tuple(sorted(omissions, key=lambda item: item.candidate_id)),
            sections=build_sections(selected_items),
            warnings=warnings,
            rendered_context=rendered,
            telemetry={
                "mode": "SHADOW",
                "cache_hit": cache_hit,
                "route_id": request.resolution_result.telemetry.get("route_id"),
                "router_profile": request.resolution_result.telemetry.get("route_profile"),
                "router_config_version": request.resolution_result.telemetry.get("router_config_version"),
                "authority_policy_version": request.resolution_result.policy_version,
                "compiler_policy_version": config.policy_version,
                "candidate_count": len(snapshot.candidates),
                "selected_count": len(selected_items),
                "canonical_write": False,
                "selection_method": "tiered_deterministic",
            },
        )
        if config.cache_enabled and options.cache_enabled:
            try:
                self.cache.store(self._cache_key(compilation_id), snapshot.revisions, result.manifest_dict())
            except (OSError, ValueError):
                result = ContextBundle(
                    **{
                        **result.__dict__,
                        "status": "DEGRADED" if result.status == "SUCCESS" else result.status,
                        "warnings": tuple(sorted(set(result.warnings + ("compiler_cache_write_failed",)))),
                    }
                )
        return result
