"""Turkish decision/lesson/observation phrasing reaches the right commitment and type."""

import pytest

from extraction import Commitment, _classify_commitment, _memory_type


@pytest.mark.parametrize("text", [
    "Karar verildi: hafıza servisi Windows'ta gizli çalışır.",
    "Kararlaştırdık, eşikler değişmeyecek.",
    "Bundan sonra her PR'da tam test takımını çalıştırıyoruz.",
    "Artık inceleme ekranını kullanacağız.",
    "Holdout ayarını değiştirmeyeceğiz.",
    "Anlaştık, V2 SHADOW kalır.",
])
def test_turkish_decisions_are_committed_decisions(text):
    assert _classify_commitment(text, "user") is Commitment.COMMITTED
    assert _memory_type(text) == "decision"


def test_turkish_lesson_and_observation():
    assert _memory_type("Meğer BOM yüzünden Codex hook'ları çalışmıyormuş.") == "lesson"
    assert _classify_commitment("Codex hook'u hata veriyor.", "user") is Commitment.OBSERVED


@pytest.mark.parametrize("text", [
    "Bundan sonra ne yapalım?",
    "Artık bunu kullanacağız mı?",
])
def test_turkish_questions_stay_questions(text):
    assert _classify_commitment(text, "user") is Commitment.QUESTION


def test_assistant_turkish_decision_is_only_proposed():
    assert _classify_commitment("Bundan sonra servisi yeniden başlatacağız.", "assistant") is Commitment.PROPOSED
