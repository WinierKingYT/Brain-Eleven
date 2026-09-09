"""R0 provider sockets: config, fail-closed behavior, and safety boundaries."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from brain_eleven.extraction.providers import create_semantic_provider
from brain_eleven.extraction.providers.codex_cli import CodexCLIProvider
from brain_eleven.extraction.providers.openai_api import OpenAIAPIProvider
from brain_eleven.extraction.semantic import SemanticStatus
from brain_eleven.retrieval.embedding_provider import (
    EmbeddingStatus,
    OpenAIEmbeddingProvider,
    UnavailableEmbeddingProvider,
    UnavailableReranker,
    create_embedding_provider,
    create_reranker,
)


def _message(content: str = "The project will use SQLite.") -> dict[str, object]:
    return {
        "content": content,
        "role": "user",
        "project_id": "brain-eleven",
        "evidence_id": "case-r0-001",
        "occurred_at": None,
    }


def _proposition() -> dict[str, object]:
    return {
        "candidate_id": "candidate-r0-001",
        "project_id": "brain-eleven",
        "claim_type": "decision",
        "subject": "database",
        "predicate": "uses",
        "value": "SQLite",
        "commitment": "explicit",
        "temporal_scope": None,
        "source_role": "user",
        "evidence_refs": ["case-r0-001"],
        "confidence_components": {"classification": 0.9},
        "correction_clues": None,
        "target_clues": None,
        "schema_version": "ig01-a-proposition-v1",
    }


class _FakeResponses:
    def __init__(self, payload: object = None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error

    def create(self, **kwargs: object) -> SimpleNamespace:
        del kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(output_text=json.dumps(self.payload))


class _FakeOpenAI:
    def __init__(self, payload: object = None, error: Exception | None = None) -> None:
        self.responses = _FakeResponses(payload, error)


def test_factory_defaults_to_unavailable_and_rejects_unknown(tmp_path):
    default = create_semantic_provider(config_path=tmp_path / "missing.json", environ={})
    assert default.provider_id == "unavailable"
    assert default.extract(_message()).status == SemanticStatus.SEMANTIC_UNAVAILABLE.value

    unknown = create_semantic_provider(
        config_path=tmp_path / "missing.json",
        environ={"IG_SEMANTIC_PROVIDER": "not-a-provider"},
    )
    assert unknown.provider_id == "unavailable"
    assert unknown.reason == "unknown_provider"


def test_factory_reads_config_switch_and_fails_closed_on_missing_key(tmp_path):
    config = tmp_path / "ig-provider-config.json"
    config.write_text('{"semantic_provider":"openai_api"}', encoding="utf-8")
    provider = create_semantic_provider(config_path=config, environ={})
    assert provider.provider_id == "unavailable"
    assert provider.reason == "missing_api_key"

    selected = create_semantic_provider(
        config_path=config,
        environ={"OPENAI_API_KEY": "not-a-secret"},
        openai_client=_FakeOpenAI({"propositions": []}),
    )
    assert selected.provider_id == "openai-api"


def test_openai_provider_accepts_valid_payload_and_rejects_extra_field():
    valid = OpenAIAPIProvider(client=_FakeOpenAI({"propositions": [_proposition()]}))
    result = valid.extract(_message())
    assert result.status == SemanticStatus.MEASURED.value
    assert len(result.propositions) == 1

    invalid = _proposition()
    invalid["canonical_commit"] = False
    result = OpenAIAPIProvider(client=_FakeOpenAI({"propositions": [invalid]})).extract(_message())
    assert result.status == SemanticStatus.INVALID_OUTPUT.value
    assert not result.propositions


def test_openai_timeout_is_unavailable():
    result = OpenAIAPIProvider(client=_FakeOpenAI(error=TimeoutError())).extract(_message())
    assert result.status == SemanticStatus.SEMANTIC_UNAVAILABLE.value
    assert result.error_code == "PROVIDER_CALL_FAILED"


def test_codex_cli_enforces_json_and_nonzero_contract(tmp_path):
    executable = tmp_path / "codex.exe"
    executable.write_text("placeholder", encoding="utf-8")

    def good_runner(command, **kwargs):
        del kwargs
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(json.dumps({"propositions": [_proposition()]}), encoding="utf-8")
        return SimpleNamespace(returncode=0)

    result = CodexCLIProvider(executable=str(executable), runner=good_runner).extract(_message())
    assert result.status == SemanticStatus.MEASURED.value
    assert result.propositions

    def bad_json_runner(command, **kwargs):
        del kwargs
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text("not-json", encoding="utf-8")
        return SimpleNamespace(returncode=0)

    result = CodexCLIProvider(executable=str(executable), runner=bad_json_runner).extract(_message())
    assert result.status == SemanticStatus.SEMANTIC_UNAVAILABLE.value

    def nonzero_runner(command, **kwargs):
        del command, kwargs
        return SimpleNamespace(returncode=1)

    result = CodexCLIProvider(executable=str(executable), runner=nonzero_runner).extract(_message())
    assert result.status == SemanticStatus.SEMANTIC_UNAVAILABLE.value


def test_provider_modules_do_not_import_canonical_stores():
    forbidden = {"MemoryStore", "StateStore", "lifecycle", "brain_eleven.memory", "brain_eleven.state"}
    root = Path(__file__).resolve().parents[1] / "brain_eleven" / "extraction" / "providers"
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        rendered = "\n".join(ast.unparse(node) for node in imports)
        assert not any(item in rendered for item in forbidden), path


def test_provider_log_records_are_content_free(caplog):
    evidence = "R0_PRIVATE_EVIDENCE_MUST_NOT_APPEAR_IN_LOGS"
    with caplog.at_level("INFO"):
        OpenAIAPIProvider(client=_FakeOpenAI({"propositions": []})).extract(_message(evidence))
    assert evidence not in caplog.text
    assert "semantic_provider_call" in caplog.text
    assert any(record.case_id.startswith("sha256:") for record in caplog.records)


def test_embedding_provider_is_real_or_explicitly_unavailable():
    unavailable = UnavailableEmbeddingProvider().embed_text("semantic text")
    assert unavailable.status == EmbeddingStatus.EMBEDDING_UNAVAILABLE.value
    assert unavailable.vectors == ()

    class Embeddings:
        def create(self, **kwargs):
            assert kwargs["input"] == ["one", "two"]
            return SimpleNamespace(data=[
                SimpleNamespace(index=1, embedding=[0.2, 0.3]),
                SimpleNamespace(index=0, embedding=[0.1, 0.4]),
            ])

    client = SimpleNamespace(embeddings=Embeddings())
    result = OpenAIEmbeddingProvider(client=client).embed(["one", "two"])
    assert result.status == EmbeddingStatus.EMBEDDING_AVAILABLE.value
    assert result.vectors == ((0.1, 0.4), (0.2, 0.3))

    configured = create_embedding_provider(environ={})
    assert configured.provider_id == "unavailable"


def test_local_embedding_and_reranker_are_real_model_adapters(monkeypatch):
    class FakeSentenceTransformer:
        def __init__(self, model_name, **kwargs):
            assert model_name == "fake/multilingual"
            assert kwargs["local_files_only"] is True

        def encode(self, texts, convert_to_numpy=True):
            assert convert_to_numpy is True
            return [[float(index + 1), 1.0] for index, _ in enumerate(texts)]

    class FakeCrossEncoder:
        def __init__(self, model_name, **kwargs):
            assert model_name == "fake/reranker"
            assert kwargs["local_files_only"] is True

        def predict(self, pairs):
            return [float(index) for index, _ in enumerate(pairs)]

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer, CrossEncoder=FakeCrossEncoder),
    )
    environ = {
        "IG_EMBEDDING_PROVIDER": "local",
        "IG_LOCAL_EMBEDDING_MODEL": "fake/multilingual",
        "IG_RERANKER_PROVIDER": "local",
        "IG_LOCAL_RERANKER_MODEL": "fake/reranker",
        "IG_LOCAL_MODELS_LOCAL_FILES_ONLY": "1",
    }
    embedding = create_embedding_provider(environ=environ)
    vectors = embedding.embed(["one", "two"])
    assert vectors.status == EmbeddingStatus.EMBEDDING_AVAILABLE.value
    assert vectors.provider_id == "sentence-transformers"
    assert vectors.vectors == ((1.0, 1.0), (2.0, 1.0))

    reranker = create_reranker(environ=environ)
    scores = reranker.rerank("query", ["one", "two"])
    assert scores.status == EmbeddingStatus.EMBEDDING_AVAILABLE.value
    assert scores.provider_id == "cross-encoder"
    assert scores.model == "fake/reranker"
    assert scores.scores == (0.0, 1.0)


def test_local_model_construction_failure_and_unselected_reranker_fail_closed(monkeypatch):
    class MissingModel:
        def __init__(self, *args, **kwargs):
            del args, kwargs
            raise OSError("model missing")

    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=MissingModel, CrossEncoder=MissingModel))
    embedding = create_embedding_provider(
        environ={"IG_EMBEDDING_PROVIDER": "local", "IG_LOCAL_MODELS_LOCAL_FILES_ONLY": "1"}
    )
    assert embedding.provider_id == "unavailable"
    assert embedding.embed(["text"]).status == EmbeddingStatus.EMBEDDING_UNAVAILABLE.value
    reranker = create_reranker(environ={})
    assert isinstance(reranker, UnavailableReranker)
    result = reranker.rerank("query", ["candidate"])
    assert result.status == EmbeddingStatus.EMBEDDING_UNAVAILABLE.value
    assert result.scores == ()
