"""PRE-04 role, commitment and output-boundary contract tests."""

from __future__ import annotations

import json

from evidence import TranscriptReader
from extraction import Commitment, DeterministicExtractor, NewMemoryCandidate, StateMutationProposal


def _batch(tmp_path, rows, *, project_id="brain-eleven"):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return TranscriptReader().read(
        transcript,
        session_id="session_01",
        project_id=project_id,
        captured_at="2026-09-05T10:00:00Z",
    )


def test_explicit_user_decision_becomes_one_project_memory_candidate(tmp_path):
    result = DeterministicExtractor().extract(
        _batch(tmp_path, [{"role": "user", "content": "SQLite kullanacağız çünkü uygulama tamamen lokal."}])
    )

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert isinstance(candidate, NewMemoryCandidate)
    assert candidate.memory_type == "decision"
    assert candidate.commitment == Commitment.COMMITTED.value
    assert candidate.scope == "project"
    assert candidate.project_id == "brain-eleven"
    assert len(candidate.evidence_refs) == 1


def test_assistant_proposal_hypothetical_and_quote_never_become_user_decisions(tmp_path):
    result = DeterministicExtractor().extract(
        _batch(
            tmp_path,
            [
                {"role": "assistant", "content": "SQLite could be better."},
                {"role": "user", "content": "SQLite kullansak mı?"},
                {"role": "user", "content": '"Use Redis for everything." başka dokümandan alıntı.'},
            ],
        )
    )

    assert result.candidates == ()
    assert [item.reason for item in result.quarantined] == [
        "HYPOTHETICAL_NOT_COMMITMENT",
        "QUESTION_NOT_COMMITMENT",
        "QUOTED_CONTENT",
    ]
    assert all(item.commitment != Commitment.COMMITTED.value for item in result.quarantined)


def test_multi_claim_turn_routes_current_facts_to_state_and_decision_to_memory(tmp_path):
    result = DeterministicExtractor().extract(
        _batch(
            tmp_path,
            [
                {"role": "user", "content": "PostgreSQL yerine SQLite kullanacağız."},
                {"role": "user", "content": "Deployment blocker çözüldü ama auth tests hâlâ fail."},
            ],
        )
    )

    assert isinstance(result.candidates[0], NewMemoryCandidate)
    assert result.candidates[0].memory_type == "decision"
    assert [candidate.operation for candidate in result.candidates[1:]] == [
        "RESOLVE_BLOCKER",
        "ADD_BLOCKER",
    ]
    assert all(isinstance(candidate, StateMutationProposal) for candidate in result.candidates[1:])


def test_explicit_correction_never_creates_an_unresolved_lifecycle_mutation(tmp_path):
    result = DeterministicExtractor().extract(
        _batch(tmp_path, [{"role": "user", "content": "Hayır, PostgreSQL değil SQLite kullanacağız."}])
    )

    assert len(result.candidates) == 1
    assert isinstance(result.candidates[0], NewMemoryCandidate)
    assert result.candidates[0].content.startswith("Hayır")
    assert [item.reason for item in result.quarantined] == ["LIFECYCLE_TARGET_UNKNOWN"]


def test_unknown_project_is_quarantined_and_cannot_produce_a_canonical_candidate(tmp_path):
    result = DeterministicExtractor().extract(
        _batch(tmp_path, [{"role": "user", "content": "SQLite kullanacağız."}], project_id=None)
    )

    assert result.candidates == ()
    assert result.quarantined[0].reason == "SCOPE_UNRESOLVED"


def test_secret_candidate_is_quarantined_before_any_memory_or_state_output(tmp_path):
    result = DeterministicExtractor().extract(
        _batch(tmp_path, [{"role": "user", "content": "API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz123456"}])
    )

    assert result.candidates == ()
    assert result.quarantined[0].reason == "potential_secret"


def test_requirement_fact_becomes_typed_state_proposal(tmp_path):
    result = DeterministicExtractor().extract(
        _batch(tmp_path, [{"role": "user", "content": "Security requirement must be met."}])
    )

    assert len(result.candidates) == 1
    assert isinstance(result.candidates[0], StateMutationProposal)
    assert result.candidates[0].operation == "ADD_REQUIREMENT"


def test_machine_output_can_omit_candidate_text_for_safe_telemetry(tmp_path):
    result = DeterministicExtractor().extract(
        _batch(tmp_path, [{"role": "user", "content": "SQLite kullanacağız."}])
    )
    rendered = json.dumps(result.to_dict(include_content=False), ensure_ascii=False)

    assert "SQLite kullanacağız" not in rendered
    assert result.candidates[0].candidate_id in rendered
