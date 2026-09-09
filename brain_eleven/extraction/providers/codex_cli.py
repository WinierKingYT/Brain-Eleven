"""Measurement-only semantic provider backed by ``codex exec``.

This path is intentionally not a production per-capture integration. It uses
the locally authenticated Codex CLI so R1 can obtain real semantic numbers
without copying a ChatGPT OAuth token into this repository or asking the user
to provide an API key. Every invocation is ephemeral, bounded by a timeout,
and required to return the frozen proposal JSON contract.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess  # nosec B404
import tempfile
from time import perf_counter
from typing import Any, Mapping, Sequence

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
    parse_json_object,
)


DEFAULT_MODEL = "gpt-5.6-luna"


def discover_codex_executable(environ: Mapping[str, str] | None = None) -> str | None:
    """Find an explicitly configured CLI, PATH install, or standard Windows install."""

    values = os.environ if environ is None else environ
    configured = values.get("CODEX_CLI_PATH")
    if configured and Path(configured).is_file():
        return configured
    path_match = shutil.which("codex") or shutil.which("codex.exe")
    if path_match:
        return path_match
    local_app_data = values.get("LOCALAPPDATA")
    roots = [Path(local_app_data) / "OpenAI" / "Codex" / "bin"] if local_app_data else []
    if os.name == "nt":
        roots.append(Path.home() / "AppData" / "Local" / "OpenAI" / "Codex" / "bin")
    for root in roots:
        if root.is_dir():
            candidates = sorted(root.glob("*/codex.exe"), reverse=True)
            if candidates:
                return str(candidates[0])
    return None


class CodexCLIProvider:
    """Use one ephemeral Codex CLI invocation per case for measurement only."""

    provider_id = "codex-cli"
    provider_revision = "codex-cli-measurement-v1"

    def __init__(
        self,
        *,
        executable: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout_s: float = 60.0,
        runner: Any | None = None,
    ) -> None:
        resolved = executable or discover_codex_executable()
        if not resolved or not Path(resolved).is_file():
            raise ProviderConfigurationError("codex_cli_not_found")
        if not model.strip():
            raise ProviderConfigurationError("invalid_model")
        if timeout_s <= 0:
            raise ProviderConfigurationError("invalid_timeout")
        self.executable = resolved
        self.model = model
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
    ) -> "CodexCLIProvider":
        values = os.environ if environ is None else environ
        timeout = float(values.get("IG_CODEX_TIMEOUT_S", "60"))
        return cls(
            executable=executable or discover_codex_executable(values),
            model=values.get("IG_CODEX_MODEL", DEFAULT_MODEL),
            timeout_s=timeout,
            runner=runner,
        )

    def _call(self, content: str) -> Mapping[str, Any]:
        with tempfile.TemporaryDirectory(prefix="brain-eleven-codex-") as directory:
            root = Path(directory)
            output_path = root / "last-message.json"
            prompt = f"{MODEL_INSTRUCTION}\nThe evidence to classify is below.\n{content}"
            # The CLI's output-schema option is not available consistently
            # across installed Codex builds. JSON-only output is enforced here
            # by exact parsing, then by the frozen proposition validator.
            command: list[str] = [
                self.executable,
                "exec",
                "--ephemeral",
                "--skip-git-repo-check",
                "--color",
                "never",
                "--output-last-message",
                str(output_path),
                "--model",
                self.model,
                "-",
            ]
            runner = self._runner or subprocess.run
            try:
                completed = runner(
                    command,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise RuntimeError("codex cli invocation failed") from error
            if getattr(completed, "returncode", 1) != 0:
                raise RuntimeError("codex cli returned non-zero")
            if not output_path.is_file():
                raise RuntimeError("codex cli returned no structured output")
            try:
                return parse_json_object(output_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError) as error:
                # The CLI contract is stricter than the model contract:
                # malformed/non-JSON output means this measurement path is
                # unavailable, never an invalid semantic proposition.
                raise RuntimeError("codex cli returned invalid structured output") from error

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


CodexSemanticProvider = CodexCLIProvider


__all__ = ["CodexCLIProvider", "CodexSemanticProvider", "DEFAULT_MODEL", "discover_codex_executable"]
