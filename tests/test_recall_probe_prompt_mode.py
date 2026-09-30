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

    def request_service(vault_arg, route, payload, timeout):
        calls.append((route, payload, timeout))
        return {
            "status": "SUCCESS",
            "context": "## TOP MEMORIES\n\nWe decided alpha is delivered at prompt time."
            if payload["request"] == "Alpha?" else "",
            "selected_ids": [],
            "delivered": payload["request"] == "Alpha?",
        }

    monkeypatch.setattr("brain_eleven.runtime.launcher.ensure_service", lambda *args, **kwargs: True)
    monkeypatch.setattr("brain_eleven.runtime.launcher.request_service", request_service)
    monkeypatch.setattr("brain_eleven.runtime.context.compile_bootstrap",
                        lambda *args, **kwargs: {"context": "", "selected_ids": []})
    result = probe(vault, questions_path=questions, mode="prompt")
    by_id = {entry["id"]: entry for entry in result["results"]}

    assert result["mode"] == "prompt"
    assert (result["score"], result["of"]) == (1, 3)
    assert by_id[1]["status"] == "IN_CONTEXT"
    assert by_id[2]["status"] == "IN_MEMORY_NOT_DELIVERED"
    assert by_id[3]["status"] == "NOT_IN_MEMORY"
    assert by_id[2]["why_not_delivered"]
    assert [payload["request"] for _, payload, _ in calls] == ["Alpha?", "Beta?", "Gamma?"]
    assert all(route == "/api/context" and payload["client"] == "codex"
               and payload["event"] == "UserPromptSubmit" and timeout == 2
               for route, payload, timeout in calls)
    assert [payload["turn"] for _, payload, _ in calls] == [
        "recall-probe:1", "recall-probe:2", "recall-probe:3"]


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

    def request_service(vault_arg, route, payload, timeout):
        calls.append(payload.get("event"))
        return {"status": "SUCCESS", "context": "alpha", "selected_ids": [], "delivered": True}

    monkeypatch.setattr("brain_eleven.runtime.launcher.ensure_service", lambda *args, **kwargs: True)
    monkeypatch.setattr("brain_eleven.runtime.launcher.request_service", request_service)
    monkeypatch.setattr("brain_eleven.runtime.context.compile_bootstrap",
                        lambda *args, **kwargs: {"context": "", "selected_ids": []})
    main(["--vault", str(vault), "recall-probe", "--questions", str(questions)])
    default_result = json.loads(capsys.readouterr().out)
    assert "mode" not in default_result
    assert calls == []

    main(["--vault", str(vault), "recall-probe", "--mode", "prompt", "--questions", str(questions)])
    prompt_result = json.loads(capsys.readouterr().out)
    assert prompt_result["mode"] == "prompt"
    assert prompt_result["score"] == 1
    assert calls == ["UserPromptSubmit"]


def test_prompt_semantic_reranker_admits_lower_ranked_same_scope_candidates(monkeypatch):
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
                "below-floor": (0.9, 0.1),
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
            scores = {"current-high": 0.5, "current-floor": 0.1, "semantic-match": 0.9,
                      "below-floor": 0.95}
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

    # A memory ranked below the current V1 top-five (and below its lowest
    # score) is exactly the W39 case: it must be able to win the slot.
    assert [item["memory_id"] for item in selected] == ["below-floor", "semantic-match"]
    assert "below-floor" in reranker.texts
    # Scope tiers stay fixed: a higher-scored memory from a tier that is not
    # represented in the baseline never enters.
    assert "other-scope" not in embeddings.texts
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


def _latency_fakes():
    class Embeddings:
        provider_id, model = "latency-test", "latency-test"

        def __init__(self):
            self.calls = []

        def embed(self, texts):
            self.calls.append(list(texts))
            return EmbeddingResult(
                status=EmbeddingStatus.EMBEDDING_AVAILABLE.value, provider_id="t", model="t",
                vectors=tuple((1.0, 0.0) if text in {"q", "m19"} else (0.0, 1.0) for text in texts),
            )

    class Reranker:
        def __init__(self):
            self.texts = []

        def rerank(self, query, texts):
            self.texts = list(texts)
            return RerankerResult(
                status=EmbeddingStatus.EMBEDDING_AVAILABLE.value, provider_id="t", model="t",
                scores=tuple(1.0 if text == "m19" else 0.0 for text in texts),
            )

    return Embeddings(), Reranker()


def test_prompt_rerank_shortlists_cross_encoder_and_reuses_memory_vectors(monkeypatch):
    import brain_eleven.runtime.context as context

    monkeypatch.setattr(context, "infer_memory_scope", lambda item: ("project", "p", "project"))
    monkeypatch.setattr(context, "_EMBEDDING_CACHE", {})
    pool = [{"memory_id": f"m{i}", "content": f"m{i}", "ranking_score": 1 - i / 100}
            for i in range(40)]
    embeddings, reranker = _latency_fakes()

    def run():
        return context._rank_prompt_candidates(
            "q", pool[:5], pool, project_id="project", stable_key=lambda item: item["memory_id"],
            embedding_provider=embeddings, reranker=reranker)

    # The service warm-up embeds the pool; a prompt then embeds only itself.
    context._embed_cached(embeddings, [item["content"] for item in pool])
    first = run()
    assert first[0]["memory_id"] == "m19"
    assert len(first) == 5
    assert len(reranker.texts) == context.RERANK_SHORTLIST
    assert "m19" in reranker.texts
    run()
    # Warm-up plus the query once; the second prompt embeds nothing new.
    assert embeddings.calls[1] == ["q"]
    assert len(embeddings.calls) == 2


def test_prompt_providers_are_built_once_per_config(tmp_path, monkeypatch):
    import brain_eleven.runtime.context as context
    import brain_eleven.retrieval.embedding_provider as providers

    built = []
    monkeypatch.setattr(context, "_PROVIDER_CACHE", {})
    monkeypatch.setattr(providers, "create_embedding_provider", lambda **kw: built.append(kw) or "E")
    monkeypatch.setattr(providers, "create_reranker", lambda **kw: "R")
    config = tmp_path / "ig-provider-config.json"
    config.write_text("{}", encoding="utf-8")

    assert context._prompt_providers(config) == ("E", "R")
    assert context._prompt_providers(config) == ("E", "R")
    assert len(built) == 1
    assert built[0]["environ"]["IG_LOCAL_MODELS_LOCAL_FILES_ONLY"] == "true"


def test_prompt_never_waits_for_loading_providers(tmp_path, monkeypatch):
    import brain_eleven.runtime.context as context

    monkeypatch.setattr(context, "_PROVIDER_CACHE", {})
    started = []
    monkeypatch.setattr(context, "warm_prompt_providers", lambda path, texts=(): started.append(path))
    config = tmp_path / "ig-provider-config.json"
    config.write_text("{}", encoding="utf-8")

    # Another thread is loading or warming: the prompt returns at once, even
    # when providers are already cached, and starts nothing.
    import threading
    holding, release = threading.Event(), threading.Event()

    def hold():
        with context._PROVIDER_LOCK:
            holding.set()
            release.wait(5)

    holder = threading.Thread(target=hold)
    holder.start()
    holding.wait(5)
    try:
        assert context._prompt_providers(config, block=False) is None
    finally:
        release.set()
        holder.join(5)
    assert started == []

    # Providers already cached under the real key, but warm-up still holds the
    # lock: the prompt still gets None instead of competing with the warm-up.
    import brain_eleven.retrieval.embedding_provider as providers
    monkeypatch.setattr(providers, "create_embedding_provider", lambda **kw: "E")
    monkeypatch.setattr(providers, "create_reranker", lambda **kw: "R")
    assert context._prompt_providers(config) == ("E", "R")
    holding.clear(); release.clear()
    holder = threading.Thread(target=hold)
    holder.start()
    holding.wait(5)
    try:
        assert context._prompt_providers(config, block=False) is None
    finally:
        release.set()
        holder.join(5)
    assert context._prompt_providers(config, block=False) == ("E", "R")
    assert started == []
    # Nobody is loading and nothing is cached: the prompt still returns at
    # once but starts a load.
    context._PROVIDER_CACHE.clear()
    assert context._prompt_providers(config, block=False) is None
    for _ in range(50):
        if started:
            break
        __import__("time").sleep(.01)
    assert started == [config]


def test_prompt_does_not_embed_a_large_backlog_inline(monkeypatch):
    import brain_eleven.runtime.context as context

    monkeypatch.setattr(context, "_EMBEDDING_CACHE", {})
    embeddings, _ = _latency_fakes()
    texts = [f"t{i}" for i in range(20)]

    assert context._embed_cached(embeddings, texts, inline_limit=8) is None
    for _ in range(100):
        if len(context._EMBEDDING_CACHE) == 20:
            break
        __import__("time").sleep(.01)
    # The backlog was embedded in the background; the next prompt is served.
    assert len(context._embed_cached(embeddings, texts, inline_limit=8)) == 20


def test_prompt_rerank_respects_its_time_budget(monkeypatch):
    import brain_eleven.runtime.context as context

    monkeypatch.setattr(context, "infer_memory_scope", lambda item: ("project", "p", "project"))
    monkeypatch.setattr(context, "_EMBEDDING_CACHE", {})
    pool = [{"memory_id": f"m{i}", "content": f"m{i}", "ranking_score": 1 - i / 100} for i in range(40)]
    embeddings, reranker = _latency_fakes()
    context._embed_cached(embeddings, ["q", *(item["content"] for item in pool)])

    def run():
        return context._rank_prompt_candidates(
            "q", pool[:5], pool, project_id="project", stable_key=lambda item: item["memory_id"],
            embedding_provider=embeddings, reranker=reranker)

    # A slow cross-encoder (measured 0.1 s per pair) fits 9 pairs in 0.9 s.
    monkeypatch.setattr(context, "_RERANK_PAIR_SECONDS", [0.1])
    assert run()[0]["memory_id"] == "m19"
    assert 5 <= len(reranker.texts) <= 9
    # Too slow to rerank even the five slots: keep the V1 order untouched.
    reranker.texts = []
    monkeypatch.setattr(context, "_RERANK_PAIR_SECONDS", [1.0])
    assert [item["memory_id"] for item in run()] == ["m0", "m1", "m2", "m3", "m4"]
    assert reranker.texts == []


def test_prompt_probe_fails_closed_when_live_service_is_unavailable(tmp_path, monkeypatch):
    vault, _ = _runtime(tmp_path, shadow_accept=True)
    questions = tmp_path / "q.json"
    questions.write_text(json.dumps({"questions": [{"id": 1, "question": "Alpha?", "groups": [["alpha"]]}]}),
                         encoding="utf-8")
    monkeypatch.setattr("brain_eleven.runtime.launcher.ensure_service", lambda *args, **kwargs: False)
    monkeypatch.setattr("brain_eleven.runtime.launcher.request_service",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not call")))
    monkeypatch.setattr("brain_eleven.runtime.context.compile_bootstrap",
                        lambda *args, **kwargs: {"context": "", "selected_ids": []})
    result = probe(vault, questions_path=questions, mode="prompt")

    assert result["score"] == 0
    assert result["prompt_context_statuses"] == {"1": "SERVICE_UNAVAILABLE"}
    assert result["results"][0]["status"] == "NOT_IN_MEMORY"


def test_service_stays_up_longer_while_prompt_models_are_loaded(monkeypatch):
    import brain_eleven.runtime.context as context
    from brain_eleven.runtime import service

    class Loaded:
        provider_id = "sentence-transformers"

    class Unavailable:
        provider_id = "unavailable"

    monkeypatch.setattr(context, "_PROVIDER_CACHE", {})
    assert service.idle_limit_seconds() == service.IDLE_LIMIT_SECONDS
    context._PROVIDER_CACHE["k"] = (Unavailable(), None)
    assert service.idle_limit_seconds() == service.IDLE_LIMIT_SECONDS
    context._PROVIDER_CACHE["k"] = (Loaded(), None)
    assert service.idle_limit_seconds() == service.PROMPT_MODELS_IDLE_LIMIT_SECONDS
