"""Synthetic evaluation vaults must remain safe, offline, and reproducible."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from evals.fixture_generator import (
    CANONICAL_MEMORY_RELATIVE_PATH,
    FIXTURE_MANIFEST_NAME,
    FixtureGenerationError,
    build_vault,
)
from evals.schema import load_fixture


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "evals" / "fixtures" / "phase15-contract.json"
_compiler_spec = importlib.util.spec_from_file_location(
    "phase15_fixture_context_compiler", ROOT / "scripts" / "context-compiler.py"
)
_compiler_module = importlib.util.module_from_spec(_compiler_spec)
_compiler_spec.loader.exec_module(_compiler_module)
ContextCompiler = _compiler_module.ContextCompiler


@pytest.fixture
def fixture():
    return load_fixture(FIXTURE_PATH)


def _canonical(root: Path):
    return json.loads((root / CANONICAL_MEMORY_RELATIVE_PATH).read_text(encoding="utf-8"))


def test_generator_writes_canonical_memory_and_manifest(fixture, tmp_path):
    generated = build_vault(fixture, tmp_path / "vault", seed=17, noise_count=3)

    canonical = _canonical(generated.root)
    manifest = json.loads((generated.root / FIXTURE_MANIFEST_NAME).read_text(encoding="utf-8"))

    assert canonical["schema_version"] == 2
    assert canonical["revision"] == 0
    assert canonical["summary"]["fixture_id"] == "phase15_contract"
    assert len(canonical["validated_memory"]) == len(fixture.memories) + 3
    assert manifest["memory_ids"] == list(generated.memory_ids)
    assert generated.memory_ids[-3:] == ("noise_17_0000", "noise_17_0001", "noise_17_0002")


def test_generator_is_byte_for_byte_deterministic_for_same_seed(fixture, tmp_path):
    first = build_vault(fixture, tmp_path / "first", seed=11, noise_count=2)
    second = build_vault(fixture, tmp_path / "second", seed=11, noise_count=2)

    assert (first.root / CANONICAL_MEMORY_RELATIVE_PATH).read_bytes() == (
        second.root / CANONICAL_MEMORY_RELATIVE_PATH
    ).read_bytes()
    assert (first.root / FIXTURE_MANIFEST_NAME).read_bytes() == (
        second.root / FIXTURE_MANIFEST_NAME
    ).read_bytes()


def test_generator_varies_noise_deterministically_by_seed(fixture, tmp_path):
    first = build_vault(fixture, tmp_path / "first", seed=1, noise_count=1)
    second = build_vault(fixture, tmp_path / "second", seed=2, noise_count=1)

    assert _canonical(first.root)["validated_memory"] != _canonical(second.root)["validated_memory"]
    assert first.memory_ids[-1] == "noise_1_0000"
    assert second.memory_ids[-1] == "noise_2_0000"


def test_generator_preserves_scope_and_lifecycle_labels(fixture, tmp_path):
    generated = build_vault(fixture, tmp_path / "vault", seed=0)
    records = {record["memory_id"]: record for record in _canonical(generated.root)["validated_memory"]}

    assert records["mem_markdown_source_of_truth"]["scope"] == "global"
    assert records["mem_markdown_source_of_truth"]["project_id"] == ""
    assert records["mem_markdown_before_sqlite"]["scope"] == "project"
    assert records["mem_markdown_before_sqlite"]["project_id"] == "eleven_capture"
    assert records["mem_superseded_save_rule"]["status"] == "superseded"


def test_generated_vault_is_consumable_by_the_current_project_safe_compiler(fixture, tmp_path):
    generated = build_vault(fixture, tmp_path / "vault", seed=7)

    compiled = ContextCompiler(str(generated.root), project_id="eleven_capture").compile()
    selected_ids = {memory["memory_id"] for memory in compiled["top_memories"]}

    assert "mem_markdown_before_sqlite" in selected_ids
    assert "mem_promtgen_storage" not in selected_ids
    assert "mem_superseded_save_rule" not in selected_ids


def test_generator_refuses_to_overwrite_nonempty_target(fixture, tmp_path):
    target = tmp_path / "existing"
    target.mkdir()
    (target / "user-file.txt").write_text("do not replace", encoding="utf-8")

    with pytest.raises(FixtureGenerationError, match="refusing to overwrite"):
        build_vault(fixture, target)

    assert (target / "user-file.txt").read_text(encoding="utf-8") == "do not replace"


@pytest.mark.parametrize("seed,noise_count", [(-1, 0), (0, -1)])
def test_generator_rejects_negative_parameters(fixture, tmp_path, seed, noise_count):
    with pytest.raises(FixtureGenerationError, match="non-negative"):
        build_vault(fixture, tmp_path / "vault", seed=seed, noise_count=noise_count)
