"""EXTRACT-01 review-noise reduction regression tests."""

from __future__ import annotations

import json
import re

import pytest

from brain_eleven.projects.registry import ProjectRegistry
from brain_eleven.runtime.migration import migrate
from brain_eleven.runtime.review import ReviewStore
from brain_eleven.runtime.storage import RuntimeConfig, write_json
from brain_eleven.runtime.worker import Worker, enqueue
from brain_eleven.state import StateService
from evidence import TranscriptReader
from extraction import Commitment, DeterministicExtractor


def _batch(tmp_path, content):
    transcript = tmp_path / "extract.jsonl"
    transcript.write_text(json.dumps({"role": "user", "content": content}) + "\n", encoding="utf-8")
    return TranscriptReader().read(
        transcript,
        session_id="extract-session",
        project_id="project-a",
        captured_at="2026-09-24T10:00:00Z",
    )


@pytest.mark.parametrize(
    "content",
    [
        "Redis kullansak mı?",
        "Belki Redis kullanabiliriz.",
        '"Redis kullanacağız" başka dokümandan alıntı.',
        "Hayır, Redis kullanmıyoruz.",
        "Bugün birkaç dosyaya baktım.",
    ],
)
def test_non_memory_user_utterances_remain_quarantined(tmp_path, content):
    result = DeterministicExtractor().extract(_batch(tmp_path, content))
    assert result.candidates == ()
    assert len(result.quarantined) == 1


@pytest.mark.parametrize(
    ("content", "memory_type"),
    [
        ("Yerel araçları tercih ederim.", "preference"),
        ("Bu hatadan öğrendik: kilidi yazmadan önce almalıyız.", "lesson"),
    ],
)
def test_explicit_user_preferences_and_lessons_remain_reviewable(tmp_path, content, memory_type):
    result = DeterministicExtractor().extract(_batch(tmp_path, content))
    assert len(result.candidates) == 1
    assert result.candidates[0].memory_type == memory_type
    assert result.candidates[0].commitment == Commitment.OBSERVED.value


def test_worker_does_not_reintroduce_quarantined_user_text_into_review(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    project = ProjectRegistry(vault).register(vault, project_id="project-a", proactive_capture=True)
    StateService(vault).init_project(project["project_id"], source={"type": "user", "reference": "extract-01"})
    migrate(vault)
    write_json(
        RuntimeConfig(vault).path,
        {
            "schema_version": 1,
            "mode": "SHADOW",
            "project_ids": [project["project_id"]],
            "local_model": None,
            "b1_human_approval": True,
            "transcript_roots": {"claude": [str(tmp_path)], "codex": [str(tmp_path)]},
        },
    )
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(vault.resolve()))
    transcript_root = tmp_path / slug
    transcript_root.mkdir()
    transcript = transcript_root / "extract-session.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "type": "user",
                "sessionId": "extract-session",
                "message": {"role": "user", "content": "Redis kullansak mı? Belki daha hızlı olabilir."},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    enqueue(
        vault,
        "claude",
        {"session_id": "extract-session", "cwd": str(vault), "transcript_path": str(transcript)},
    )

    result = Worker(vault).once()

    assert result["status"] == "PROCESSED"
    assert result["review_effect_count"] == 0
    assert ReviewStore(vault).list() == []

