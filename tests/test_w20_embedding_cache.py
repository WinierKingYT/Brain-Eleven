"""Durability and live-reader tests for the legacy embedding cache."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


embedding_generator = load_module("w20_embedding_generator", "embedding-generator.py")
semantic_search = load_module("w20_semantic_search", "semantic-search.py")
EmbeddingGenerator = embedding_generator.EmbeddingGenerator
SemanticSearchEngine = semantic_search.SemanticSearchEngine


def enable_fake_provider(generator):
    class FakeEmbeddings:
        def create(self, *, input, model):
            vector = generator._embed_fallback(input).tolist()
            return SimpleNamespace(data=[SimpleNamespace(embedding=vector)])

    generator.use_openai = True
    generator.client = SimpleNamespace(embeddings=FakeEmbeddings())
    return generator


def add_entry(generator, memory_id, content):
    vector = np.zeros(generator.dimension, dtype=np.float32)
    vector[0] = 1.0
    generator.embeddings[memory_id] = generator._cache_entry(content, vector)


def read_cache(generator):
    return json.loads(generator.embedding_cache.read_text(encoding="utf-8"))


def test_save_failure_preserves_previous_snapshot(tmp_path, monkeypatch):
    generator = enable_fake_provider(EmbeddingGenerator(str(tmp_path)))
    add_entry(generator, "one", "first")
    assert generator.save() is True
    before = generator.embedding_cache.read_bytes()

    add_entry(generator, "two", "second")

    def fail_write(*args, **kwargs):
        raise OSError("simulated interrupted publication")

    monkeypatch.setattr(embedding_generator, "write_json", fail_write)
    assert generator.save() is False
    assert generator.embedding_cache.read_bytes() == before
    assert set(read_cache(generator)["embeddings"]) == {"one"}


def test_concurrent_generators_merge_distinct_entries(tmp_path):
    first = enable_fake_provider(EmbeddingGenerator(str(tmp_path)))
    second = enable_fake_provider(EmbeddingGenerator(str(tmp_path)))
    add_entry(first, "one", "first")
    add_entry(second, "two", "second")

    assert first.save() is True
    assert second.save() is True
    assert set(read_cache(first)["embeddings"]) == {"one", "two"}


def test_incompatible_same_id_fails_without_overwriting_prior_cache(tmp_path):
    first = enable_fake_provider(EmbeddingGenerator(str(tmp_path)))
    add_entry(first, "same", "original")
    assert first.save() is True
    before = first.embedding_cache.read_bytes()

    second = enable_fake_provider(EmbeddingGenerator(str(tmp_path)))
    add_entry(second, "same", "changed content")
    assert second.save() is False
    assert second.embedding_cache.read_bytes() == before
    assert read_cache(second)["embeddings"]["same"]["content_hash"] == first.embeddings["same"]["content_hash"]


def test_save_creates_cache_parent_and_single_sidecar_lock(tmp_path):
    vault = tmp_path / "new-vault"
    generator = enable_fake_provider(EmbeddingGenerator(str(vault)))
    add_entry(generator, "one", "first")

    assert generator.save() is True
    assert generator.embedding_cache.exists()
    assert generator.embedding_lock == generator.embedding_cache.with_name("embeddings.json.lock")
    assert generator.embedding_lock.exists()
    assert not generator.embedding_cache.with_name("embeddings.json.lock.lock").exists()


def test_clear_cache_is_durable_after_reconstruction(tmp_path):
    generator = enable_fake_provider(EmbeddingGenerator(str(tmp_path)))
    add_entry(generator, "one", "first")
    assert generator.save() is True
    assert generator.clear_cache() is True

    reconstructed = EmbeddingGenerator(str(tmp_path))
    assert reconstructed.embeddings == {}
    assert read_cache(generator)["embeddings"] == {}


def test_clear_failure_is_explicit_and_restores_local_snapshot(tmp_path, monkeypatch):
    generator = enable_fake_provider(EmbeddingGenerator(str(tmp_path)))
    add_entry(generator, "one", "first")
    assert generator.save() is True
    before = generator.embedding_cache.read_bytes()

    def fail_write(*args, **kwargs):
        raise OSError("simulated clear failure")

    monkeypatch.setattr(embedding_generator, "write_json", fail_write)
    assert generator.clear_cache() is False
    assert generator.embedding_cache.read_bytes() == before
    assert set(generator.embeddings) == {"one"}


def test_stale_generator_cannot_resurrect_durable_clear(tmp_path):
    writer = enable_fake_provider(EmbeddingGenerator(str(tmp_path)))
    add_entry(writer, "one", "first")
    assert writer.save() is True

    stale = enable_fake_provider(EmbeddingGenerator(str(tmp_path)))
    clearer = enable_fake_provider(EmbeddingGenerator(str(tmp_path)))
    assert clearer.clear_cache() is True
    assert stale.save() is True
    assert read_cache(stale)["embeddings"] == {}


def test_process_concurrency_retains_distinct_entries(tmp_path):
    worker = """
import importlib.util
import sys
from pathlib import Path
import numpy as np
spec = importlib.util.spec_from_file_location('embedding_generator', Path('scripts') / 'embedding-generator.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
generator = module.EmbeddingGenerator(sys.argv[1])
generator.use_openai = True
generator.client = object()
vector = np.zeros(generator.dimension, dtype=np.float32)
vector[0] = 1.0
generator.embeddings[sys.argv[2]] = generator._cache_entry(sys.argv[3], vector)
if not generator.save():
    raise SystemExit(2)
"""
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", worker, os.fspath(tmp_path), memory_id, content],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        for memory_id, content in (("one", "first"), ("two", "second"))
    ]
    outcomes = [process.communicate(timeout=30) for process in processes]
    assert all(process.returncode == 0 for process in processes), outcomes
    cache = json.loads((tmp_path / ".claude" / "embeddings.json").read_text(encoding="utf-8"))
    assert set(cache["embeddings"]) == {"one", "two"}


def test_semantic_search_refreshes_cache_without_restart(tmp_path):
    engine = SemanticSearchEngine(str(tmp_path))
    enable_fake_provider(engine.generator)
    writer = enable_fake_provider(EmbeddingGenerator(str(tmp_path)))
    memory = {"memory_id": "one", "content": "first", "type": "decision"}
    writer.batch_embed([memory])
    assert writer.save() is True

    results = engine.search("first", [memory], top_k=1)
    assert [result["memory_id"] for result in results] == ["one"]


def test_malformed_or_legacy_entries_are_rejected(tmp_path):
    vault = tmp_path / ".claude"
    vault.mkdir()
    cache = vault / "embeddings.json"
    cache.write_text(
        json.dumps({"embeddings": {"legacy": [0.1, 0.2], "bad": {"vector": [0.1]}}}),
        encoding="utf-8",
    )
    generator = enable_fake_provider(EmbeddingGenerator(str(tmp_path)))

    assert generator.get_embedding("legacy", "legacy") is None
    assert generator.get_embedding("bad", "bad") is None


def test_save_does_not_replace_corrupt_snapshot(tmp_path):
    vault = tmp_path / ".claude"
    vault.mkdir()
    cache = vault / "embeddings.json"
    cache.write_text('{"embeddings":', encoding="utf-8")
    before = cache.read_bytes()
    generator = enable_fake_provider(EmbeddingGenerator(str(tmp_path)))
    add_entry(generator, "one", "first")

    assert generator.save() is False
    assert cache.read_bytes() == before
