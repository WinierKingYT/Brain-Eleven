from __future__ import annotations

import ast
from pathlib import Path

from brain_eleven.memory import MemoryStore as PackagedMemoryStore
from brain_eleven.graph import KnowledgeGraph as PackagedKnowledgeGraph
from brain_eleven.extraction import EntityExtractor as PackagedEntityExtractor
from brain_eleven.search import (
    HybridSearchEngine as PackagedHybridSearchEngine,
    MLRanker as PackagedMLRanker,
    MemoryRetriever as PackagedMemoryRetriever,
    SearchResult as PackagedSearchResult,
)
from brain_eleven.support import (
    AnomalyDetector as PackagedAnomalyDetector,
    CacheManager as PackagedCacheManager,
    DiskCache as PackagedDiskCache,
    LRUCache as PackagedLRUCache,
    MemorySummarizer as PackagedMemorySummarizer,
    jaccard_similarity as PackagedJaccardSimilarity,
    setup_logging as PackagedSetupLogging,
    tokenize as PackagedTokenize,
)
from brain_eleven.state import StateService as PackagedStateService
from authority.adapters import MemoryStore as AuthorityMemoryStore
from context_router.adapters import MemoryStore as RouterMemoryStore
from evals.authority_provider import MemoryStore as AuthorityProviderMemoryStore
from evals.compiler_v2_provider import MemoryStore as CompilerProviderMemoryStore
from evals.router_provider import MemoryStore as RouterProviderMemoryStore
from evals.router_provider import StateService as RouterProviderStateService
from evals.task_state_eval import MemoryStore as TaskStateMemoryStore
from evals.task_state_eval import StateService as TaskStateService


CALLERS = (
    "context_router/adapters.py",
    "authority/adapters.py",
    "evals/router_provider.py",
    "evals/authority_provider.py",
    "evals/compiler_v2_provider.py",
    "evals/task_state_eval.py",
    "evals/authority_evaluation.py",
    "evals/compiler_v2_evaluation.py",
    "evals/compiler_v2_benchmark.py",
    "evals/router_benchmark.py",
)

STATE_MUTATION_CALLERS = (
    "scripts/state.py",
    "scripts/state_boundary.py",
    "scripts/state_resolver.py",
)

MEMORY_MUTATION_CALLERS = (
    "scripts/memory-lifecycle.py",
    "scripts/memory_truth.py",
    "scripts/memory_provenance.py",
)

GRAPH_CALLERS = (
    "context_router/adapters.py",
    "scripts/entity_extractor.py",
    "scripts/chat_interface.py",
    "scripts/search-api.py",
)

ENTITY_CALLERS = (
    "scripts/memory_backup.py",
    "scripts/post_session_maintenance.py",
    "scripts/search-api.py",
)

SEARCH_CALLERS = (
    "scripts/chat_interface.py",
    "scripts/search-api.py",
)

SUPPORT_CALLERS = (
    "scripts/chat_interface.py",
    "scripts/post_session_maintenance.py",
    "scripts/search-api.py",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }


def test_core_and_evaluation_callers_use_packaged_store_surfaces() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative_path in CALLERS:
        imports = _imports(root / relative_path)
        assert "memory_store" not in imports, relative_path
        assert "state_store" not in imports, relative_path


def test_state_mutation_and_cli_callers_use_packaged_state_surface() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative_path in STATE_MUTATION_CALLERS:
        imports = _imports(root / relative_path)
        assert "state_store" not in imports, relative_path
        assert "brain_eleven.state" in imports, relative_path


def test_state_resolver_preserves_packaged_store_identity() -> None:
    from state_resolver import MemoryStore as ResolverMemoryStore
    from state_resolver import StateStore as ResolverStateStore

    from brain_eleven.memory import MemoryStore
    from brain_eleven.state import StateStore

    assert ResolverMemoryStore is MemoryStore
    assert ResolverStateStore is StateStore


def test_memory_mutation_callers_use_packaged_memory_surface() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative_path in MEMORY_MUTATION_CALLERS:
        imports = _imports(root / relative_path)
        assert "memory_store" not in imports, relative_path
        assert "brain_eleven.memory" in imports, relative_path


def test_memory_callers_preserve_canonical_object_identity() -> None:
    assert RouterMemoryStore is PackagedMemoryStore
    assert AuthorityMemoryStore is PackagedMemoryStore
    assert RouterProviderMemoryStore is PackagedMemoryStore
    assert AuthorityProviderMemoryStore is PackagedMemoryStore
    assert CompilerProviderMemoryStore is PackagedMemoryStore
    assert TaskStateMemoryStore is PackagedMemoryStore


def test_graph_callers_use_packaged_graph_surface() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative_path in GRAPH_CALLERS:
        imports = _imports(root / relative_path)
        assert "knowledge_graph" not in imports, relative_path
        assert "brain_eleven.graph" in imports, relative_path


def test_graph_callers_preserve_canonical_object_identity() -> None:
    from context_router.adapters import KnowledgeGraph as RouterKnowledgeGraph

    assert RouterKnowledgeGraph is PackagedKnowledgeGraph


def test_entity_callers_use_packaged_extraction_surface() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative_path in ENTITY_CALLERS:
        imports = _imports(root / relative_path)
        assert "entity_extractor" not in imports, relative_path
        assert "brain_eleven.extraction" in imports, relative_path


def test_extraction_surface_preserves_canonical_object_identity() -> None:
    from entity_extractor import EntityExtractor as LegacyEntityExtractor

    assert PackagedEntityExtractor is LegacyEntityExtractor


def test_state_callers_preserve_canonical_object_identity() -> None:
    assert RouterProviderStateService is PackagedStateService
    assert TaskStateService is PackagedStateService


def test_search_callers_use_packaged_search_surface() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative_path in SEARCH_CALLERS:
        imports = _imports(root / relative_path)
        assert "brain_eleven.search" in imports, relative_path
        source = (root / relative_path).read_text(encoding="utf-8")
        assert "memory-retriever.py" not in source, relative_path
        assert "hybrid-search.py" not in source, relative_path


def test_search_surface_preserves_cached_legacy_identity() -> None:
    import importlib

    legacy_retriever = importlib.import_module("memory_retriever")
    legacy_hybrid = importlib.import_module("hybrid_search")
    legacy_ranker = importlib.import_module("ml_ranker")

    assert PackagedMemoryRetriever is legacy_retriever.MemoryRetriever
    assert PackagedSearchResult is legacy_retriever.SearchResult
    assert PackagedHybridSearchEngine is legacy_hybrid.HybridSearchEngine
    assert PackagedMLRanker is legacy_ranker.MLRanker
    assert legacy_hybrid.MemoryRetriever is PackagedMemoryRetriever


def test_support_callers_use_packaged_support_surface() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative_path in SUPPORT_CALLERS:
        imports = _imports(root / relative_path)
        source = (root / relative_path).read_text(encoding="utf-8")
        assert "brain_eleven.support" in imports, relative_path
        for legacy_name in ("logging_config", "summarizer", "anomaly_detector", "cache_manager"):
            assert f"from {legacy_name} import" not in source, relative_path


def test_support_surface_preserves_cached_legacy_identity() -> None:
    import importlib

    legacy_logging = importlib.import_module("logging_config")
    legacy_summarizer = importlib.import_module("summarizer")
    legacy_anomaly = importlib.import_module("anomaly_detector")
    legacy_cache = importlib.import_module("cache_manager")

    assert PackagedSetupLogging is legacy_logging.setup_logging
    assert PackagedMemorySummarizer is legacy_summarizer.MemorySummarizer
    assert PackagedTokenize is legacy_summarizer.tokenize
    assert PackagedJaccardSimilarity is legacy_summarizer.jaccard_similarity
    assert PackagedAnomalyDetector is legacy_anomaly.AnomalyDetector
    assert PackagedLRUCache is legacy_cache.LRUCache
    assert PackagedDiskCache is legacy_cache.DiskCache
    assert PackagedCacheManager is legacy_cache.CacheManager
