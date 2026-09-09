"""Production OpenAI Responses/Chat semantic proposal provider.

This adapter is proposal-only. It delegates all evidence authority and schema
validation to :class:`CallableSemanticProvider`; it has no canonical-store or
lifecycle-writer imports. It is disabled unless explicitly selected and an
``OPENAI_API_KEY`` is available.
"""

from __future__ import annotations

import os
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
    PROPOSITION_SCHEMA,
    RESPONSE_SCHEMA,
    ProviderConfigurationError,
    finish_result,
    parse_json_object,
    response_text,
)


DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIAPIProvider:
    """Call the OpenAI API and return only validated semantic proposals."""

    provider_id = "openai-api"
    provider_revision = "openai-api-v1"

    def __init__(
        self,
        *,
        client: Any | None = None,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout_s: float = 30.0,
    ) -> None:
        if not model.strip():
            raise ProviderConfigurationError("invalid_model")
        if timeout_s <= 0:
            raise ProviderConfigurationError("invalid_timeout")
        if client is None:
            if not api_key:
                raise ProviderConfigurationError("missing_api_key")
            try:
                from openai import OpenAI
            except ImportError as error:
                raise ProviderConfigurationError("openai_sdk_not_installed") from error
            kwargs: dict[str, Any] = {"api_key": api_key, "timeout": timeout_s, "max_retries": 0}
            base_url = os.environ.get("OPENAI_BASE_URL")
            if base_url:
                kwargs["base_url"] = base_url
            try:
                client = OpenAI(**kwargs)
            except Exception as error:
                raise ProviderConfigurationError("openai_client_init_failed") from error
        self.client = client
        self.model = model
        self.timeout_s = timeout_s
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
        client: Any | None = None,
    ) -> "OpenAIAPIProvider":
        values = os.environ if environ is None else environ
        return cls(
            client=client,
            api_key=values.get("OPENAI_API_KEY"),
            model=values.get("IG_OPENAI_SEMANTIC_MODEL", DEFAULT_MODEL),
            timeout_s=float(values.get("IG_OPENAI_TIMEOUT_S", "30")),
        )

    def _call(self, content: str) -> Mapping[str, Any]:
        responses = getattr(self.client, "responses", None)
        if responses is not None and hasattr(responses, "create"):
            response = responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": MODEL_INSTRUCTION},
                    {"role": "user", "content": content},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "ig01_a_propositions",
                        "strict": True,
                        "schema": RESPONSE_SCHEMA,
                    }
                },
            )
        else:
            completions = getattr(getattr(self.client, "chat", None), "completions", None)
            if completions is None or not hasattr(completions, "create"):
                raise RuntimeError("openai client has no supported API")
            response = completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": MODEL_INSTRUCTION},
                    {"role": "user", "content": content},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "ig01_a_propositions",
                        "strict": True,
                        "schema": RESPONSE_SCHEMA,
                    },
                },
            )
        return parse_json_object(response_text(response))

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


OpenAISemanticProvider = OpenAIAPIProvider


__all__ = ["DEFAULT_MODEL", "OpenAIAPIProvider", "OpenAISemanticProvider"]
