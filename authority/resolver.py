"""Read-only Phase 18 authority resolver."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, Optional

from .adapters import AuthorityEvidenceAdapter, AuthorityEvidenceError, AuthorityStaleInput
from .cache import AuthorityCache
from .config import AuthorityConfig, AuthorityConfigError
from .models import AuthorityOptions, ResolutionResult
from .policy import AuthorityPolicyError, resolve_metadata


class AuthorityScopeError(ValueError):
    """Router scope and trusted authority scope are not identical."""


class AuthorityInputError(ValueError):
    """Task/Router input does not meet the Phase 18 hand-off contract."""


class AuthorityResolver:
    """Resolve authority without retrieval or writes to canonical authorities."""

    def __init__(self, vault_path: str | Path):
        self.vault_path = Path(vault_path)
        self.evidence = AuthorityEvidenceAdapter(self.vault_path)
        self.cache = AuthorityCache(self.vault_path)

    @staticmethod
    def _result(
        status: str,
        policy_version: str,
        *,
        revisions: Optional[Mapping[str, Any]] = None,
        error: Optional[str] = None,
        degraded: tuple[str, ...] = (),
        telemetry: Optional[Mapping[str, Any]] = None,
    ) -> ResolutionResult:
        return ResolutionResult(
            status=status,
            policy_version=policy_version,
            input_revisions=dict(revisions or {}),
            degraded_reasons=degraded,
            error=error,
            telemetry=dict(telemetry or {}),
        )

    @staticmethod
    def _scope_from_plan(router_result: Any) -> tuple[str, tuple[str, ...], bool, str]:
        plan = router_result.plan
        if plan is None:
            raise AuthorityInputError("RouterResult requires a RetrievalPlan")
        scope = plan.scope
        return scope.mode, tuple(scope.project_ids), scope.include_global, plan.history_mode

    @staticmethod
    def _validate_task_state(task_state: Any) -> None:
        try:
            task = task_state.task
            state = task_state.state
            project = task.project
        except AttributeError as exc:
            raise AuthorityInputError("TaskStateContext is required") from exc
        if project.status not in {"resolved", "unresolved", "archived"}:
            raise AuthorityInputError("Task project resolution is invalid")
        if project.project_id is not None and state.project_id != project.project_id:
            raise AuthorityInputError("Task project and StateSnapshot project must match")

    @classmethod
    def _validate_scope(cls, task_state: Any, router_result: Any, options: AuthorityOptions) -> None:
        mode, project_ids, include_global, history_mode = cls._scope_from_plan(router_result)
        if (mode, project_ids, include_global, history_mode) != (
            options.scope_mode,
            options.selected_project_ids if options.scope_mode == "SELECTED_PROJECTS" else (
                (task_state.task.project.project_id,) if options.scope_mode == "CURRENT_PROJECT" else ()
            ),
            options.include_global,
            options.history_mode,
        ):
            raise AuthorityScopeError("Router scope does not match trusted authority options")
        task_project = task_state.task.project.project_id
        if mode == "CURRENT_PROJECT":
            if task_project is None or project_ids != (task_project,):
                raise AuthorityScopeError("CURRENT_PROJECT requires the resolved task project")
        elif mode == "GLOBAL_ONLY":
            if project_ids:
                raise AuthorityScopeError("GLOBAL_ONLY cannot include project candidates")
        elif mode == "SELECTED_PROJECTS":
            if task_project is None or task_project not in project_ids:
                raise AuthorityScopeError("SELECTED_PROJECTS must explicitly include the task project")
        else:
            raise AuthorityScopeError(f"Unsupported Router scope: {mode}")

        for candidate in router_result.candidates:
            if candidate.project_id is None:
                if not include_global:
                    raise AuthorityScopeError("Global candidate is outside trusted authority scope")
            elif candidate.project_id not in project_ids:
                raise AuthorityScopeError("Candidate is outside trusted authority project scope")

    @staticmethod
    def _cache_key(router_result: Any, policy_version: str) -> str:
        plan = router_result.plan
        fingerprint = getattr(plan, "fingerprint", "")
        if not isinstance(fingerprint, str) or not fingerprint:
            raise AuthorityInputError("Router plan fingerprint is invalid")
        digest = hashlib.sha256(f"{policy_version}:{fingerprint}".encode("utf-8")).hexdigest()
        return f"authority:{digest}"

    @staticmethod
    def _router_lineage(router_result: Any) -> Mapping[str, Any]:
        """Content-free upstream lineage needed by a downstream compiler."""
        plan = router_result.plan
        if plan is None:
            return {}
        return {
            "route_id": plan.route_id,
            "route_profile": plan.route_profile,
            "router_config_version": plan.router_config_version,
        }

    @staticmethod
    def _cached_result(document: Mapping[str, Any]) -> Optional[ResolutionResult]:
        """Only accept strictly content-free cache output.

        Cached payloads are never used as source evidence; canonical snapshots
        have already been validated before this conversion is attempted.
        """
        from .serialization import resolution_result_from_dict

        try:
            return resolution_result_from_dict(document)
        except (TypeError, ValueError):
            return None

    def resolve(
        self,
        task_state: Any,
        router_result: Any,
        options: AuthorityOptions | None = None,
    ) -> ResolutionResult:
        options = options or AuthorityOptions()
        try:
            config = AuthorityConfig.load(self.vault_path)
        except AuthorityConfigError as exc:
            return self._result("FAILED", "authority-v1", error=str(exc))

        if options.mode == "OFF":
            return self._result(
                "EMPTY",
                config.policy_version,
                degraded=("authority_off",),
                telemetry={"mode": "OFF", "cache_hit": False},
            )

        try:
            self._validate_task_state(task_state)
            if router_result.status == "STALE_INPUT":
                return self._result("STALE_INPUT", config.policy_version, error="Router input is stale")
            if router_result.status not in {"SUCCESS", "DEGRADED", "EMPTY"}:
                raise AuthorityInputError(f"RouterResult cannot be resolved: {router_result.status}")
            if router_result.telemetry.get("mode") not in {None, "SHADOW"}:
                raise AuthorityInputError("Authority accepts only a SHADOW RouterResult")
            self._validate_scope(task_state, router_result, options)
            snapshot = self.evidence.snapshot(router_result)
        except AuthorityScopeError as exc:
            return self._result("SCOPE_ERROR", config.policy_version, error=str(exc))
        except AuthorityStaleInput as exc:
            return self._result("STALE_INPUT", config.policy_version, error=str(exc))
        except (AuthorityInputError, AttributeError, TypeError, ValueError) as exc:
            return self._result("INVALID_INPUT", config.policy_version, error=str(exc))
        except AuthorityEvidenceError as exc:
            return self._result("FAILED", config.policy_version, error=str(exc))

        cache_key = self._cache_key(router_result, config.policy_version)
        if config.cache_enabled:
            cached = self._cached_result(self.cache.load(cache_key, snapshot.revisions) or {})
            if cached is not None:
                return ResolutionResult(
                    status=cached.status,
                    policy_version=cached.policy_version,
                    input_revisions=cached.input_revisions,
                    candidates=cached.candidates,
                    conflict_sets=cached.conflict_sets,
                    ledger=cached.ledger,
                    degraded_reasons=cached.degraded_reasons,
                    error=cached.error,
                    telemetry={
                        **cached.telemetry,
                        **self._router_lineage(router_result),
                        "mode": "SHADOW",
                        "cache_hit": True,
                    },
                )

        try:
            candidates, conflicts, ledger = resolve_metadata(snapshot)
        except AuthorityPolicyError as exc:
            return self._result("FAILED", config.policy_version, revisions=snapshot.revisions, error=str(exc))
        if not self.evidence.inputs_current(snapshot):
            return self._result(
                "STALE_INPUT",
                config.policy_version,
                revisions=snapshot.revisions,
                error="Canonical source changed during authority resolution",
            )

        degraded = tuple(router_result.degraded_reasons)
        status = "EMPTY" if not candidates else ("DEGRADED" if degraded else "SUCCESS")
        result = ResolutionResult(
            status=status,
            policy_version=config.policy_version,
            input_revisions=snapshot.revisions,
            candidates=candidates,
            conflict_sets=conflicts,
            ledger=ledger,
            degraded_reasons=degraded,
            telemetry={
                **self._router_lineage(router_result),
                "mode": "SHADOW",
                "cache_hit": False,
                "candidate_count": len(candidates),
                "conflict_count": len(conflicts),
                "retrieval_signal_influence": "excluded",
            },
        )
        if config.cache_enabled:
            try:
                self.cache.store(cache_key, snapshot.revisions, result.to_dict())
            except OSError:
                # Cache is derived state; failure must not change canonical truth.
                result = ResolutionResult(
                    status="DEGRADED" if result.status == "SUCCESS" else result.status,
                    policy_version=result.policy_version,
                    input_revisions=result.input_revisions,
                    candidates=result.candidates,
                    conflict_sets=result.conflict_sets,
                    ledger=result.ledger,
                    degraded_reasons=tuple(sorted(set(result.degraded_reasons + ("authority_cache_write_failed",)))),
                    telemetry=result.telemetry,
                )
        return result
