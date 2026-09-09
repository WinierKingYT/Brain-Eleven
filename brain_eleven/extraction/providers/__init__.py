"""Config-gated semantic provider factory.

The factory defaults to ``UnavailableProvider``. Selecting a remote provider
is an explicit operator action through ``IG_SEMANTIC_PROVIDER`` or
``.claude/ig-provider-config.json``; every construction/probe failure falls
back to the same unavailable result.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from brain_eleven.extraction.semantic import SemanticProvider, UnavailableProvider

from .codex_cli import CodexCLIProvider, CodexSemanticProvider
from .openai_api import OpenAIAPIProvider, OpenAISemanticProvider


DEFAULT_CONFIG_PATH = Path(".claude") / "ig-provider-config.json"
SUPPORTED_PROVIDERS = frozenset({"openai_api", "codex_cli", "unavailable"})


def _config_selection(
    *,
    config_path: Path | str | None,
    environ: Mapping[str, str],
) -> str:
    explicit = environ.get("IG_SEMANTIC_PROVIDER")
    if explicit is not None:
        return explicit.strip().lower()
    path = Path(config_path) if config_path is not None else Path(environ.get("IG_PROVIDER_CONFIG", DEFAULT_CONFIG_PATH))
    if not path.is_file():
        return "unavailable"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("provider config is unreadable") from error
    if not isinstance(payload, Mapping):
        raise ValueError("provider config must be an object")
    selected = payload.get("semantic_provider", payload.get("provider", payload.get("IG_SEMANTIC_PROVIDER", "unavailable")))
    if not isinstance(selected, str):
        raise ValueError("provider selection must be a string")
    return selected.strip().lower()


def create_semantic_provider(
    *,
    config_path: Path | str | None = None,
    environ: Mapping[str, str] | None = None,
    openai_client: Any | None = None,
    codex_executable: str | None = None,
    codex_runner: Any | None = None,
) -> SemanticProvider:
    """Return the selected provider, or an unavailable provider on any failure."""

    values = os.environ if environ is None else environ
    try:
        selected = _config_selection(config_path=config_path, environ=values)
        if selected not in SUPPORTED_PROVIDERS:
            return UnavailableProvider("unavailable", "unavailable", "unknown_provider")
        if selected == "unavailable":
            return UnavailableProvider("unavailable", "unavailable", "provider_not_configured")
        if selected == "openai_api":
            return OpenAIAPIProvider.from_environment(environ=values, client=openai_client)
        return CodexCLIProvider.from_environment(
            environ=values,
            executable=codex_executable,
            runner=codex_runner,
        )
    except Exception as error:
        reason = getattr(error, "reason_code", "provider_construction_failed")
        if not isinstance(reason, str) or not reason:
            reason = "provider_construction_failed"
        return UnavailableProvider("unavailable", "unavailable", reason[:64])


def configured_semantic_provider(**kwargs: Any) -> SemanticProvider:
    """Compatibility alias used by evaluation adapters."""

    return create_semantic_provider(**kwargs)


create_provider = create_semantic_provider


__all__ = [
    "CodexCLIProvider",
    "CodexSemanticProvider",
    "DEFAULT_CONFIG_PATH",
    "OpenAIAPIProvider",
    "OpenAISemanticProvider",
    "SUPPORTED_PROVIDERS",
    "configured_semantic_provider",
    "create_semantic_provider",
    "create_provider",
]
