"""The Phase 17 read-only task-aware Context Router."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Optional

from .adapters import GraphAdapter, MemoryAdapter, RawCandidate, StateAdapter, infer_memory_scope
from .cache import RouterCache
from .config import RouterConfig, RouterConfigError
from .models import Candidate, RetrievalPlan, RetrievalQuery, RouteScope, RouterResult, RoutingOptions
from .planner import FALLBACK_TIER, STRICT_TIER, build_plan
from .policy import ScopePolicyError, lifecycle_allowed, resolve_history_mode, resolve_profile, resolve_scope


class StaleTaskStateError(RuntimeError):
    """The caller-provided Phase 16 state snapshot no longer matches state."""


class ContextRouter:
    """Route one Phase 16 TaskStateContext without mutating any authority."""

    def __init__(self, vault_path: str | Path):
        self.vault_path = Path(vault_path)
        self.memory = MemoryAdapter(self.vault_path)
        self.state = StateAdapter(self.vault_path)
        self.graph = GraphAdapter(self.vault_path)
        self.cache = RouterCache(self.vault_path)

    @staticmethod
    def _error(status: str, message: str, plan: Optional[RetrievalPlan] = None) -> RouterResult:
        return RouterResult(status=status, plan=plan, input_revisions={}, error=message)

    @staticmethod
    def _state_revisions(states: Mapping[str, Any]) -> dict[str, Any]:
        return {
            project_id: {"status": state.status, "revision": state.state_revision}
            for project_id, state in sorted(states.items())
        }

    def _validate_state_scope(self, task_state, scope: RouteScope, options: RoutingOptions) -> tuple[dict[str, Any], list[str]]:
        task = task_state.task
        primary = task_state.state
        if scope.mode != "GLOBAL_ONLY":
            task_project = task.project.project_id
            if task_project not in scope.project_ids or primary.project_id != task_project:
                raise ScopePolicyError("Task project and StateSnapshot project must match")
        states = self.state.resolve_projects(scope)
        degraded: list[str] = []
        for project_id, state in states.items():
            reason = self.state.unavailable_reason(
                state, allow_archived_history=options.allow_archived_history
            )
            if reason:
                if reason == "state_project_archived":
                    raise ScopePolicyError(f"Archived project requires allow_archived_history: {project_id}")
                if reason == "state_project_unknown":
                    raise ScopePolicyError(f"Unknown registered project: {project_id}")
                raise RuntimeError(f"Canonical state unavailable for {project_id}: {reason}")
            degraded_reason = self.state.degraded_reason(state)
            if degraded_reason:
                degraded.append(f"{degraded_reason}:{project_id}")
        if scope.mode != "GLOBAL_ONLY":
            current = states[task.project.project_id]
            if current.status != primary.status or current.state_revision != primary.state_revision:
                raise StaleTaskStateError(
                    "TaskStateContext state snapshot changed before routing"
                )
        return states, degraded

    @staticmethod
    def _candidate_from_raw(raw: RawCandidate, data: Mapping[str, Any]) -> Candidate:
        return Candidate(
            candidate_id=raw.candidate_id,
            source_type=raw.source_type,
            project_id=raw.project_id,
            content_type=raw.content_type,
            lifecycle=raw.lifecycle,
            source_revision=raw.source_revision,
            canonical_ref=raw.canonical_ref,
            retrieved_by=tuple(sorted(data["queries"])),
            match_signals=tuple(sorted(data["signals"])),
            retrieval_score=max(data["scores"]),
        )

    @classmethod
    def _normalize(cls, candidates: list[RawCandidate], budget: Mapping[str, int]) -> tuple[Candidate, ...]:
        merged: dict[str, dict[str, Any]] = {}
        for raw in candidates:
            entry = merged.setdefault(
                raw.candidate_id,
                {"raw": raw, "queries": set(), "signals": set(), "scores": []},
            )
            entry["queries"].add(raw.query_id)
            entry["signals"].add(raw.signal)
            entry["scores"].append(raw.score)
        by_source: dict[str, list[Candidate]] = defaultdict(list)
        for entry in merged.values():
            candidate = cls._candidate_from_raw(entry["raw"], entry)
            by_source[candidate.source_type].append(candidate)
        bounded: list[Candidate] = []
        for source, values in sorted(by_source.items()):
            values.sort(key=lambda candidate: (-candidate.retrieval_score, candidate.candidate_id))
            bounded.extend(values[: budget.get(source, 0)])
        return tuple(sorted(bounded, key=lambda candidate: (-candidate.retrieval_score, candidate.source_type, candidate.candidate_id)))

    def _graph_candidates(
        self,
        graph_query: RetrievalQuery,
        plan: RetrievalPlan,
        snapshot: tuple[Mapping[str, Any], ...],
        revision: int,
        config: RouterConfig,
    ) -> tuple[list[RawCandidate], Optional[str]]:
        memory_ids, reason = self.graph.expand(
            graph_query,
            plan.scope,
            revision,
            max_hops=config.max_graph_hops,
        )
        if reason:
            return [], reason
        profile = config.profiles[plan.route_profile]
        index = self.memory.by_id(snapshot)
        output: list[RawCandidate] = []
        for memory_id in sorted(memory_ids):
            memory = index.get(memory_id)
            if memory is None:
                continue
            if memory.get("type") not in profile.memory_types:
                continue
            if not self.memory.allowed(
                memory,
                plan.scope,
                plan.history_mode,
                include_global=plan.scope.include_global,
            ):
                continue
            if not lifecycle_allowed(str(memory.get("status", "active")), plan.history_mode):
                continue
            memory_scope, _, project_id = infer_memory_scope(dict(memory))
            output.append(
                RawCandidate(
                    candidate_id=memory_id,
                    source_type="memory",
                    project_id=project_id if memory_scope == "project" else None,
                    content_type=str(memory.get("type", "unknown")),
                    lifecycle=str(memory.get("status", "active")),
                    source_revision=revision,
                    canonical_ref={"authority": "memory", "memory_id": memory_id},
                    query_id=graph_query.query_id,
                    signal="graph_relation",
                    score=0.58,
                )
            )
        return output, None

    @staticmethod
    def _cached_result(document: Mapping[str, Any]) -> Optional[RouterResult]:
        try:
            plan_document = document.get("plan")
            if not isinstance(plan_document, Mapping):
                return None
            scope_document = plan_document["scope"]
            scope = RouteScope(
                mode=scope_document["mode"],
                project_ids=tuple(scope_document["project_ids"]),
                include_global=bool(scope_document["include_global"]),
            )
            queries = tuple(
                RetrievalQuery(
                    query_id=query["query_id"],
                    source=query["source"],
                    strategy=query["strategy"],
                    terms=tuple(query.get("terms", ())),
                    memory_types=tuple(query.get("memory_types", ())),
                    pass_name=query.get("pass", "strict"),
                )
                for query in plan_document["queries"]
            )
            plan = RetrievalPlan(
                route_id=plan_document["route_id"],
                task_id=plan_document["task_id"],
                route_profile=plan_document["route_profile"],
                scope=scope,
                history_mode=plan_document["history_mode"],
                queries=queries,
                candidate_budget=plan_document["candidate_budget"],
                router_config_version=plan_document["router_config_version"],
                fingerprint=plan_document["fingerprint"],
            )
            candidates = tuple(
                Candidate(
                    candidate_id=item["candidate_id"],
                    source_type=item["source_type"],
                    project_id=item.get("project_id"),
                    content_type=item["content_type"],
                    lifecycle=item["lifecycle"],
                    source_revision=item.get("source_revision"),
                    canonical_ref=item["canonical_ref"],
                    retrieved_by=tuple(item["retrieved_by"]),
                    match_signals=tuple(item["match_signals"]),
                    retrieval_score=item["retrieval_score"],
                )
                for item in document.get("candidates", ())
            )
            telemetry = dict(document.get("telemetry", {}))
            telemetry["cache_hit"] = True
            return RouterResult(
                status=document["status"],
                plan=plan,
                input_revisions=document["input_revisions"],
                candidates=candidates,
                degraded_reasons=tuple(document.get("degraded_reasons", ())),
                error=document.get("error"),
                telemetry=telemetry,
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _inputs_current(self, states: Mapping[str, Any], memory_revision: int) -> bool:
        try:
            if self.memory.revision() != memory_revision:
                return False
            for project_id, prior in states.items():
                current = self.state.resolver.resolve(project_id)
                if current.status != prior.status or current.state_revision != prior.state_revision:
                    return False
        except Exception:
            return False
        return True

    def _route(self, task_state, options: RoutingOptions, attempt: int) -> RouterResult:
        try:
            config = RouterConfig.load(self.vault_path)
            scope = resolve_scope(task_state.task, options)
            history_mode = resolve_history_mode(task_state.task, options)
            profile = resolve_profile(task_state.task)
            # Profiles can be stricter than a trusted caller, never broader.
            scope = replace(
                scope,
                include_global=scope.include_global and config.profiles[profile].allow_global,
            )
            plan = build_plan(task_state.task, scope, history_mode, config)
        except RouterConfigError as exc:
            return self._error("FAILED", str(exc))
        except ScopePolicyError as exc:
            return self._error("SCOPE_ERROR", str(exc))
        except Exception as exc:
            return self._error("INVALID_TASK", str(exc))

        if options.mode == "OFF":
            return RouterResult(
                status="EMPTY",
                plan=plan,
                input_revisions={},
                degraded_reasons=("router_off",),
                telemetry={"mode": "OFF", "cache_hit": False},
            )

        try:
            states, degraded = self._validate_state_scope(task_state, scope, options)
            memory_revision, snapshot = self.memory.snapshot()
        except ScopePolicyError as exc:
            return self._error("SCOPE_ERROR", str(exc), plan)
        except StaleTaskStateError as exc:
            return self._error("STALE_INPUT", str(exc), plan)
        except Exception as exc:
            return self._error("FAILED", str(exc), plan)

        revisions = {
            "memory": memory_revision,
            "state": self._state_revisions(states),
            "graph": memory_revision,
        }
        if config.cache_enabled:
            cached = self._cached_result(self.cache.load(plan.fingerprint, revisions) or {})
            if cached is not None:
                return cached

        raw_candidates: list[RawCandidate] = []
        strict_memory = [query for query in plan.queries if query.source == "memory" and query.pass_name == STRICT_TIER]
        for query in strict_memory:
            raw_candidates.extend(
                self.memory.retrieve(
                    snapshot,
                    memory_revision,
                    query,
                    scope,
                    history_mode,
                    include_global=scope.mode == "GLOBAL_ONLY",
                )
            )
        for query in (query for query in plan.queries if query.source == "state"):
            raw_candidates.extend(self.state.retrieve(states, query))

        strict_memory_count = sum(candidate.source_type == "memory" for candidate in raw_candidates)
        if strict_memory_count < config.strict_min_memory_candidates:
            # Re-run the same high-confidence queries against the permitted
            # global tier only after the same-project strict pass is sparse.
            if scope.include_global and scope.mode != "GLOBAL_ONLY":
                for query in strict_memory:
                    raw_candidates.extend(
                        self.memory.retrieve(
                            snapshot,
                            memory_revision,
                            query,
                            scope,
                            history_mode,
                            include_global=True,
                        )
                    )
            for query in (
                query for query in plan.queries if query.source == "memory" and query.pass_name == FALLBACK_TIER
            ):
                raw_candidates.extend(
                    self.memory.retrieve(
                        snapshot,
                        memory_revision,
                        query,
                        scope,
                        history_mode,
                        include_global=scope.include_global,
                    )
                )
            for query in (query for query in plan.queries if query.source == "graph"):
                graph_candidates, graph_reason = self._graph_candidates(
                    query, plan, snapshot, memory_revision, config
                )
                raw_candidates.extend(graph_candidates)
                if graph_reason:
                    degraded.append(graph_reason)

        candidates = self._normalize(raw_candidates, plan.candidate_budget)
        if not self._inputs_current(states, memory_revision):
            if attempt < config.retry_on_revision_change:
                return self._route(task_state, options, attempt + 1)
            return RouterResult(
                status="STALE_INPUT",
                plan=plan,
                input_revisions=revisions,
                degraded_reasons=tuple(degraded),
                error="Canonical source changed during routing",
                telemetry={"mode": options.mode, "attempt": attempt + 1, "cache_hit": False},
            )

        status = "EMPTY" if not candidates else ("DEGRADED" if degraded else "SUCCESS")
        telemetry = {
            "mode": options.mode,
            "attempt": attempt + 1,
            "cache_hit": False,
            "queries_generated": len(plan.queries),
            "candidates_raw": len(raw_candidates),
            "candidates_final": len(candidates),
            "memory_candidates": sum(candidate.source_type == "memory" for candidate in candidates),
            "state_candidates": sum(candidate.source_type == "state" for candidate in candidates),
        }
        result = RouterResult(
            status=status,
            plan=plan,
            input_revisions=revisions,
            candidates=candidates,
            degraded_reasons=tuple(sorted(set(degraded))),
            telemetry=telemetry,
        )
        if config.cache_enabled:
            self.cache.store(plan.fingerprint, revisions, result.to_dict())
        return result

    def route(self, task_state, options: RoutingOptions | None = None) -> RouterResult:
        """Create a plan and candidate references without changing any canonical record."""
        return self._route(task_state, options or RoutingOptions(), attempt=0)
