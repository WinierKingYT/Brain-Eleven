"""Versioned, fail-closed configuration for the derived Phase 19 compiler."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


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

    @classmethod
    def load(cls, vault_path: str | Path) -> "CompilerConfig":
        path = Path(vault_path) / CONFIG_RELATIVE_PATH
        if not path.exists():
            return cls()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CompilerConfigError(f"Compiler configuration is unreadable: {exc}") from exc
        if not isinstance(payload, Mapping) or set(payload) != {
            "schema_version", "policy_version", "cache_enabled", "max_rebalance_iterations", "default_mode"
        }:
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
        return cls(policy, cache_enabled, iterations, mode)
