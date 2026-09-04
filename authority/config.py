"""Versioned, fail-closed configuration for the authority resolver."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


AUTHORITY_CONFIG_VERSION = 1


class AuthorityConfigError(ValueError):
    """The authority configuration is invalid or weakens a safety invariant."""


@dataclass(frozen=True)
class AuthorityConfig:
    version: int = AUTHORITY_CONFIG_VERSION
    policy_version: str = "authority-v1"
    cache_enabled: bool = True
    shadow_retry_on_stale: int = 1

    def __post_init__(self) -> None:
        if self.version != AUTHORITY_CONFIG_VERSION:
            raise AuthorityConfigError(f"Unsupported authority config schema: {self.version}")
        if self.policy_version != "authority-v1":
            raise AuthorityConfigError(f"Unsupported authority policy: {self.policy_version}")
        if not isinstance(self.cache_enabled, bool):
            raise AuthorityConfigError("cache_enabled must be boolean")
        if self.shadow_retry_on_stale not in {0, 1}:
            raise AuthorityConfigError("shadow_retry_on_stale must be 0 or 1")

    @classmethod
    def load(cls, vault_path: str | Path) -> "AuthorityConfig":
        path = Path(vault_path) / ".claude" / "authority-resolver.json"
        if not path.exists():
            return cls()
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthorityConfigError(f"Cannot read authority config: {path}") from exc
        if not isinstance(document, Mapping):
            raise AuthorityConfigError("Authority config must be an object")
        if set(document) - {"schema_version", "policy", "cache"}:
            raise AuthorityConfigError("Unknown authority config field")
        if document.get("schema_version") != AUTHORITY_CONFIG_VERSION:
            raise AuthorityConfigError("authority config schema_version must be 1")
        policy = document.get("policy", {})
        cache = document.get("cache", {})
        if not isinstance(policy, Mapping) or not isinstance(cache, Mapping):
            raise AuthorityConfigError("policy and cache must be objects")
        if set(policy) - {"version", "allow_implicit_cross_project", "allow_retrieval_score_authority"}:
            raise AuthorityConfigError("Unknown authority policy field")
        if set(cache) - {"enabled", "shadow_retry_on_stale"}:
            raise AuthorityConfigError("Unknown authority cache field")
        if policy.get("allow_implicit_cross_project", False) is not False:
            raise AuthorityConfigError("Implicit cross-project authority is permanently disabled")
        if policy.get("allow_retrieval_score_authority", False) is not False:
            raise AuthorityConfigError("Retrieval score can never determine authority")
        return cls(
            policy_version=policy.get("version", "authority-v1"),
            cache_enabled=cache.get("enabled", True),
            shadow_retry_on_stale=cache.get("shadow_retry_on_stale", 1),
        )
