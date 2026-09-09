"""Shared, content-free helpers for remote semantic provider adapters."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import logging
from time import perf_counter
from typing import Any, Mapping

from brain_eleven.extraction.semantic import ProviderResult


logger = logging.getLogger(__name__)


class ProviderConfigurationError(RuntimeError):
    """A provider cannot be constructed from the current configuration."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


MODEL_INSTRUCTION = """Return only one JSON object with this exact shape:
{\"propositions\": [{\"candidate_id\": \"...\", \"project_id\": null,
\"claim_type\": \"...\", \"subject\": null, \"predicate\": null,
\"value\": null, \"commitment\": \"...\", \"temporal_scope\": null,
\"source_role\": \"...\", \"evidence_refs\": [],
\"confidence_components\": {\"classification\": 0.0}, \"correction_clues\": null,
\"target_clues\": null, \"schema_version\": \"ig01-a-proposition-v1\"}]}
Each array item must contain those fields directly. Use only these frozen
claim_type values: decision, preference, lesson, requirement, blocker,
observation, open_loop, or no_commitment. Use only these commitment values:
committed, proposed, hypothetical, question, negated, quoted, observed, or
uncertain. source_role must be user, assistant, tool, or system. Include at
least one numeric confidence_components value between 0 and 1. Never wrap an
item in a \"proposition\" key, return a proposition as a string, add
writer/persistence fields, or include prompt, transcript, secret, or other
fields. Do not repeat evidence text in metadata. If no safe proposition is present, return exactly
{\"propositions\": []}."""


# This schema constrains the model response. The existing semantic boundary is
# still authoritative and performs a second strict validation pass.
PROPOSITION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "candidate_id": {"type": "string"},
        "project_id": {"type": ["string", "null"]},
        "claim_type": {"type": "string"},
        "subject": {"type": ["string", "null"]},
        "predicate": {"type": ["string", "null"]},
        "value": {},
        "commitment": {"type": "string"},
        "temporal_scope": {"type": ["object", "null"]},
        "source_role": {"type": "string"},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "confidence_components": {"type": "object", "additionalProperties": {"type": "number"}},
        "correction_clues": {"type": ["object", "null"]},
        "target_clues": {"type": ["object", "null"]},
        "schema_version": {"type": "string"},
    },
    "required": [
        "candidate_id",
        "project_id",
        "claim_type",
        "subject",
        "predicate",
        "value",
        "commitment",
        "temporal_scope",
        "source_role",
        "evidence_refs",
        "confidence_components",
        "correction_clues",
        "target_clues",
        "schema_version",
    ],
}


RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "propositions": {"type": "array", "items": PROPOSITION_SCHEMA},
    },
    "required": ["propositions"],
}


def parse_json_object(payload: Any) -> Mapping[str, Any]:
    """Parse a provider response without accepting prose or fenced JSON."""

    if isinstance(payload, Mapping):
        return payload
    if not isinstance(payload, str):
        raise ValueError("provider response is not JSON text")
    parsed = json.loads(payload)
    if not isinstance(parsed, Mapping):
        raise ValueError("provider response is not a JSON object")
    return parsed


def response_text(response: Any) -> str:
    """Extract only the final structured text from SDK response shapes."""

    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str):
        return output_text
    if isinstance(response, Mapping) and isinstance(response.get("output_text"), str):
        return str(response["output_text"])

    output = getattr(response, "output", None)
    if output is None and isinstance(response, Mapping):
        output = response.get("output")
    if isinstance(output, list):
        for item in output:
            content_items = getattr(item, "content", None)
            if content_items is None and isinstance(item, Mapping):
                content_items = item.get("content")
            if isinstance(content_items, list):
                for content_item in content_items:
                    text = getattr(content_item, "text", None)
                    if text is None and isinstance(content_item, Mapping):
                        text = content_item.get("text")
                    if isinstance(text, str):
                        return text

    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, Mapping):
        choices = response.get("choices")
    if isinstance(choices, list) and choices:
        message = getattr(choices[0], "message", None)
        if message is None and isinstance(choices[0], Mapping):
            message = choices[0].get("message")
        content = getattr(message, "content", None)
        if content is None and isinstance(message, Mapping):
            content = message.get("content")
        if isinstance(content, str):
            return content
    raise ValueError("provider response did not contain structured text")


def finish_result(result: ProviderResult, *, started: float, case_id: str, provider_id: str) -> ProviderResult:
    """Attach bounded latency and emit a log record that contains no content."""

    elapsed_ms = round((perf_counter() - started) * 1000, 3)
    case_id_hash = "sha256:" + hashlib.sha256((case_id or "unknown").encode("utf-8")).hexdigest()
    logger.info(
        "semantic_provider_call",
        extra={
            "case_id": case_id_hash,
            "provider_id": provider_id,
            "status": result.status,
            "latency_ms": elapsed_ms,
        },
    )
    return replace(result, elapsed_ms=elapsed_ms)
