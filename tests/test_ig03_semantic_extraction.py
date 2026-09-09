"""IG-03 proposal-only semantic extraction contract tests."""

from __future__ import annotations

import pytest

from brain_eleven.extraction.semantic import (
    CallableSemanticProvider,
    DeterministicSafetyPrefilter,
    DeterministicRegexProvider,
    SemanticStatus,
    UnavailableProvider,
    PropositionValidationError,
    build_proposition,
    validate_proposition,
    SemanticProposition,
    ProviderResult,
)


def _message(content: str, *, role: str = "user", project_id: str | None = "brain-eleven"):
    return {
        "content": content,
        "role": role,
        "project_id": project_id,
        "evidence_id": "evidence-01",
        "occurred_at": None,
    }


def _payload(**overrides):
    value = {
        "candidate_id": "cand-01",
        "project_id": "brain-eleven",
        "claim_type": "decision",
        "subject": "auth",
        "predicate": "uses",
        "value": "session cookie",
        "commitment": "explicit",
        "temporal_scope": None,
        "source_role": "user",
        "evidence_refs": ["evidence-01"],
        "confidence_components": {"classification": 0.9, "scope": 1.0},
        "correction_clues": None,
        "target_clues": None,
        "schema_version": "ig01-a-proposition-v1",
    }
    value.update(overrides)
    return value


def test_prefilter_blocks_secrets_and_preserves_evidence_flags():
    prefilter = DeterministicSafetyPrefilter()
    secret = prefilter.evaluate("API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz123456")
    assert secret.allowed is False
    assert secret.reason_code == "potential_secret"
    assert secret.content_hash.startswith("sha256:")

    question = prefilter.evaluate("JWT kullansak mı?")
    assert question.allowed is True
    assert "question" in question.evidence_flags

    quoted = prefilter.evaluate('"Use Redis." başka dokümandan alıntı.')
    assert quoted.allowed is False
    assert quoted.reason_code == "quoted_material"
    assert "quoted" in quoted.evidence_flags


def test_builder_rejects_unknown_and_nested_authority_fields():
    bad_top = _payload(canonical_commit=True)
    try:
        build_proposition(bad_top)
    except PropositionValidationError:
        pass
    else:
        raise AssertionError("canonical writer field must be rejected")

    try:
        build_proposition(_payload(value={"content": "secret raw text"}))
    except PropositionValidationError:
        pass
    else:
        raise AssertionError("nested raw content field must be rejected")

    try:
        build_proposition(_payload(evidence_refs=[None]))
    except PropositionValidationError:
        pass
    else:
        raise AssertionError("null evidence references must be rejected")


def test_validator_is_fail_closed_for_unknown_role_and_prefilter_flags():
    unknown = build_proposition(_payload(source_role="unknown"))
    unknown_result = validate_proposition(unknown)
    assert unknown_result.valid is False
    assert unknown_result.reason_code == "UNKNOWN_SOURCE_ROLE"

    flagged = build_proposition(_payload(value=None))
    flagged_result = validate_proposition(flagged, evidence_flags=("question",))
    assert flagged_result.valid is False
    assert flagged_result.reason_code == "QUESTION_COMMITMENT"


def test_direct_proposition_and_provider_result_are_revalidated():
    unsafe = SemanticProposition(
        candidate_id="cand-unsafe",
        project_id="brain-eleven",
        claim_type="decision",
        subject="auth",
        predicate="uses",
        value={"canonical_commit": True},
        commitment="explicit",
        temporal_scope=None,
        source_role="user",
        evidence_refs=("evidence-unsafe",),
        confidence_components={"classification": 1.0},
        correction_clues=None,
        target_clues=None,
    )
    result = validate_proposition(unsafe)
    assert result.valid is False
    try:
        ProviderResult(status=SemanticStatus.MEASURED.value, provider_id="x", model="y", propositions=(unsafe,))
    except ValueError:
        pass
    else:
        raise AssertionError("ProviderResult must revalidate proposition objects")

    try:
        ProviderResult(
            status=SemanticStatus.MEASURED.value,
            provider_id="x",
            model="y",
            metadata={"provider_revision": {"note": "raw"}},
        )
    except ValueError:
        pass
    else:
        raise AssertionError("provider metadata must remain scalar and content-free")


def test_provider_review_records_require_full_hash_and_bounded_reason_code():
    with pytest.raises(ValueError):
        ProviderResult(
            status=SemanticStatus.SEMANTIC_UNAVAILABLE.value,
            provider_id="x",
            model="y",
            review_records=({"case_hash": "sha256:short", "reason_code": "x"},),
        )
    with pytest.raises(ValueError):
        ProviderResult(
            status=SemanticStatus.SEMANTIC_UNAVAILABLE.value,
            provider_id="x",
            model="y",
            review_records=({"case_hash": "sha256:" + "a" * 64, "reason_code": "contains space"},),
        )


def test_provider_forces_evidence_authority_fields_over_model_output():
    def model(_: str):
        row = _payload(project_id="foreign", source_role="user", evidence_refs=["foreign"])
        return {"propositions": [row]}

    result = CallableSemanticProvider("model", "test", model).extract(
        _message("SQLite kullanacağız.", role="assistant", project_id="brain-eleven")
    )
    assert result.propositions == ()
    assert result.review_records


def test_callable_provider_never_invoked_for_filtered_content():
    calls: list[str] = []

    def model(text: str):
        calls.append(text)
        return {"propositions": [_payload()]}

    provider = CallableSemanticProvider("local-qwen", "qwen-test", model)
    result = provider.extract(_message("password=supersecretvalue123"))
    assert result.status == SemanticStatus.FILTERED.value
    assert result.error_code == "potential_secret"
    assert calls == []


def test_callable_provider_rejects_malicious_canonical_output():
    def model(_: str):
        row = _payload()
        row["canonical_commit"] = True
        return {"propositions": [row]}

    result = CallableSemanticProvider("strong-model", "test", model).extract(_message("SQLite kullanacağız."))
    assert result.status == SemanticStatus.INVALID_OUTPUT.value
    assert result.propositions == ()


def test_callable_provider_keeps_assistant_commitment_out_of_canonical_candidates():
    def model(_: str):
        return {"propositions": [_payload(commitment="explicit")]}

    result = CallableSemanticProvider("strong-model", "test", model).extract(
        _message("We should use Postgres.", role="assistant")
    )
    assert result.status == SemanticStatus.MEASURED.value
    assert result.propositions == ()
    assert result.review_records


def test_unavailable_provider_is_explicit_and_deterministic_control_is_proposal_only():
    unavailable = UnavailableProvider("qwen-local", "qwen3", "not_installed").extract(_message("SQLite kullanacağız."))
    assert unavailable.status == SemanticStatus.SEMANTIC_UNAVAILABLE.value
    assert unavailable.error_code == "not_installed"

    measured = DeterministicRegexProvider().extract(_message("SQLite kullanacağız."))
    assert measured.status == SemanticStatus.MEASURED.value
    assert measured.propositions
    assert all("canonical_commit" not in item.to_dict() for item in measured.propositions)
