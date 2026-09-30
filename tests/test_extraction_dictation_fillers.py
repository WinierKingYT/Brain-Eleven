"""Dictation fillers are dropped from captured memory text.

2026-09-30: the owner dictates in Turkish; a W39 recall answer was stored
as "Dökümanları e, uzun bir süre topluyor ..." and could not be matched.
"""

from __future__ import annotations

import json

import pytest

from evidence import TranscriptReader
from extraction import DeterministicExtractor, NewMemoryCandidate, strip_dictation_fillers


@pytest.mark.parametrize(("raw", "clean"), [
    ("Dökümanları e, uzun bir süre topluyor.", "Dökümanları uzun bir süre topluyor."),
    ("Ee, SQLite kullanacağız.", "SQLite kullanacağız."),
    ("Bunu ııı yarın eee yapacağız.", "Bunu yarın yapacağız."),
    ("Hmm, tamam.", "tamam."),
])
def test_standalone_fillers_are_removed(raw, clean):
    assert strip_dictation_fillers(raw) == clean


@pytest.mark.parametrize("text", [
    "II ve III farklı.",
    "III. bölüm önemli.",
    "keep HMM model",
    "Harfler a, b, c, d, e, f olsun.",
    "fn(a, e, b) kullan",
    "`ee` değişkeni",
    "hı hı, tamam onu kullan.",
    "e-posta adresini değiştirdik.",
    "Emre ve Ece karar verdi.",
    "Plan e ile başlıyor: e2e testleri.",
    "Değer 3e olmalı.",
])
def test_words_containing_e_are_untouched(text):
    assert strip_dictation_fillers(text) == text


def test_captured_memory_content_has_no_fillers(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(json.dumps({"role": "user", "content": "Ee, SQLite kullanacağız çünkü uygulama tamamen lokal."}) + "\n",
                          encoding="utf-8")
    batch = TranscriptReader().read(transcript, session_id="s", project_id="brain-eleven",
                                    captured_at="2026-09-30T10:00:00Z")
    result = DeterministicExtractor().extract(batch)

    memories = [c for c in result.candidates if isinstance(c, NewMemoryCandidate)]
    assert memories and all(not c.content.lower().startswith("ee") for c in memories)


def test_filler_only_segment_keeps_later_candidate_ids(tmp_path):
    from extraction import _candidate_id

    transcript = tmp_path / "s.jsonl"
    transcript.write_text(json.dumps({"role": "user", "content": "Ee. Postgres kullanacağız. Redis de kullanacağız."})
                          + "\n", encoding="utf-8")
    batch = TranscriptReader().read(transcript, session_id="s", project_id="brain-eleven",
                                    captured_at="2026-09-30T10:00:00Z")
    candidates = DeterministicExtractor().extract(batch).candidates
    message = batch.messages[0]

    # The dropped filler segment keeps index 0, so later ids do not shift.
    assert [c.candidate_id for c in candidates] == [
        _candidate_id(message, index, c.candidate_type) for index, c in zip((1, 2), candidates)]
