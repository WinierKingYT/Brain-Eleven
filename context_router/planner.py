"""Offline deterministic query decomposition for Phase 17."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Iterable

from .config import ProfileConfig, RouterConfig
from .models import RetrievalPlan, RetrievalQuery, RouteScope
from .policy import resolve_profile


_MEMORY_ID = re.compile(r"\bmem_[A-Za-z0-9_-]+\b")
_ARTIFACT = re.compile(r"(?<!\w)(?:[A-Za-z0-9_.-]+[\\/])+(?:[A-Za-z0-9_.-]+)(?!\w)")
_TOKEN = re.compile(r"[^\W_]+(?:[-_][^\W_]+)*", re.UNICODE)
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "bu", "bir", "için", "ile", "de", "da", "the", "to", "of", "in",
        "ve", "veya", "mi", "mı", "mu", "mü", "olarak", "şu", "that", "this", "please",
    }
)
_ALIASES = {
    "db": ("database",),
    "sqlite": ("sqlite", "database"),
    "markdown": ("markdown", "filesystem"),
    "quick-note": ("quick note",),
}
STRICT_TIER = "strict"
FALLBACK_TIER = "fallback"


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = str(value or "").strip()
        if value and value.casefold() not in seen:
            result.append(value)
            seen.add(value.casefold())
    return tuple(result)


def _concepts(raw_request: str) -> tuple[str, ...]:
    tokens = [token for token in _TOKEN.findall(raw_request) if len(token) > 2]
    return _unique(token for token in tokens if token.casefold() not in _STOPWORDS)[:12]


def _aliases(values: Iterable[str]) -> tuple[str, ...]:
    expanded: list[str] = []
    for value in values:
        expanded.extend(_ALIASES.get(value.casefold(), ()))
    return _unique(expanded)


def _fingerprint(
    task,
    profile: str,
    scope: RouteScope,
    history_mode: str,
    config_version: int,
) -> str:
    """Fingerprint all task inputs that can affect planning or cache output."""
    document = {
        "task_id": task.task_id,
        "raw_request": task.raw_request,
        "entities": list(getattr(task, "entities", ())),
        "canonical_domains": list(getattr(task, "canonical_domains", ())),
        "discovered_domains": list(getattr(task, "discovered_domains", ())),
        "continuation_of": getattr(task, "continuation_of", None),
        "profile": profile,
        "scope": scope.to_dict(),
        "history_mode": history_mode,
        "config_version": config_version,
    }
    raw = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_plan(task, scope: RouteScope, history_mode: str, config: RouterConfig) -> RetrievalPlan:
    """Produce a stable plan. Fallback queries are listed before execution."""
    profile = resolve_profile(task)
    profile_config: ProfileConfig = config.profiles[profile]
    queries: list[RetrievalQuery] = []

    def add(source: str, strategy: str, terms: tuple[str, ...] = (), query_tier: str = STRICT_TIER) -> None:
        if len(queries) >= config.max_queries_per_route:
            return
        query_id = f"q{len(queries) + 1:02d}"
        queries.append(
            RetrievalQuery(
                query_id=query_id,
                source=source,
                strategy=strategy,
                terms=terms,
                memory_types=profile_config.memory_types if source == "memory" else (),
                pass_name=query_tier,
            )
        )

    direct_ids = _unique(_MEMORY_ID.findall(task.raw_request))
    for memory_id in direct_ids:
        add("memory", "DIRECT_ID", (memory_id,))
    for artifact in _unique(_ARTIFACT.findall(task.raw_request)):
        add("memory", "ARTIFACT", (artifact,))
    for entity in _unique(getattr(task, "entities", ())):
        add("memory", "EXACT_ENTITY", (entity,))
    concepts = _concepts(task.raw_request)
    if concepts:
        add("memory", "CONCEPT", concepts)
    domains = _unique((*getattr(task, "canonical_domains", ()), *getattr(task, "discovered_domains", ())))
    if domains:
        add("memory", "DOMAIN", domains)
    if scope.project_ids:
        add("state", "CURRENT_PROJECT_STATE")
    if profile == "continuation":
        add("memory", "RECENT_CONTINUITY", (), STRICT_TIER)
    aliases = _aliases((*concepts, *domains))
    if aliases:
        add("memory", "CONCEPT", aliases, FALLBACK_TIER)
    if profile_config.allow_graph and (getattr(task, "entities", ()) or concepts or domains):
        add("graph", "RELATION_EXPANSION", _unique((*getattr(task, "entities", ()), *concepts, *domains)), FALLBACK_TIER)

    fingerprint = _fingerprint(task, profile, scope, history_mode, config.version)
    route_id = "route_" + fingerprint[:20]
    return RetrievalPlan(
        route_id=route_id,
        task_id=task.task_id,
        route_profile=profile,
        scope=scope,
        history_mode=history_mode,
        queries=tuple(queries),
        candidate_budget={
            "memory": profile_config.memory_candidate_budget,
            "state": profile_config.state_candidate_budget,
            "graph": profile_config.graph_candidate_budget,
        },
        router_config_version=config.version,
        fingerprint=fingerprint,
    )
