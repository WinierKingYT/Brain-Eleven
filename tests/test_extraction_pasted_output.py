"""Pasted tool/terminal output in a user turn is evidence, never a commitment.

2026-09-29: user turns that pasted Codex tool logs, git output and graphify
progress lines became canonical requirements, blockers, the current
milestone and "decision" memories, and were shown at every SessionStart.
"""

from __future__ import annotations

import json

import pytest

from evidence import TranscriptReader
from extraction import DeterministicExtractor, NewMemoryCandidate, StateMutationProposal


def _extract(tmp_path, content):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(json.dumps({"role": "user", "content": content}) + "\n", encoding="utf-8")
    batch = TranscriptReader().read(transcript, session_id="session_01", project_id="brain-eleven",
                                    captured_at="2026-09-29T10:00:00Z")
    return DeterministicExtractor().extract(batch)


PASTED = [
    "[15] tool exec result: Script completed\nWall time 1.3 seconds\nOutput:\n\n===== ROOT =====\nThe build is currently failing.",
    "[30] tool exec result: Script completed\nWall time 1.2 seconds\nOutput:\n\n 136: ## Case schema\n 137: Every case must have an id.",
    "diff --git a/worker.py b/worker.py\n-    old = 1\n+    new = 2  # we decided to use two",
    "if it persists, please report the file(s) (#1666).\r\n[graphify extract] scanning C:\\Users\\faruk",
    "PS C:\\Users\\faruk\\Documents\\Brain-Eleven> git status\nerror: build is still failing",
    "IG01-A-EVALUATION-CONTRACT.md:252:| Latency | p50 and p95 must be reported over 5 samples",
]


@pytest.mark.parametrize("content", PASTED)
def test_pasted_machine_output_is_quarantined_not_committed(tmp_path, content):
    result = _extract(tmp_path, content)

    assert not [c for c in result.candidates if isinstance(c, (StateMutationProposal, NewMemoryCandidate))]
    # Nothing reaches canonical state or memory; the machine output itself is
    # quarantined as pasted output (a leading prose fragment may be quarantined
    # for its own reason).
    assert "PASTED_OUTPUT" in {q.reason for q in result.quarantined}


def test_plain_user_prose_is_still_captured(tmp_path):
    result = _extract(tmp_path, "SQLite kullanacağız çünkü uygulama tamamen lokal. Nightly build is currently failing on Windows.")

    assert any(isinstance(c, NewMemoryCandidate) for c in result.candidates)
    assert any(isinstance(c, StateMutationProposal) for c in result.candidates)
    assert not any(q.reason == "PASTED_OUTPUT" for q in result.quarantined)


@pytest.mark.parametrize("content", [
    "Plan:\n1: kararı yaz\nSQLite kullanacağız çünkü uygulama lokal.",
    "2026: yeni plan olmalı ve SQLite kullanacağız.",
    "=== Özet ===\nSQLite kullanacağız çünkü uygulama tamamen lokal.",
])
def test_user_typed_lists_and_headings_are_not_pasted_output(tmp_path, content):
    result = _extract(tmp_path, content)

    assert not any(q.reason == "PASTED_OUTPUT" for q in result.quarantined)
    assert result.candidates
