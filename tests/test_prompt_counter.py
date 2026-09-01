"""Regression tests for the UserPromptSubmit checkpoint counter."""

import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "prompt_counter", Path(__file__).parent.parent / "scripts" / "prompt-counter.py"
)
prompt_counter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prompt_counter)


def test_counter_persists_prompts_and_creates_interval_checkpoint(tmp_path):
    first = prompt_counter.record_prompt(tmp_path, checkpoint_interval=3, now="2026-09-01T10:00:00Z")
    second = prompt_counter.record_prompt(tmp_path, checkpoint_interval=3, now="2026-09-01T10:01:00Z")
    third = prompt_counter.record_prompt(tmp_path, checkpoint_interval=3, now="2026-09-01T10:02:00Z")

    assert [first["count"], second["count"], third["count"]] == [1, 2, 3]
    assert third["checkpoint_created"] is True
    checkpoint = Path(third["checkpoint_path"])
    assert checkpoint.name == "prompt-000003.md"
    assert "Prompt count: 3" in checkpoint.read_text(encoding="utf-8")
    state = json.loads((tmp_path / ".claude" / "prompt-counter-state.json").read_text(encoding="utf-8"))
    assert state["count"] == 3
    assert state["last_checkpoint_at"] == "2026-09-01T10:02:00Z"


def test_counter_rejects_invalid_checkpoint_interval(tmp_path):
    with pytest.raises(ValueError):
        prompt_counter.record_prompt(tmp_path, checkpoint_interval=0)


def test_counter_fails_visibly_for_corrupt_state(tmp_path):
    state = tmp_path / ".claude" / "prompt-counter-state.json"
    state.parent.mkdir()
    state.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(prompt_counter.PromptCounterError):
        prompt_counter.record_prompt(tmp_path)
