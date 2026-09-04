"""Versioned, fail-closed configuration for the Phase 17 router."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


ROUTER_CONFIG_VERSION = 1


class RouterConfigError(ValueError):
    """The router configuration is missing required safety guarantees."""


@dataclass(frozen=True)
class ProfileConfig:
    memory_candidate_budget: int
    state_candidate_budget: int
    graph_candidate_budget: int
    memory_types: tuple[str, ...]
    allow_global: bool = True
    allow_graph: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_candidate_budget": self.memory_candidate_budget,
            "state_candidate_budget": self.state_candidate_budget,
            "graph_candidate_budget": self.graph_candidate_budget,
            "memory_types": list(self.memory_types),
            "allow_global": self.allow_global,
            "allow_graph": self.allow_graph,
        }


_DEFAULT_PROFILE = ProfileConfig(20, 12, 6, ("decision", "lesson", "open_loop", "observation"))
DEFAULT_PROFILES: dict[str, ProfileConfig] = {
    "continuation": ProfileConfig(20, 12, 4, ("open_loop", "decision", "lesson")),
    "implementation": ProfileConfig(30, 12, 8, ("decision", "lesson", "open_loop")),
    "debugging": ProfileConfig(30, 12, 8, ("lesson", "decision", "open_loop")),
    "architecture": ProfileConfig(30, 12, 8, ("decision", "lesson")),
    "review": ProfileConfig(25, 12, 4, ("decision", "lesson", "open_loop")),
    "research": ProfileConfig(25, 8, 8, ("decision", "lesson", "observation")),
    "general": _DEFAULT_PROFILE,
}


@dataclass(frozen=True)
class RouterConfig:
    version: int = ROUTER_CONFIG_VERSION
    profiles: Mapping[str, ProfileConfig] = None
    retry_on_revision_change: int = 1
    max_queries_per_route: int = 16
    max_graph_hops: int = 2
    strict_min_memory_candidates: int = 3
    cache_enabled: bool = True

    def __post_init__(self) -> None:
        if self.version != ROUTER_CONFIG_VERSION:
            raise RouterConfigError(f"Unsupported router config schema: {self.version}")
        profiles = dict(DEFAULT_PROFILES if self.profiles is None else self.profiles)
        missing = set(DEFAULT_PROFILES) - set(profiles)
        if missing:
            raise RouterConfigError(f"Missing router profiles: {', '.join(sorted(missing))}")
        for name, profile in profiles.items():
            if not isinstance(profile, ProfileConfig):
                raise RouterConfigError(f"Invalid profile config: {name}")
            for value in (
                profile.memory_candidate_budget,
                profile.state_candidate_budget,
                profile.graph_candidate_budget,
            ):
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise RouterConfigError("Candidate budgets must be non-negative integers")
        if self.retry_on_revision_change not in {0, 1}:
            raise RouterConfigError("retry_on_revision_change must be 0 or 1")
        for name, value in (
            ("max_queries_per_route", self.max_queries_per_route),
            ("max_graph_hops", self.max_graph_hops),
            ("strict_min_memory_candidates", self.strict_min_memory_candidates),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RouterConfigError(f"{name} must be a non-negative integer")
        if not isinstance(self.cache_enabled, bool):
            raise RouterConfigError("cache_enabled must be boolean")
        object.__setattr__(self, "profiles", profiles)

    @classmethod
    def load(cls, vault_path: str | Path) -> "RouterConfig":
        path = Path(vault_path) / ".claude" / "context-router.json"
        if not path.exists():
            return cls()
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RouterConfigError(f"Cannot read router config: {path}") from exc
        if not isinstance(document, Mapping):
            raise RouterConfigError("Router config must be an object")
        allowed = {
            "schema_version",
            "profiles",
            "routing",
        }
        unknown = set(document) - allowed
        if unknown:
            raise RouterConfigError(f"Unknown router config fields: {', '.join(sorted(unknown))}")
        if document.get("schema_version") != ROUTER_CONFIG_VERSION:
            raise RouterConfigError("Router config schema_version must be 1")
        profiles = dict(DEFAULT_PROFILES)
        supplied_profiles = document.get("profiles", {})
        if not isinstance(supplied_profiles, Mapping):
            raise RouterConfigError("profiles must be an object")
        for name, values in supplied_profiles.items():
            if name not in profiles or not isinstance(values, Mapping):
                raise RouterConfigError(f"Invalid router profile: {name}")
            allowed_profile = set(ProfileConfig.__dataclass_fields__)
            if set(values) - allowed_profile:
                raise RouterConfigError(f"Unknown fields for router profile: {name}")
            merged = profiles[name].to_dict()
            merged.update(values)
            memory_types = merged.get("memory_types")
            if not isinstance(memory_types, list) or not all(isinstance(item, str) for item in memory_types):
                raise RouterConfigError(f"Profile {name} memory_types must be a string list")
            merged["memory_types"] = tuple(memory_types)
            profiles[name] = ProfileConfig(**merged)
        routing = document.get("routing", {})
        if not isinstance(routing, Mapping):
            raise RouterConfigError("routing must be an object")
        allowed_routing = {
            "allow_implicit_cross_project",
            "retry_on_revision_change",
            "max_queries_per_route",
            "max_graph_hops",
            "strict_min_memory_candidates",
            "cache_enabled",
        }
        if set(routing) - allowed_routing:
            raise RouterConfigError("Unknown routing configuration field")
        if routing.get("allow_implicit_cross_project", False) is not False:
            raise RouterConfigError("Implicit cross-project routing is permanently disabled")
        return cls(
            profiles=profiles,
            retry_on_revision_change=routing.get("retry_on_revision_change", 1),
            max_queries_per_route=routing.get("max_queries_per_route", 16),
            max_graph_hops=routing.get("max_graph_hops", 2),
            strict_min_memory_candidates=routing.get("strict_min_memory_candidates", 3),
            cache_enabled=routing.get("cache_enabled", True),
        )
