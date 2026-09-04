"""Phase 15 baseline adapter tests.

These tests exercise the production compiler only through the adapter boundary;
metric calculation will remain independent in the following package.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from evals.baseline import (
    BASELINE_CAPABILITIES,
    BASELINE_PROVIDER_ID,
    BaselineAdapterError,
    BaselineContextProvider,
    normalize_context_compiler_output,
)
from evals.fixture_generator import build_vault
from evals.schema import load_fixture, load_tasks


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "evals" / "fixtures" / "phase15-contract.json"
TASK_PATH = ROOT / "evals" / "corpus" / "dev" / "eleven-capture-atomic-save-001.json"


@pytest.fixture
def fixture():
    return load_fixture(FIXTURE_PATH)


@pytest.fixture
def task(fixture):
    return load_tasks([TASK_PATH], fixture)[0]


@pytest.fixture
def generated_vault(fixture, tmp_path):
    return build_vault(fixture, tmp_path / "vault", seed=13, noise_count=3)


def test_baseline_normalizes_current_compiler_selection(task, generated_vault):
    result = BaselineContextProvider().select(task, generated_vault.root)
    selected_ids = {item.id for item in result.selected_items}

    assert result.task_id == task.task_id
    assert result.provider_id == BASELINE_PROVIDER_ID
    assert result.project_id == "eleven_capture"
    assert result.retrieval_scope == "default"
    assert result.source_memory_revision == 0
    assert result.capabilities == BASELINE_CAPABILITIES
    assert "mem_markdown_before_sqlite" in selected_ids
    assert "mem_promtgen_storage" not in selected_ids
    assert "mem_superseded_save_rule" not in selected_ids
    assert all(item.source_type == "memory" for item in result.selected_items)
    assert all(item.status == "active" for item in result.selected_items)
    assert {item.project_id for item in result.selected_items} <= {None, "eleven_capture"}


def test_baseline_is_deterministic_and_does_not_rank_by_prompt(task, generated_vault):
    provider = BaselineContextProvider()

    first = provider.select(task, generated_vault.root)
    second = provider.select(task, generated_vault.root)
    different_prompt = replace(
        task,
        prompt="Unrelated wording: what should this unrelated system retrieve?",
    )
    changed_prompt = provider.select(different_prompt, generated_vault.root)

    assert first.as_dict() == second.as_dict()
    assert first.as_dict() == changed_prompt.as_dict()


def test_baseline_without_current_project_returns_only_global_memory(task, generated_vault):
    global_task = replace(task, task_id="global_only", project_id=None)

    result = BaselineContextProvider().select(global_task, generated_vault.root)

    assert result.project_id is None
    assert result.selected_items
    assert all(item.project_id is None for item in result.selected_items)
    assert "mem_markdown_before_sqlite" not in {item.id for item in result.selected_items}


def test_normalizer_rejects_scope_mismatch(task):
    output = {
        "source_memory_revision": 0,
        "summary": {"project_id": task.project_id, "retrieval_scope": "all"},
        "top_memories": [],
    }

    with pytest.raises(BaselineAdapterError, match="default retrieval scope"):
        normalize_context_compiler_output(task, output)
