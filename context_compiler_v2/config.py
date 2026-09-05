"""Versioned, fail-closed configuration for the derived Phase 19 compiler."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .profile_policy import DEFAULT_PROFILE_BUDGETS, ProfileBudgetPolicy, profile_budgets_from_dict


CONFIG_RELATIVE_PATH = Path(".claude") / "context-compiler-v2.json"
CONFIG_SCHEMA_VERSION = 1


class CompilerConfigError(ValueError):
    """Configuration errors never silently enable a compiler policy."""


@dataclass(frozen=True)
class CompilerConfig:
    policy_version: str = "context-compiler-v2-policy-v1"
    cache_enabled: bool = True
    max_rebalance_iterations: int = 8
    default_mode: str = "SHADOW"
    profile_budgets: Mapping[str, ProfileBudgetPolicy] = field(
        default_factory=lambda: dict(DEFAULT_PROFILE_BUDGETS)
    )

    @classmethod
    def load(cls, vault_path: str | Path) -> "CompilerConfig":
        path = Path(vault_path) / CONFIG_RELATIVE_PATH
        if not path.exists():
            return cls()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CompilerConfigError(f"Compiler configuration is unreadable: {exc}") from exc
        required = {"schema_version", "policy_version", "cache_enabled", "max_rebalance_iterations", "default_mode"}
        if not isinstance(payload, Mapping) or set(payload) - (required | {"profile_budgets"}) or required - set(payload):
            raise CompilerConfigError("Compiler configuration has an unsupported schema")
        if payload["schema_version"] != CONFIG_SCHEMA_VERSION:
            raise CompilerConfigError("Compiler configuration schema_version is unsupported")
        policy = payload["policy_version"]
        if not isinstance(policy, str) or policy != "context-compiler-v2-policy-v1":
            raise CompilerConfigError("Compiler configuration policy_version is unsupported")
        cache_enabled = payload["cache_enabled"]
        iterations = payload["max_rebalance_iterations"]
        mode = payload["default_mode"]
        if not isinstance(cache_enabled, bool):
            raise CompilerConfigError("Compiler configuration cache_enabled must be boolean")
        if isinstance(iterations, bool) or not isinstance(iterations, int) or not 1 <= iterations <= 32:
            raise CompilerConfigError("Compiler configuration max_rebalance_iterations must be 1..32")
        if mode not in {"OFF", "SHADOW"}:
            raise CompilerConfigError("Compiler configuration default_mode must be OFF or SHADOW")
        try:
            profile_budgets = profile_budgets_from_dict(payload["profile_budgets"])
        except (KeyError, TypeError, ValueError) as exc:
            if "profile_budgets" in payload:
                raise CompilerConfigError(f"Compiler profile budget policy is invalid: {exc}") from exc
            profile_budgets = dict(DEFAULT_PROFILE_BUDGETS)
        return cls(policy, cache_enabled, iterations, mode, profile_budgets)
