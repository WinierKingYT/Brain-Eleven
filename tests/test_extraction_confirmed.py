"""An assistant decision the user explicitly approves next becomes a user-committed candidate."""

from extraction import Commitment, DeterministicExtractor, NewMemoryCandidate
from tests.test_extraction import _batch


def _decisions(result):
    return [c for c in result.candidates if isinstance(c, NewMemoryCandidate)]


def test_short_approval_promotes_only_the_assistant_decision(tmp_path):
    result = DeterministicExtractor().extract(_batch(tmp_path, [
        {"role": "assistant", "content": "Bundan sonra her PR'da tam test takımını çalıştıracağız. Hava güzel."},
        {"role": "user", "content": "Tamam, öyle yapalım."},
    ]))
    found = _decisions(result)
    assert len(found) == 1
    assert found[0].commitment == Commitment.COMMITTED.value
    assert found[0].memory_type == "decision"
    assert len(found[0].evidence_refs) == 2
    assert found[0].confidence_components["source_authority"] == 1.0


def test_without_approval_the_proposal_stays_quarantined(tmp_path):
    for reply in ("Hayır, bunu yapmayalım.", "Tamam ama önce şunu açıkla: neden tam takım gerekiyor, CI zaten çalıştırıyor?"):
        result = DeterministicExtractor().extract(_batch(tmp_path, [
            {"role": "assistant", "content": "Bundan sonra her PR'da tam test takımını çalıştıracağız."},
            {"role": "user", "content": reply},
        ]))
        assert not any(c.commitment == Commitment.COMMITTED.value and len(c.evidence_refs) == 2
                       for c in _decisions(result))
        assert any(q.reason == "ASSISTANT_PROPOSAL" for q in result.quarantined)


def test_approved_assistant_question_is_not_promoted(tmp_path):
    result = DeterministicExtractor().extract(_batch(tmp_path, [
        {"role": "assistant", "content": "Bundan sonra SQLite kullanacağız mı?"},
        {"role": "user", "content": "evet"},
    ]))
    assert not any(len(c.evidence_refs) == 2 for c in _decisions(result))
