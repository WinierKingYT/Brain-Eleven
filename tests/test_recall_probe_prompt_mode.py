import json

from brain_eleven.runtime.recall_probe import probe
from brain_eleven.runtime.context import _rank_prompt_candidates
from brain_eleven.retrieval.embedding_provider import (
    EmbeddingResult,
    EmbeddingStatus,
    RerankerResult,
)
from tests.test_memclaim01_claim_key import NEW_TIME, _accept, _review_item, _runtime


def test_prompt_mode_uses_each_user_prompt_context_and_keeps_memory_scoring(tmp_path, monkeypatch):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    _accept(vault, _review_item(tmp_path, vault, "alpha",
                                "We decided alpha is delivered at prompt time.", NEW_TIME))
    _accept(vault, _review_item(tmp_path, vault, "beta",
                                "We decided beta remains a validated memory.", NEW_TIME))
    questions = tmp_path / "prompt-questions.json"
    questions.write_text(json.dumps({"questions": [
        {"id": 1, "question": "Alpha?", "groups": [["alpha"]]},
        {"id": 2, "question": "Beta?", "groups": [["beta"]]},
        {"id": 3, "question": "Gamma?", "groups": [["gamma"]]},
    ]}), encoding="utf-8")

    calls = []

    def compile_context(vault_arg, root, request, **kwargs):
        calls.append((request, kwargs))
        return {
            "status": "SUCCESS",
            "context": "## TOP MEMORIES\n\nWe decided alpha is delivered at prompt time." if request == "Alpha?" else "",
            "selected_ids": [],
            "delivered": request == "Alpha?",
        }

    monkeypatch.setattr("brain_eleven.runtime.context.compile_context", compile_context)
    result = probe(vault, questions_path=questions, mode="prompt")
    by_id = {entry["id"]: entry for entry in result["results"]}

    assert result["mode"] == "prompt"
    assert (result["score"], result["of"]) == (1, 3)
    assert by_id[1]["status"] == "IN_CONTEXT"
    assert by_id[2]["status"] == "IN_MEMORY_NOT_DELIVERED"
    assert by_id[3]["status"] == "NOT_IN_MEMORY"
    assert by_id[2]["why_not_delivered"]
    assert [request for request, _ in calls] == ["Alpha?", "Beta?", "Gamma?"]
    assert all(options["client"] == "claude" and options["event"] == "UserPromptSubmit" for _, options in calls)
    assert [options["turn"] for _, options in calls] == ["recall-probe:1", "recall-probe:2", "recall-probe:3"]


def test_recall_probe_cli_defaults_to_bootstrap_and_accepts_prompt_mode(tmp_path, capsys, monkeypatch):
    from brain_eleven.__main__ import main

    vault, _ = _runtime(tmp_path, shadow_accept=True)
    _accept(vault, _review_item(tmp_path, vault, "alpha",
                                "We decided alpha is delivered at prompt time.", NEW_TIME))
    questions = tmp_path / "prompt-questions.json"
    questions.write_text(json.dumps({"questions": [
        {"id": 1, "question": "Alpha?", "groups": [["alpha"]]},
    ]}), encoding="utf-8")
    calls = []

    def compile_context(vault_arg, root, request, **kwargs):
        calls.append(kwargs.get("event"))
        return {"status": "SUCCESS", "context": "alpha", "selected_ids": [], "delivered": True}

    monkeypatch.setattr("brain_eleven.runtime.context.compile_context", compile_context)
    main(["--vault", str(vault), "recall-probe", "--questions", str(questions)])
    default_result = json.loads(capsys.readouterr().out)
    assert "mode" not in default_result
    assert calls == []

    main(["--vault", str(vault), "recall-probe", "--mode", "prompt", "--questions", str(questions)])
    prompt_result = json.loads(capsys.readouterr().out)
    assert prompt_result["mode"] == "prompt"
    assert prompt_result["score"] == 1
    assert calls == ["UserPromptSubmit"]


def test_prompt_semantic_reranker_respects_existing_score_floor(monkeypatch):
    monkeypatch.setattr(
        "brain_eleven.runtime.context.infer_memory_scope",
        lambda item: ("project", "project", item.get("scope_project")),
    )

    baseline = [
        {"memory_id": "current-high", "content": "current-high", "ranking_score": 0.92,
         "scope_project": "project"},
        {"memory_id": "current-floor", "content": "current-floor", "ranking_score": 0.80,
         "scope_project": "project"},
    ]
    ranked_pool = [
        *baseline,
        {"memory_id": "semantic-match", "content": "semantic-match", "ranking_score": 0.80,
         "scope_project": "project"},
        {"memory_id": "below-floor", "content": "below-floor", "ranking_score": 0.79,
         "scope_project": "project"},
        {"memory_id": "other-scope", "content": "other-scope", "ranking_score": 0.99,
         "scope_project": None},
    ]

    class FakeEmbeddingProvider:
        def __init__(self):
            self.texts = []

        def embed(self, texts):
            self.texts = list(texts)
            vectors = {
                "which decision?": (1.0, 0.0),
                "current-high": (0.3, 0.7),
                "current-floor": (0.0, 1.0),
                "semantic-match": (1.0, 0.0),
            }
            return EmbeddingResult(
                status=EmbeddingStatus.EMBEDDING_AVAILABLE.value,
                provider_id="test",
                model="test",
                vectors=tuple(vectors[text] for text in texts),
            )

    class FakeReranker:
        def __init__(self):
            self.texts = []

        def rerank(self, query, texts):
            self.texts = list(texts)
            scores = {"current-high": 0.5, "current-floor": 0.1, "semantic-match": 0.9}
            return RerankerResult(
                status=EmbeddingStatus.EMBEDDING_AVAILABLE.value,
                provider_id="test",
                model="test",
                scores=tuple(scores[text] for text in texts),
            )

    embeddings = FakeEmbeddingProvider()
    reranker = FakeReranker()
    selected = _rank_prompt_candidates(
        "which decision?",
        baseline,
        ranked_pool,
        project_id="project",
        stable_key=lambda item: item["memory_id"],
        embedding_provider=embeddings,
        reranker=reranker,
    )

    assert [item["memory_id"] for item in selected] == ["semantic-match", "current-high"]
    assert "below-floor" not in embeddings.texts
    assert "below-floor" not in reranker.texts
    assert "other-scope" not in reranker.texts


def test_prompt_semantic_retrieval_falls_back_to_legacy_order_when_unavailable(monkeypatch):
    monkeypatch.setattr(
        "brain_eleven.runtime.context.infer_memory_scope",
        lambda item: ("project", "project", item.get("scope_project")),
    )
    baseline = [
        {"memory_id": "first", "content": "first", "ranking_score": 0.9,
         "scope_project": "project"},
        {"memory_id": "second", "content": "second", "ranking_score": 0.8,
         "scope_project": "project"},
    ]
    pool = [*baseline, {"memory_id": "third", "content": "third", "ranking_score": 0.8,
                        "scope_project": "project"}]

    class UnavailableEmbeddingProvider:
        def embed(self, texts):
            return EmbeddingResult(
                status=EmbeddingStatus.EMBEDDING_UNAVAILABLE.value,
                provider_id="unavailable",
                model="unavailable",
            )

    class UnusedReranker:
        def rerank(self, query, texts):
            raise AssertionError("reranker must not run without embeddings")

    selected = _rank_prompt_candidates(
        "query",
        baseline,
        pool,
        project_id="project",
        stable_key=lambda item: item["memory_id"],
        embedding_provider=UnavailableEmbeddingProvider(),
        reranker=UnusedReranker(),
    )

    assert selected == baseline
