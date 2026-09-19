#!/usr/bin/env python3
"""
Brain-Eleven v3 REST API
Complete API server with hybrid search, ML ranking, and memory management
"""

from fastapi import FastAPI, HTTPException, Query, Body, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Literal
import hmac
import json
import hashlib
import os
import re
import sys
import importlib.util
import uuid
import copy
from pathlib import Path
import logging

# On Windows, the console's active codepage (e.g. cp1254) often can't encode
# the emoji used in log/print statements throughout scripts/*, which raises
# UnicodeEncodeError and crashes startup entirely. Force UTF-8 stdout/stderr
# up front so this entrypoint is codepage-independent. No-op on platforms
# where streams are already UTF-8 (Linux/Docker) or don't support reconfigure.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# Direct execution needs the repository package root.  The scripts directory
# is used below as a filesystem location for hyphenated compatibility modules;
# it is no longer injected as a second import root.
SCRIPTS_DIR = Path(__file__).parent
REPO_ROOT = SCRIPTS_DIR.resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load .env for local runs (docker-compose already injects real env vars
# directly, so this is a no-op there - python-dotenv never overrides an
# already-set variable by default).
try:
    from dotenv import load_dotenv
    load_dotenv(SCRIPTS_DIR.parent / ".env")
except ImportError:
    pass  # python-dotenv not installed - fall back to real env vars only


def _load_hyphenated_module(name: str, filename: str):
    """Load a module whose filename uses hyphens (not valid for `import`)."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Import our components. cache_manager and logging_config use underscores
# and are directly importable; the remaining legacy validator/embedding
# adapters still use importlib until their bounded migrations are complete.
try:
    _memory_validator = _load_hyphenated_module("memory_validator", "memory-validator.py")

    from brain_eleven.search import (
        HybridSearchEngine,
        HeuristicRanker as PackagedHeuristicRanker,
        MemoryRetriever,
        SearchResult,
    )

    # Keep the API's historical names stable while the search surface moves
    # behind the package boundary.
    HeuristicRanker = PackagedHeuristicRanker
    MemoryValidator = _memory_validator.MemoryValidator

    from brain_eleven.support import CacheManager, AnomalyDetector, MemorySummarizer
    from brain_eleven.graph import KnowledgeGraph
    from brain_eleven.extraction import EntityExtractor
    from brain_eleven.runtime.chat_interface import ChatAgent
    from brain_eleven.memory import (
        filter_memories,
        infer_memory_scope,
        scoped_fingerprint,
    )
    from brain_eleven.projects.registry import (
        ProjectRegistry,
        ProjectRegistryError,
        registry_path as project_registry_path,
    )
    from brain_eleven.memory import MemoryStore, MemoryStoreConflict, no_change
    from brain_eleven.runtime.capture_safety import CaptureSafetyError, evaluate_capture
except ImportError as e:
    print(f"Warning: Could not import components: {e}")

# Setup logging
from brain_eleven.support import setup_logging
logger = setup_logging(__name__)


# ============================================================================
# API Models
# ============================================================================

class MemoryCreate(BaseModel):
    type: str = Field(..., description="Memory type: decision, lesson, open_loop, etc")
    content: str = Field(..., description="Memory content")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    scope: Optional[Literal["global", "project"]] = None
    project: str = Field(default="", description="Optional originating project identifier")
    project_label: str = Field(default="", description="Human-readable project label")
    project_id: str = Field(
        default="", max_length=256, description="Opaque project namespace identifier"
    )
    project_root: Optional[str] = Field(
        default=None,
        max_length=4096,
        description="Project root used only to derive project_id",
    )
    timestamp: Optional[str] = None

class MemoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: Optional[str] = None
    confidence: Optional[float] = None
    status: Optional[str] = None
    resolved_by: Optional[str] = Field(default=None, max_length=256)
    reason: Optional[str] = Field(default=None, max_length=1000)
    superseded_by: Optional[str] = Field(default=None, max_length=256)
    project_id: Optional[str] = Field(default=None, max_length=256)
    expected_revision: Optional[int] = Field(default=None, ge=0)

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4096, description="Search query")
    top_k: int = Field(default=5, ge=1, le=100)
    hybrid: bool = Field(default=True, description="Use hybrid search")
    project_id: Optional[str] = Field(default=None, max_length=256)
    retrieval_scope: Literal["default", "global", "project", "all"] = "default"

class RankRequest(BaseModel):
    query: str
    candidates: List[Dict]
    project_id: Optional[str] = Field(default=None, max_length=256)
    retrieval_scope: Literal["default", "global", "project", "all"] = "default"

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str = "3.0.0"
    services: Dict[str, str]

# ============================================================================
# Global State & Lifespan
# ============================================================================

# VAULT_PATH is injected by the Docker image (ENV VAULT_PATH=/vault) and
# docker-compose.yml, which volume-mounts ./data/vault to /vault. Without
# reading it here the API resolves to the container's home directory and
# silently ignores the mounted vault entirely. Unset for local runs, so it
# falls back to the repo's canonical location under the user's home.
vault_path = Path(os.environ.get("VAULT_PATH", str(Path.home() / "Documents/Brain-Eleven")))
memory_store = None
hybrid_engine = None
ranker = None
cache = None
graph = None
chat_agent = None


def _rebuild_graph() -> "KnowledgeGraph":
    """
    Rebuild the knowledge graph from the current canonical store and swap
    it into both the module-level `graph` and the running ChatAgent.

    Call this after ANY write to validated-memory.json (create, update,
    delete, and the batch validator run) - the graph is a derived
    projection, not an independent store, so a write that doesn't trigger
    this leaves the graph reflecting stale data. EntityExtractor.build_graph
    always clears before repopulating, so this is a real fresh rebuild,
    not an incremental add on top of whatever was there before.
    """
    global graph
    extractor = EntityExtractor(str(vault_path))
    graph = extractor.build_graph()
    if chat_agent:
        chat_agent.graph = graph
    return graph


def _memory_corpus_fingerprint(memories: List[Dict], revision: object = None) -> str:
    """Create a privacy-safe cache identity for the filtered memory corpus."""
    records = [
        {
            "memory_id": str(memory.get("memory_id", "")),
            "content_hash": hashlib.sha256(str(memory.get("content", "")).encode("utf-8")).hexdigest(),
            "status": str(memory.get("status", "")),
            "updated_at": str(memory.get("updated_at", memory.get("timestamp", ""))),
        }
        for memory in memories
    ]
    payload = json.dumps({"revision": revision, "records": sorted(records, key=lambda item: item["memory_id"])}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _ensure_graph_current() -> "KnowledgeGraph":
    """Recover the graph projection before serving graph-backed responses."""
    if graph is None:
        raise RuntimeError("Knowledge graph is not initialized")
    current_revision = MemoryStore(vault_path).revision()
    if not graph.is_current(current_revision):
        logger.warning(
            "Knowledge graph projection is %s; rebuilding before retrieval",
            graph.projection_status(current_revision).get("status"),
        )
        return _rebuild_graph()
    return graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown as a single context manager (the on_event hooks
    this replaced are deprecated as of FastAPI 0.95+)."""
    global memory_store, hybrid_engine, ranker, cache, chat_agent

    logger.info("🚀 Starting Brain-Eleven API...")

    try:
        memory_store = MemoryRetriever(str(vault_path))
        logger.info("✅ Memory store initialized")

        hybrid_engine = HybridSearchEngine(str(vault_path))
        logger.info("✅ Hybrid search engine initialized")

        ranker = HeuristicRanker()
        logger.info("✅ ML ranker initialized")

        # Cache manager (Phase 9A: L1 memory + L2 Redis + L3 disk)
        cache = CacheManager(
            vault_path=str(vault_path),
            redis_host=os.environ.get("REDIS_HOST", "localhost"),
            redis_port=int(os.environ.get("REDIS_PORT", "6379")),
        )
        logger.info("✅ Cache manager initialized")

        # ChatAgent builds its own MemoryRetriever/HybridSearchEngine
        # internally rather than reusing the ones above - duplicate init
        # cost is negligible here.
        chat_agent = ChatAgent(str(vault_path))
        logger.info("✅ Chat agent initialized")

        # Build the knowledge graph fresh on startup (Phase 11A/B). Cheap at
        # this data volume; _rebuild_graph() always clears before
        # repopulating, so this reflects the current store exactly, not
        # whatever an old persisted knowledge-graph.json happened to have.
        _rebuild_graph()
        logger.info(f"✅ Knowledge graph built: {graph.stats()}")

        logger.info("✅ All services ready!")
    except Exception as e:
        logger.error(f"❌ Startup error: {e}")
        raise

    yield

    logger.info("🛑 Shutting down Brain-Eleven API...")


# ============================================================================
# FastAPI App Setup
# ============================================================================

app = FastAPI(
    title="Brain-Eleven v3",
    description="Advanced memory system with semantic search and ML ranking",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware. allow_origins=["*"] combined with allow_credentials=True
# is both a browser-spec violation (credentialed requests can't actually
# use a wildcard origin) and, for an API with unauthenticated write
# endpoints, an open door for any page the user's browser visits to call
# them. Default to localhost dev origins; override via CORS_ALLOWED_ORIGINS
# (comma-separated) for a real deployment.
_cors_origins_env = os.environ.get("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS = (
    [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
    if _cors_origins_env
    else ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000", "http://127.0.0.1:8000"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def bounded_request_validation_error(request: Request, exc: RequestValidationError):
    """Keep request validation details from reflecting submitted secrets/paths."""
    return JSONResponse(
        status_code=422,
        content={"detail": {"code": "INVALID_REQUEST"}},
    )

# HTTP boundary policy. The API key is an internal/admin bearer credential;
# it is intentionally kept out of request contexts, records, and diagnostics.
API_KEY = os.environ.get("BRAIN_ELEVEN_API_KEY") or None
_PUBLIC_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_HTTP_SCOPED_READ_PATHS = frozenset(
    {
        ("POST", "/search"),
        ("POST", "/rank"),
        ("GET", "/memories"),
        ("GET", "/digest"),
        ("GET", "/anomalies"),
        ("GET", "/graph/entities"),
        ("POST", "/chat"),
    }
)
_CONFIGURED_HOST = (
    os.environ["BRAIN_ELEVEN_HOST"]
    if "BRAIN_ELEVEN_HOST" in os.environ
    else "127.0.0.1"
)
_IS_LOOPBACK_HOST = str(_CONFIGURED_HOST).lower() in _LOOPBACK_HOSTS
_HTTP_PROJECT_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}\Z")


@dataclass(frozen=True)
class _HttpScopeContext:
    """Normalized scope facts produced by the single HTTP read boundary."""

    project_id: Optional[str]
    retrieval_scope: str
    admin: bool = False


def _http_policy_error(code: str, status_code: int = 403) -> HTTPException:
    """Return a stable, content-free HTTP policy error."""
    return HTTPException(status_code=status_code, detail={"code": code})


def _http_policy_response(code: str, status_code: int) -> JSONResponse:
    """Return the middleware form of a stable, content-free policy error."""
    return JSONResponse(status_code=status_code, content={"detail": {"code": code}})


def _http_project_id(project_id: Optional[str]) -> Optional[str]:
    """Normalize an opaque project ID without accepting path/query fragments."""
    if project_id is None:
        return None
    if not isinstance(project_id, str):
        raise _http_policy_error("HTTP_PROJECT_INVALID", 422)
    normalized = project_id.strip()
    if not normalized or not _HTTP_PROJECT_ID_PATTERN.fullmatch(normalized):
        raise _http_policy_error("HTTP_PROJECT_INVALID", 422)
    return normalized


def _validate_http_project(project_id: str) -> None:
    """Validate a project context through the existing read-only registry."""
    try:
        record = ProjectRegistry(vault_path).get(project_id)
    except (ProjectRegistryError, OSError, TypeError, ValueError, UnicodeError):
        # Registry corruption and unavailable identity are deliberately
        # indistinguishable from an unknown project at this boundary.
        raise _http_policy_error("HTTP_PROJECT_UNKNOWN", 404) from None

    if not record or record.get("project_id") != project_id:
        raise _http_policy_error("HTTP_PROJECT_UNKNOWN", 404)
    if record.get("status") != "active" or record.get("proactive_capture") is not True:
        raise _http_policy_error("HTTP_PROJECT_UNAVAILABLE", 403)


def _http_create_project_id(memory: MemoryCreate) -> Optional[str]:
    """Resolve a create request's project claim through registry read access."""
    if memory.project_id:
        return memory.project_id
    if memory.scope == "project" and memory.project_root:
        try:
            record = ProjectRegistry(vault_path).resolve(memory.project_root)
        except (ProjectRegistryError, OSError, TypeError, ValueError, UnicodeError):
            raise _http_policy_error("HTTP_PROJECT_UNKNOWN", 404) from None
        if not record or not record.get("project_id"):
            raise _http_policy_error("HTTP_PROJECT_UNKNOWN", 404)
        return record["project_id"]
    return memory.project or None


def _authorize_http_scope(
    request: Request,
    project_id: Optional[str],
    retrieval_scope: str,
) -> _HttpScopeContext:
    """Authorize and normalize every HTTP scope-bearing request.

    Project IDs are checked against the canonical registry before any memory,
    graph, digest, anomaly, or chat data is loaded. The `all` scope is granted
    only from the middleware's validated API-key marker.
    """
    if retrieval_scope not in {"default", "global", "project", "all"}:
        raise _http_policy_error("HTTP_SCOPE_INVALID", 422)

    normalized_project_id = _http_project_id(project_id)
    admin = bool(getattr(request.state, "http_admin_authorized", False))

    if retrieval_scope == "all":
        if not admin:
            raise _http_policy_error("HTTP_ADMIN_KEY_REQUIRED", 403)
    elif retrieval_scope == "project" and not normalized_project_id:
        raise _http_policy_error("HTTP_SCOPE_REQUIRED", 403)

    if normalized_project_id:
        _validate_http_project(normalized_project_id)

    return _HttpScopeContext(
        project_id=normalized_project_id,
        retrieval_scope=retrieval_scope,
        admin=admin and retrieval_scope == "all",
    )


def _load_http_memories(context: _HttpScopeContext) -> tuple[List[Dict], Dict]:
    """Load only the corpus allowed by a previously authorized context."""
    validated_file = vault_path / ".claude/validated-memory.json"
    if not validated_file.exists():
        return [], {}

    with open(validated_file, encoding="utf-8") as handle:
        data = json.load(handle)
    records = data.get("validated_memory", [])
    if not isinstance(records, list):
        raise ValueError("validated_memory must be a list")
    return (
        filter_memories(
            records,
            project_id=context.project_id,
            retrieval_scope=context.retrieval_scope,
        ),
        data,
    )


_GRAPH_MEMORY_NODE_TYPES = frozenset({"DECISION", "LESSON", "OPEN_LOOP", "OBSERVATION"})


class _HttpScopedGraphView:
    """Read-only graph view that restores provenance for derived nodes.

    The persisted projection predates HTTP scope authorization: technology and
    phase nodes are shared IDs and carry no project field.  Their incoming
    ``source_memory`` edges are the available provenance boundary.  A scoped
    view therefore admits such a node only when at least one source memory is
    in the already-filtered HTTP corpus.  The canonical graph object is never
    mutated.
    """

    def __init__(self, graph: KnowledgeGraph, context: _HttpScopeContext):
        self._graph = graph
        self._context = context
        self._allowed_memory_ids = self._load_allowed_memory_ids()

    def _load_allowed_memory_ids(self):
        if self._context.admin and self._context.retrieval_scope == "all":
            return None
        memories, _data = _load_http_memories(self._context)
        return {
            str(memory.get("memory_id"))
            for memory in memories
            if memory.get("memory_id")
        }

    def _node_visible(self, node_id: str) -> bool:
        if not self._graph.is_entity_visible(
            node_id,
            self._context.project_id,
            self._context.retrieval_scope,
        ):
            return False
        if self._allowed_memory_ids is None:
            return True
        data = self._graph.graph.nodes.get(node_id, {})
        if data.get("type") in _GRAPH_MEMORY_NODE_TYPES or data.get("type") == "PROJECT":
            return True
        return any(
            str(edge_data.get("source_memory", "")) in self._allowed_memory_ids
            for _source, _target, edge_data in self._graph.graph.in_edges(
                node_id, data=True
            )
        )

    def find_entities(self, **kwargs):
        return [
            entity
            for entity in self._graph.find_entities(**kwargs)
            if self._node_visible(entity["id"])
        ]

    def is_entity_visible(self, entity_id: str, *args, **kwargs) -> bool:
        return self._node_visible(entity_id)

    def get_entity(self, entity_id: str):
        if not self._node_visible(entity_id):
            return None
        return self._graph.get_entity(entity_id)

    def get_relationships(self, entity_id: str, **kwargs):
        if not self._node_visible(entity_id):
            return []
        return [
            relationship
            for relationship in self._graph.get_relationships(entity_id, **kwargs)
            if self._node_visible(relationship["source"])
            and self._node_visible(relationship["target"])
        ]

    def traverse(self, entity_id: str, **kwargs):
        if not self._node_visible(entity_id):
            return {"nodes": [], "edges": []}
        subgraph = self._graph.traverse(entity_id, **kwargs)
        visible_ids = {
            node["id"] for node in subgraph.get("nodes", []) if self._node_visible(node["id"])
        }
        return {
            "nodes": [node for node in subgraph.get("nodes", []) if node["id"] in visible_ids],
            "edges": [
                edge
                for edge in subgraph.get("edges", [])
                if edge["source"] in visible_ids and edge["target"] in visible_ids
            ],
        }

    def stats(self):
        visible_nodes = [
            (node_id, data)
            for node_id, data in self._graph.graph.nodes(data=True)
            if self._node_visible(node_id)
        ]
        visible_ids = {node_id for node_id, _data in visible_nodes}
        visible_edges = [
            (source, target, data)
            for source, target, data in self._graph.graph.edges(data=True)
            if source in visible_ids and target in visible_ids
        ]
        entities_by_type = {}
        for _node_id, data in visible_nodes:
            node_type = data.get("type", "unknown")
            entities_by_type[node_type] = entities_by_type.get(node_type, 0) + 1
        relationships_by_type = {}
        for _source, _target, data in visible_edges:
            rel_type = data.get("rel_type", "unknown")
            relationships_by_type[rel_type] = relationships_by_type.get(rel_type, 0) + 1
        return {
            "total_entities": len(visible_nodes),
            "total_relationships": len(visible_edges),
            "entities_by_type": entities_by_type,
            "relationships_by_type": relationships_by_type,
            "projection": self._graph.projection_status(),
        }


def _http_admin_key_is_valid(request: Request) -> bool:
    """Validate the configured bearer credential without exposing it."""
    supplied = request.headers.get("X-API-Key")
    return bool(API_KEY and supplied and hmac.compare_digest(supplied, API_KEY))


def _is_http_scoped_read(request: Request) -> bool:
    """Identify read routes whose ordinary loopback scope stays usable."""
    method_path = (request.method.upper(), request.url.path)
    if method_path in _HTTP_SCOPED_READ_PATHS:
        return True
    if request.method.upper() != "GET":
        return False
    path = request.url.path
    return (
        path.startswith("/memories/")
        or path.startswith("/graph/entities/")
        or path.startswith("/graph/traverse/")
    )


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    """Protect sensitive routes when configured or bound beyond loopback."""
    if request.url.path in _PUBLIC_PATHS:
        return await call_next(request)

    request.state.http_admin_authorized = False
    supplied_admin_key = _http_admin_key_is_valid(request)
    if API_KEY:
        if not supplied_admin_key and (
            not _IS_LOOPBACK_HOST or not _is_http_scoped_read(request)
        ):
            return _http_policy_response("HTTP_ADMIN_KEY_REQUIRED", 401)
        request.state.http_admin_authorized = supplied_admin_key
    elif not _IS_LOOPBACK_HOST:
        # A non-loopback deployment without a configured key has no trusted
        # boundary. Fail closed on the first protected request.
        return _http_policy_response("HTTP_ADMIN_KEY_REQUIRED", 403)

    return await call_next(request)

# ============================================================================
# Health & Status Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        services={
            "memory_store": "ready",
            "search_engine": "ready",
            "ranker": "ready"
        }
    )

@app.get("/status")
async def status():
    """Get system status"""
    try:
        data = MemoryStore(vault_path).load()
        memory_count = len(data.get("validated_memory", []))

        return {
            "status": "operational",
            "timestamp": datetime.now().isoformat(),
            "memory_count": memory_count,
            "store_revision": data["revision"],
            "vault_path": str(vault_path)
        }
    except Exception as e:
        logger.error(f"Status check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Search Endpoints
# ============================================================================

@app.post("/search")
async def search(request: SearchRequest, http_request: Request):
    """
    Hybrid search: combines lexical + semantic search

    Returns ranked results with combined scores
    """
    scope_context = _authorize_http_scope(
        http_request, request.project_id, request.retrieval_scope
    )
    try:
        logger.info(f"Search query: {request.query}")

        # Load memories
        memories, data = _load_http_memories(scope_context)
        if not data:
            raise HTTPException(status_code=404, detail="No memories found")

        if not memories:
            return {"results": [], "query": request.query, "count": 0}

        # Cache key incorporates a content/revision fingerprint. Corpus size
        # alone lets same-sized mutations reuse stale search results.
        cache_key = CacheManager.make_key(
            "search", request.query, request.top_k, request.project_id or "global-only",
            request.retrieval_scope, _memory_corpus_fingerprint(memories, data.get("revision")),
        )

        def compute_results():
            return hybrid_engine.search(
                request.query, memories, top_k=request.top_k,
                project_id=scope_context.project_id,
                retrieval_scope=scope_context.retrieval_scope,
            )

        results = cache.get_or_compute(cache_key, compute_results) if cache else compute_results()

        logger.info(f"Search returned {len(results)} results")

        return {
            "results": results,
            "query": request.query,
            "count": len(results),
            "timestamp": datetime.now().isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/rank")
async def rank_results(request: RankRequest, http_request: Request):
    """
    Deterministic weighted ranking: applies 5-feature weighting to candidates

    Features: search_relevance, memory_quality, recency, novelty, match_type
    """
    scope_context = _authorize_http_scope(
        http_request, request.project_id, request.retrieval_scope
    )
    try:
        # Load memories for context
        memories, _data = _load_http_memories(scope_context)

        # Apply the same visibility policy to the candidate set itself. The
        # context corpus alone is not enough: otherwise a caller could send a
        # foreign project's candidate directly to /rank and bypass retrieval.
        candidates = filter_memories(
            request.candidates,
            project_id=scope_context.project_id,
            retrieval_scope=scope_context.retrieval_scope,
        )
        allowed_ids = {memory.get("memory_id") for memory in memories}
        candidates = [
            candidate
            for candidate in candidates
            if candidate.get("memory_id") in allowed_ids
        ]
        ranked = ranker.rank(request.query, candidates, memories)

        return {
            "results": ranked,
            "query": request.query,
            "count": len(ranked),
            "timestamp": datetime.now().isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ranking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/embed")
async def embed_text(query: str = Query(..., description="Text to embed")):
    """
    Generate embedding for text using text-embedding-3-small

    Embeddings are cached (Phase 9A) since they're a pure function of the
    input text and expensive to (re)compute via the OpenAI API.
    """
    try:
        _embedding_generator = _load_hyphenated_module("embedding_generator", "embedding-generator.py")
        EmbeddingGenerator = _embedding_generator.EmbeddingGenerator

        # Version the API cache alongside the provider-backed contract so old
        # deterministic/fallback vectors cannot be reused after migration.
        cache_key = CacheManager.make_key("embed-v2", "text-embedding-3-small", query)

        def compute_embedding():
            gen = EmbeddingGenerator(str(vault_path))
            embedding = gen.embed_text(query)
            if embedding is None:
                raise RuntimeError("semantic embedding provider unavailable")
            return embedding.tolist()

        embedding = cache.get_or_compute(cache_key, compute_embedding) if cache else compute_embedding()

        return {
            "text": query,
            "embedding": embedding,
            "dimension": len(embedding),
            "model": "text-embedding-3-small"
        }
    except RuntimeError as e:
        logger.info("Embedding unavailable: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Memory Endpoints
# ============================================================================

@app.get("/memories")
async def list_memories(
    http_request: Request,
    skip: int = 0,
    limit: int = 100,
    project_id: Optional[str] = None,
    retrieval_scope: Literal["default", "global", "project", "all"] = "default",
):
    """List all memories"""
    scope_context = _authorize_http_scope(http_request, project_id, retrieval_scope)
    try:
        memories, _data = _load_http_memories(scope_context)
        if not _data:
            return {"memories": [], "total": 0}

        # Pagination
        total = len(memories)
        memories = memories[skip:skip + limit]

        return {
            "memories": memories,
            "total": total,
            "skip": skip,
            "limit": limit
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List memories error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/memories")
async def create_memory(memory: MemoryCreate, http_request: Request):
    """
    Create a new memory through the real validation pipeline (fingerprint
    dedup, conflict detection, quality scoring) - NOT a raw append.

    Previously this minted its own fake "ULID" (an epoch-seconds string,
    collidable within the same second and not a real ULID at all) and
    wrote a bare {memory_id, type, content, confidence, timestamp, status}
    record directly to validated-memory.json, skipping every check
    memory-validator.py exists to run and producing a memory shape that
    didn't match what the batch pipeline writes (missing source_id,
    quality_score, novelty, is_approved, dedup_fingerprint, ...) - two
    divergent memory schemas from two write paths into the same file.
    MemoryValidator.validate_single() is the fix: same fingerprint-dedup,
    conflict-detection, and quality-scoring logic the batch compiler uses,
    just scoped to one item instead of a compiled batch.
    """
    project_claim = _http_create_project_id(memory)
    if memory.scope == "project" or project_claim:
        _authorize_http_scope(http_request, project_claim, "project")
    else:
        _authorize_http_scope(http_request, None, "default")
    try:
        safety = evaluate_capture(memory.content)
        if not safety.accepted:
            raise HTTPException(status_code=422, detail=safety.to_dict())
        validator = MemoryValidator(str(vault_path))
        candidate, issues, is_new = validator.validate_single_and_append(
            type_=memory.type,
            content=memory.content,
            confidence=memory.confidence,
            source="api",
            scope=memory.scope,
            project=memory.project_label or memory.project,
            project_id=memory.project_id,
            project_root=memory.project_root,
            registry_path=str(project_registry_path(vault_path)),
        )

        if not is_new:
            # Exact fingerprint match already exists - hand back its real
            # identity instead of minting a duplicate memory_id for
            # content that's already stored.
            return {
                "memory_id": candidate.get("memory_id"),
                "status": "duplicate_returned_existing",
                "scope": candidate.get("scope", memory.scope or "global"),
                "project": candidate.get("project", memory.project),
                "project_id": candidate.get("project_id", memory.project_id),
                "timestamp": datetime.now().isoformat(),
            }

        # The graph is a derived projection of validated-memory.json, not
        # an independent store - any write here must propagate or /chat
        # and /graph/* diverge from /search and /memories within the same
        # running process.
        if cache:
            cache.clear()
        _rebuild_graph()

        logger.info(f"Created memory: {candidate.memory_id} (quality={candidate.quality_score:.2f})")

        return {
            "memory_id": candidate.memory_id,
            "status": "created",
            "scope": candidate.scope,
            "project": candidate.project,
            "project_id": candidate.project_id,
            "is_approved": candidate.is_approved,
            "quality_score": candidate.quality_score,
            "issues": [issue.description for issue in issues],
            "timestamp": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except CaptureSafetyError as e:
        raise HTTPException(status_code=422, detail=e.result.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Create memory error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/memories/{memory_id}")
async def get_memory(
    memory_id: str,
    http_request: Request,
    project_id: Optional[str] = Query(default=None, max_length=256),
    retrieval_scope: Literal["default", "global", "project", "all"] = "default",
):
    """Get specific memory"""
    scope_context = _authorize_http_scope(http_request, project_id, retrieval_scope)
    try:
        memories, _data = _load_http_memories(scope_context)
        if not _data:
            raise HTTPException(status_code=404, detail="Memory not found")

        memory = next((m for m in memories if m.get("memory_id") == memory_id), None)
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")

        return memory
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get memory error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# API lifecycle mutations deliberately use a narrow adapter around the
# existing lifecycle field vocabulary.  The canonical write remains the
# MemoryStore transaction below; this adapter only validates the request and
# applies the same fields/timestamps used by MemoryLifecycleManager.
_API_LIFECYCLE_STATUSES = {"active", "resolved", "superseded", "deleted"}
_API_TERMINAL_STATUSES = {"resolved", "superseded", "deleted"}
_API_MAX_ACTOR_LENGTH = 256
_API_MAX_REASON_LENGTH = 1000


class _ApiLifecycleError(ValueError):
    """Bounded API lifecycle rejection without exposing record contents."""

    code = "LIFECYCLE_TRANSITION_INVALID"

    def __init__(self, code: str = "LIFECYCLE_TRANSITION_INVALID"):
        self.code = code
        super().__init__(code)


def _api_error(code: str) -> HTTPException:
    """Return a fixed, content-free mutation error response."""
    return HTTPException(status_code=422, detail={"code": code})


def _clean_bounded_text(value: Optional[str], maximum: int, *, required: bool = False) -> str:
    """Normalize a bounded API string without retaining whitespace padding."""
    if value is None:
        if required:
            raise _ApiLifecycleError()
        return ""
    cleaned = str(value).strip()
    if required and not cleaned:
        raise _ApiLifecycleError()
    if len(cleaned) > maximum:
        raise _ApiLifecycleError()
    return cleaned


def _validate_api_project_scope(memory: Dict, requested_project_id: Optional[str]) -> None:
    """Check an opaque project namespace before any record mutation."""
    scope, _project, stored_project_id = infer_memory_scope(memory)
    if scope != "project":
        # A request-side project_id is intentionally ignored for global
        # records; it is never copied into canonical data.
        return
    requested = str(requested_project_id or "").strip()
    if not requested:
        raise _ApiLifecycleError("PROJECT_SCOPE_REQUIRED")
    if requested != stored_project_id:
        raise _ApiLifecycleError("PROJECT_SCOPE_MISMATCH")


def _api_memory_status(memory: Dict) -> str:
    """Return the lifecycle status while supporting missing legacy status."""
    return memory.get("status", "active")


def _api_update_scope_and_fingerprint(memory: Dict) -> None:
    """Preserve the shared scope/fingerprint normalization on content edits."""
    scope, _project, project_id = infer_memory_scope(memory)
    memory["scope"] = scope
    memory["project_id"] = project_id
    memory["dedup_fingerprint"] = scoped_fingerprint(
        memory.get("content", ""), scope, project_id, memory.get("type", "")
    )


def _api_transition_target(memory: Dict, target_id: str, memories: List[Dict]) -> Dict:
    """Resolve a supersession target within the same memory scope."""
    target = next((item for item in memories if item.get("memory_id") == target_id), None)
    if target is None or target.get("memory_id") == memory.get("memory_id"):
        raise _ApiLifecycleError()
    source_scope, _source_project, source_project_id = infer_memory_scope(memory)
    target_scope, _target_project, target_project_id = infer_memory_scope(target)
    if (source_scope, source_project_id) != (target_scope, target_project_id):
        raise _ApiLifecycleError()
    return target


def _apply_api_lifecycle_transition(
    memory: Dict,
    update: MemoryUpdate,
    memories: List[Dict],
) -> bool:
    """Apply one legal API transition; return ``False`` for terminal no-op."""
    current = _api_memory_status(memory)
    requested = update.status
    has_lifecycle_fields = any(
        value is not None for value in (update.resolved_by, update.reason, update.superseded_by)
    )
    has_content_fields = update.content is not None or update.confidence is not None

    if current not in _API_LIFECYCLE_STATUSES:
        raise _ApiLifecycleError()

    # Deletion has its own HTTP DELETE operation.  A PUT must never create or
    # repeat the deleted terminal state, even when the record is already
    # deleted.
    if requested == "deleted":
        raise _ApiLifecycleError()

    # A repeated terminal operation is an explicit idempotent no-op.  It must
    # not update timestamps, revision, cache, or the derived graph.
    if current in _API_TERMINAL_STATUSES and requested == current:
        if has_content_fields or has_lifecycle_fields:
            raise _ApiLifecycleError()
        return False

    if current in _API_TERMINAL_STATUSES:
        raise _ApiLifecycleError()

    if requested is None:
        requested = "active"
    if requested not in _API_LIFECYCLE_STATUSES:
        raise _ApiLifecycleError()

    if requested == "active":
        if has_lifecycle_fields:
            raise _ApiLifecycleError()
        # Materialize the legacy missing-status interpretation only when the
        # caller has accepted an ordinary active update.  This keeps the
        # lifecycle target explicit while preserving the missing-status read
        # compatibility for untouched records.
        memory["status"] = "active"
        if update.content is not None:
            memory["content"] = update.content
        if update.confidence is not None:
            memory["confidence"] = update.confidence
    elif requested == "resolved":
        if has_content_fields or update.superseded_by is not None:
            raise _ApiLifecycleError()
        resolved_by = _clean_bounded_text(
            update.resolved_by, _API_MAX_ACTOR_LENGTH, required=True
        )
        reason = _clean_bounded_text(update.reason, _API_MAX_REASON_LENGTH)
        memory["status"] = "resolved"
        memory["resolved_at"] = datetime.now().isoformat()
        memory["resolved_by"] = resolved_by
        if reason:
            memory["resolution_note"] = reason
    elif requested == "superseded":
        if has_content_fields or update.resolved_by is not None:
            raise _ApiLifecycleError()
        superseded_by = _clean_bounded_text(
            update.superseded_by, _API_MAX_ACTOR_LENGTH, required=True
        )
        reason = _clean_bounded_text(update.reason, _API_MAX_REASON_LENGTH)
        _api_transition_target(memory, superseded_by, memories)
        memory["status"] = "superseded"
        memory["resolved_at"] = datetime.now().isoformat()
        memory["superseded_by"] = superseded_by
        if reason:
            memory["supersession_note"] = reason

    memory["updated_at"] = datetime.now().isoformat()
    _api_update_scope_and_fingerprint(memory)
    return True


def _projection_degraded(memory_id: str) -> JSONResponse:
    """Expose a committed canonical write with a bounded projection failure."""
    return JSONResponse(
        status_code=503,
        content={
            "canonical_status": "committed",
            "memory_id": memory_id,
            "code": "GRAPH_PROJECTION_DEGRADED",
        },
    )


@app.put("/memories/{memory_id}")
async def update_memory(memory_id: str, update: MemoryUpdate, http_request: Request):
    """Update content or apply one typed, fail-closed lifecycle transition."""
    normalized_project_id = _http_project_id(update.project_id)
    _authorize_http_scope(http_request, None, "default")
    try:
        if update.content is not None:
            safety = evaluate_capture(update.content)
            if not safety.accepted:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "CAPTURE_SAFETY_REJECTED", **safety.to_dict()},
                )
        store = MemoryStore(vault_path)

        def mutate(data):
            memories = data.get("validated_memory", [])
            memory = next((m for m in memories if m.get("memory_id") == memory_id), None)
            if not memory:
                raise HTTPException(status_code=404, detail={"code": "MEMORY_NOT_FOUND"})

            memory_scope = infer_memory_scope(memory)[0]
            if memory_scope == "project" and normalized_project_id:
                _authorize_http_scope(http_request, normalized_project_id, "project")
            _validate_api_project_scope(memory, normalized_project_id)
            changed = _apply_api_lifecycle_transition(memory, update, memories)
            return (memory, True) if changed else no_change((memory, False))

        mutation, persisted = store.transact(
            mutate,
            expected_revision=update.expected_revision,
        )
        memory, changed = mutation
        # A no-op is represented by an unchanged transaction result and must
        # not invalidate cache or rebuild a derived projection.
        is_terminal_noop = not changed
        if is_terminal_noop:
            return {**memory, "store_revision": persisted["revision"]}

        if cache:
            cache.clear()
        try:
            _rebuild_graph()
        except Exception:
            logger.error("Graph rebuild failed after API update")
            return _projection_degraded(memory_id)

        logger.info(f"Updated memory: {memory_id}")
        return {**memory, "store_revision": persisted["revision"]}
    except HTTPException:
        raise
    except _ApiLifecycleError as e:
        raise _api_error(e.code)
    except MemoryStoreConflict as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MEMORY_STORE_REVISION_CONFLICT",
                "expected_revision": e.expected_revision,
                "actual_revision": e.actual_revision,
            },
        )
    except Exception:
        logger.error("Update memory failed")
        raise HTTPException(status_code=500, detail={"code": "MEMORY_MUTATION_FAILED"})

@app.delete("/memories/{memory_id}")
async def delete_memory(
    http_request: Request,
    memory_id: str,
    expected_revision: Optional[int] = Query(default=None, ge=0),
    project_id: Optional[str] = Query(default=None, max_length=256),
):
    """Delete memory (soft delete - mark as deleted)"""
    normalized_project_id = _http_project_id(project_id)
    _authorize_http_scope(http_request, None, "default")
    try:
        store = MemoryStore(vault_path)

        def mutate(data):
            memories = data.get("validated_memory", [])
            memory = next((m for m in memories if m.get("memory_id") == memory_id), None)
            if not memory:
                raise HTTPException(status_code=404, detail={"code": "MEMORY_NOT_FOUND"})
            memory_scope = infer_memory_scope(memory)[0]
            if memory_scope == "project" and normalized_project_id:
                _authorize_http_scope(http_request, normalized_project_id, "project")
            _validate_api_project_scope(memory, normalized_project_id)
            status = _api_memory_status(memory)
            if status == "deleted":
                return no_change((memory, False))
            if status != "active":
                raise _ApiLifecycleError()
            memory["status"] = "deleted"
            memory["deleted_at"] = datetime.now().isoformat()
            memory["updated_at"] = datetime.now().isoformat()
            return memory, True

        mutation, persisted = store.transact(mutate, expected_revision=expected_revision)
        memory, changed = mutation
        if not changed:
            return {
                "status": "deleted",
                "memory_id": memory_id,
                "store_revision": persisted["revision"],
            }

        if cache:
            cache.clear()
        try:
            _rebuild_graph()
        except Exception:
            logger.error("Graph rebuild failed after API delete")
            return _projection_degraded(memory_id)

        logger.info(f"Deleted memory: {memory_id}")
        return {
            "status": "deleted",
            "memory_id": memory_id,
            "store_revision": persisted["revision"],
        }
    except HTTPException:
        raise
    except _ApiLifecycleError as e:
        raise _api_error(e.code)
    except MemoryStoreConflict as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MEMORY_STORE_REVISION_CONFLICT",
                "expected_revision": e.expected_revision,
                "actual_revision": e.actual_revision,
            },
        )
    except Exception:
        logger.error("Delete memory failed")
        raise HTTPException(status_code=500, detail={"code": "MEMORY_MUTATION_FAILED"})

# ============================================================================
# Cache Endpoint (Phase 9A)
# ============================================================================

@app.get("/cache/stats")
async def cache_stats():
    """Get multi-level cache statistics (L1 in-memory, L2 Redis, L3 disk)"""
    if not cache:
        raise HTTPException(status_code=503, detail="Cache not initialized")
    return cache.stats()

@app.post("/cache/clear")
async def cache_clear():
    """Clear all cache levels (L1, L2, L3)"""
    if not cache:
        raise HTTPException(status_code=503, detail="Cache not initialized")
    cache.clear()
    logger.info("Cache cleared via API request")
    return {"status": "cleared", "timestamp": datetime.now().isoformat()}

# ============================================================================
# Digest & Anomaly Endpoints (Phase 10A/10B)
# ============================================================================

@app.get("/digest")
async def get_digest(
    http_request: Request,
    days: Optional[int] = None,
    top_n: int = 5,
    project_id: Optional[str] = None,
    retrieval_scope: Literal["default", "global", "project", "all"] = "default",
):
    """
    Generate a memory digest: top-ranked, deduped entries per type.

    Embedding/LLM-free (token-overlap dedup + quality/confidence ranking),
    so this works the same whether OPENAI_API_KEY is set or not.
    """
    scope_context = _authorize_http_scope(http_request, project_id, retrieval_scope)
    try:
        summarizer = MemorySummarizer(str(vault_path))
        digest = summarizer.generate_digest(
            days=days,
            top_n_per_type=top_n,
            project_id=scope_context.project_id,
            retrieval_scope=scope_context.retrieval_scope,
        )
        return digest
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Digest error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/anomalies")
async def get_anomalies(
    http_request: Request,
    project_id: Optional[str] = Query(default=None, max_length=256),
    retrieval_scope: Literal["default", "global", "project", "all"] = "default",
):
    """
    Scan the memory store for structural anomalies: duplicates, stale
    open loops, broken supersession links, scoring inconsistencies, etc.
    """
    scope_context = _authorize_http_scope(http_request, project_id, retrieval_scope)
    try:
        detector = AnomalyDetector(str(vault_path))
        memories, _data = _load_http_memories(scope_context)
        report = detector.detect_all(memories=memories)
        return report
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Anomaly detection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Knowledge Graph & Chat Endpoints (Phase 11)
# ============================================================================

@app.get("/graph/stats")
async def graph_stats():
    """Entity/relationship counts in the knowledge graph."""
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialized")
    return _ensure_graph_current().stats()

@app.get("/graph/entities")
async def graph_entities(
    http_request: Request,
    type: Optional[str] = None,
    name_contains: Optional[str] = None,
    project_id: Optional[str] = None,
    retrieval_scope: Literal["default", "global", "project", "all"] = "default",
):
    """List entities, optionally filtered by type and/or name substring."""
    scope_context = _authorize_http_scope(http_request, project_id, retrieval_scope)
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialized")
    current_graph = _ensure_graph_current()
    scoped_graph = _HttpScopedGraphView(current_graph, scope_context)
    return {
        "entities": scoped_graph.find_entities(
            entity_type=type,
            name_contains=name_contains,
            project_id=scope_context.project_id,
            retrieval_scope=scope_context.retrieval_scope,
        )
    }

@app.get("/graph/entities/{entity_id}/relationships")
async def graph_entity_relationships(
    http_request: Request,
    entity_id: str,
    direction: str = "both",
    project_id: Optional[str] = None,
    retrieval_scope: Literal["default", "global", "project", "all"] = "default",
):
    """Relationships for one entity. direction: out | in | both."""
    scope_context = _authorize_http_scope(http_request, project_id, retrieval_scope)
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialized")
    current_graph = _ensure_graph_current()
    scoped_graph = _HttpScopedGraphView(current_graph, scope_context)
    if not scoped_graph.is_entity_visible(entity_id):
        raise HTTPException(status_code=404, detail="Entity not found")
    return {
        "entity_id": entity_id,
        "relationships": scoped_graph.get_relationships(
            entity_id,
            direction=direction,
            project_id=scope_context.project_id,
            retrieval_scope=scope_context.retrieval_scope,
        ),
    }

@app.get("/graph/traverse/{entity_id}")
async def graph_traverse(
    http_request: Request,
    entity_id: str,
    depth: int = 2,
    project_id: Optional[str] = None,
    retrieval_scope: Literal["default", "global", "project", "all"] = "default",
):
    """Subgraph reachable from an entity within `depth` hops (either direction)."""
    scope_context = _authorize_http_scope(http_request, project_id, retrieval_scope)
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialized")
    current_graph = _ensure_graph_current()
    scoped_graph = _HttpScopedGraphView(current_graph, scope_context)
    if not scoped_graph.is_entity_visible(entity_id):
        raise HTTPException(status_code=404, detail="Entity not found")
    return scoped_graph.traverse(
        entity_id,
        max_depth=depth,
        project_id=scope_context.project_id,
        retrieval_scope=scope_context.retrieval_scope,
    )

@app.post("/graph/rebuild")
async def graph_rebuild():
    """Force a fresh rebuild of the knowledge graph from current memories."""
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialized")
    try:
        rebuilt = _rebuild_graph()
        return {
            "status": "rebuilt",
            "stats": rebuilt.stats(),
            "projection": rebuilt.projection_status(),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Graph rebuild error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    conversation_id: Optional[str] = None
    project_id: Optional[str] = Field(default=None, max_length=256)
    retrieval_scope: Literal["default", "global", "project", "all"] = "default"

@app.post("/chat")
async def chat(http_request: Request, request: ChatRequest):
    """
    Rule-based chat over the memory system (see chat_interface.py) -
    answers are grounded in real search/digest/anomaly/graph results, not
    LLM-generated free text, since no LLM is configured.
    """
    scope_context = _authorize_http_scope(
        http_request, request.project_id, request.retrieval_scope
    )
    if not chat_agent:
        raise HTTPException(status_code=503, detail="Chat agent not initialized")
    try:
        # ChatAgent's legacy anomaly handler has no context argument and would
        # otherwise inspect the entire vault. Keep the existing chat envelope
        # while returning a content-free answer for scoped HTTP requests.
        if (
            not scope_context.admin
            and chat_agent.intent_classifier.classify(request.message).name == "ANOMALY"
        ):
            return {
                "response": "Anomaly details are unavailable for this request scope.",
                "conversation_id": request.conversation_id or str(uuid.uuid4()),
                "intent": "ANOMALY",
                "follow_ups": [],
            }
        current_graph = _ensure_graph_current()
        chat_target = chat_agent
        if not scope_context.admin:
            # ChatAgent's graph handlers use the graph object directly. Give
            # them a request-local filtered view so derived technology/phase
            # nodes cannot disclose a foreign project's names.
            chat_target = copy.copy(chat_agent)
            chat_target.graph = _HttpScopedGraphView(current_graph, scope_context)
        return chat_target.chat(
            request.message,
            conversation_id=request.conversation_id,
            project_id=scope_context.project_id,
            retrieval_scope=scope_context.retrieval_scope,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Metrics Endpoint
# ============================================================================

@app.get("/metrics")
async def metrics():
    """Get system metrics"""
    try:
        validated_file = vault_path / ".claude/validated-memory.json"
        if validated_file.exists():
            with open(validated_file) as f:
                data = json.load(f)
                memories = data.get("validated_memory", [])

                active = sum(1 for m in memories if m.get("status") == "active")
                total = len(memories)
        else:
            active = 0
            total = 0

        return {
            "memories": {
                "total": total,
                "active": active,
                "inactive": total - active
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Metrics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    logger.info("🚀 Starting Brain-Eleven API Server...")

    if not API_KEY:
        logger.warning(
            "⚠️  BRAIN_ELEVEN_API_KEY is not set - ordinary loopback reads "
            "remain available, while protected routes fail closed when the "
            "server is bound to a non-loopback host."
        )

    # Default to loopback-only. The HTTP middleware applies the same explicit
    # host decision to every protected route, including the Docker
    # configuration's 0.0.0.0 bind, before any route handler can read or
    # mutate state.
    #
    # Pass the app object directly (not "module:app" string) since this
    # file's hyphenated name (search-api.py) isn't a valid import target.
    uvicorn.run(
        app,
        host=os.environ.get("BRAIN_ELEVEN_HOST", "127.0.0.1"),
        port=8000,
        reload=False,
        access_log=True
    )
