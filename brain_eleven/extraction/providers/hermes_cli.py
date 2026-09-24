"""Semantic provider backed by the locally authenticated Hermes Agent CLI.

Mirrors ``codex_cli.py``'s shape and safety posture: no separate API key
(uses Hermes's own configured provider auth, e.g. a ChatGPT/Codex
subscription), every invocation is a single ephemeral one-shot call, and the
frozen IG01-A proposition schema still does the real validation -- this
module only supplies the raw model call.

Known limitation: Hermes's one-shot mode (``-z PROMPT``) takes the prompt as
a process argument, not via stdin (unlike the Codex CLI adapter). Very long
evidence content can exceed the OS command-line length limit; this is
guarded explicitly below rather than left to fail unpredictably.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess  # nosec B404
from time import perf_counter
from typing import Any, Mapping

from brain_eleven.extraction.semantic import (
    CallableSemanticProvider,
    ProviderResult,
    SemanticProvider,
    SEMANTIC_SCHEMA_VERSION,
    _message_fields,
)

from .common import (
    MODEL_INSTRUCTION,
    ProviderConfigurationError,
    finish_result,
    hidden_console_kwargs,
    parse_json_object,
)


# Conservative bound well under typical OS command-line limits (~32767 chars
# on Windows), leaving room for MODEL_INSTRUCTION and the executable/flags.
MAX_PROMPT_CHARS = 6000


def discover_hermes_executable(environ: Mapping[str, str] | None = None) -> str | None:
    """Find an explicitly configured CLI, PATH install, or standard Windows install."""

    values = os.environ if environ is None else environ
    configured = values.get("HERMES_CLI_PATH")
    if configured and Path(configured).is_file():
        return configured
    path_match = shutil.which("hermes") or shutil.which("hermes.exe")
    if path_match:
        return path_match
    local_app_data = values.get("LOCALAPPDATA")
    roots = [Path(local_app_data) / "hermes" / "bin"] if local_app_data else []
    if os.name == "nt":
        roots.append(Path.home() / "AppData" / "Local" / "hermes" / "bin")
    for root in roots:
        candidate = root / "hermes.exe"
        if candidate.is_file():
            return str(candidate)
    return None


class HermesCLIProvider:
    """Use one ephemeral Hermes Agent one-shot invocation per case."""

    provider_id = "hermes-cli"
    provider_revision = "hermes-cli-v1"

    def __init__(
        self,
        *,
        executable: str | None = None,
        model: str | None = None,
        timeout_s: float = 60.0,
        runner: Any | None = None,
    ) -> None:
        resolved = executable or discover_hermes_executable()
        if not resolved or not Path(resolved).is_file():
            raise ProviderConfigurationError("hermes_cli_not_found")
        if timeout_s <= 0:
            raise ProviderConfigurationError("invalid_timeout")
        self.executable = resolved
        # None means "use Hermes's own configured default model/provider" --
        # unlike Codex, Hermes always has one configured (via `hermes setup`),
        # so an explicit model here is an override, not a requirement.
        self.model = model or "hermes-default"
        self._model_override = model
        self.timeout_s = timeout_s
        self._runner = runner
        self._delegate: SemanticProvider = CallableSemanticProvider(
            self.provider_id,
            self.model,
            self._call,
            provider_revision=self.provider_revision,
        )

    @classmethod
    def from_environment(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        executable: str | None = None,
        runner: Any | None = None,
    ) -> "HermesCLIProvider":
        values = os.environ if environ is None else environ
        timeout = float(values.get("IG_HERMES_TIMEOUT_S", "60"))
        return cls(
            executable=executable or discover_hermes_executable(values),
            model=values.get("IG_HERMES_MODEL") or None,
            timeout_s=timeout,
            runner=runner,
        )

    def _call(self, content: str) -> Mapping[str, Any]:
        prompt = f"{MODEL_INSTRUCTION}\nThe evidence to classify is below.\n{content}"
        if len(prompt) > MAX_PROMPT_CHARS:
            raise RuntimeError("hermes cli prompt exceeds safe command-line length")
        # --ignore-rules: don't let the CWD's AGENTS.md/memory/rules/skills
        # leak into a classification call that must see only the frozen
        # instruction and the evidence text.
        command: list[str] = [self.executable, "-z", prompt, "--ignore-rules"]
        if self._model_override:
            command.extend(["--model", self._model_override])
        runner = self._runner or subprocess.run
        try:
            completed = runner(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
                **hidden_console_kwargs(),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError("hermes cli invocation failed") from error
        if getattr(completed, "returncode", 1) != 0:
            raise RuntimeError("hermes cli returned non-zero")
        stdout = getattr(completed, "stdout", "") or ""
        if not stdout.strip():
            raise RuntimeError("hermes cli returned no structured output")
        try:
            return parse_json_object(stdout)
        except (OSError, UnicodeError, ValueError) as error:
            # The CLI contract is stricter than the model contract: malformed
            # or non-JSON stdout means this path is unavailable, never an
            # invalid semantic proposition.
            raise RuntimeError("hermes cli returned invalid structured output") from error

    def extract(
        self,
        message: Any,
        *,
        project_id: str | None = None,
        schema_version: str = SEMANTIC_SCHEMA_VERSION,
    ) -> ProviderResult:
        started = perf_counter()
        _, _, _, evidence_id, _ = _message_fields(message)
        result = self._delegate.extract(message, project_id=project_id, schema_version=schema_version)
        return finish_result(result, started=started, case_id=evidence_id, provider_id=self.provider_id)


HermesSemanticProvider = HermesCLIProvider


__all__ = ["HermesCLIProvider", "HermesSemanticProvider", "discover_hermes_executable", "MAX_PROMPT_CHARS"]
