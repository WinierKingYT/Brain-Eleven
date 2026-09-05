#!/usr/bin/env python3
"""
Brain-Eleven v3 REST API
Complete API server with hybrid search, ML ranking, and memory management
"""

from fastapi import FastAPI, HTTPException, Query, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional, Dict, Literal
import json
import os
import sys
import importlib.util
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

# Setup path for imports
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))
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
# and are directly importable; the rest use hyphenated filenames and must
# be loaded via importlib.
try:
    _memory_retriever = _load_hyphenated_module("memory_retriever", "memory-retriever.py")
    _hybrid_search = _load_hyphenated_module("hybrid_search", "hybrid-search.py")
    _ml_ranker = _load_hyphenated_module("ml_ranker", "ml-ranker.py")
    _memory_validator = _load_hyphenated_module("memory_validator", "memory-validator.py")

    MemoryRetriever = _memory_retriever.MemoryRetriever
    SearchResult = _memory_retriever.SearchResult
    HybridSearchEngine = _hybrid_search.HybridSearchEngine
    MLRanker = _ml_ranker.MLRanker
    MemoryValidator = _memory_validator.MemoryValidator

    from cache_manager import CacheManager
    from summarizer import MemorySummarizer
    from anomaly_detector import AnomalyDetector
    from knowledge_graph import KnowledgeGraph
    from entity_extractor import EntityExtractor
    from chat_interface import ChatAgent
    from memory_scope import filter_memories, infer_memory_scope, scoped_fingerprint
    from brain_eleven.projects.registry import registry_path as project_registry_path
    from memory_store import MemoryStore, MemoryStoreConflict
    from capture_safety import CaptureSafetyError, evaluate_capture
except ImportError as e:
    print(f"Warning: Could not import components: {e}")

# Setup logging
from logging_config import setup_logging
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
    project_id: str = Field(default="", description="Opaque project namespace identifier")
    project_root: Optional[str] = Field(default=None, description="Project root used only to derive project_id")
    timestamp: Optional[str] = None

class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    confidence: Optional[float] = None
    status: Optional[str] = None
    expected_revision: Optional[int] = Field(default=None, ge=0)

class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    top_k: int = Field(default=5, ge=1, le=100)
    hybrid: bool = Field(default=True, description="Use hybrid search")
    project_id: Optional[str] = None
    retrieval_scope: Literal["default", "global", "project", "all"] = "default"

class RankRequest(BaseModel):
    query: str
    candidates: List[Dict]
    project_id: Optional[str] = None
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

        ranker = MLRanker()
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
        # cost is negligible here (fallback embeddings, no network calls).
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

# API key gate. BRAIN_ELEVEN_API_KEY unset means auth is OFF - fine for
# local-only use bound to 127.0.0.1, but this endpoint set has no other
# access control (memory CRUD, cache clear, graph rebuild, chat), so
# anything reachable beyond localhost MUST set this. Logged loudly at
# startup rather than failing silently either way.
API_KEY = os.environ.get("BRAIN_ELEVEN_API_KEY")
_PUBLIC_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}

@app.middleware("http")
async def require_api_key(request: Request, call_next):
    if API_KEY and request.url.path not in _PUBLIC_PATHS:
        if request.headers.get("X-API-Key") != API_KEY:
            return JSONResponse(status_code=401, content={"detail": "Missing or invalid X-API-Key header"})
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
async def search(request: SearchRequest):
    """
    Hybrid search: combines lexical + semantic search

    Returns ranked results with combined scores
    """
    try:
        logger.info(f"Search query: {request.query}")

        # Load memories
        validated_file = vault_path / ".claude/validated-memory.json"
        if not validated_file.exists():
            raise HTTPException(status_code=404, detail="No memories found")

        with open(validated_file) as f:
            data = json.load(f)
            memories = filter_memories(
                data.get("validated_memory", []),
                project_id=request.project_id,
                retrieval_scope=request.retrieval_scope,
            )

        if not memories:
            return {"results": [], "query": request.query, "count": 0}

        # Cache key incorporates query + top_k + a fingerprint of the memory
        # set size so a cache entry can't outlive additions to the vault.
        cache_key = CacheManager.make_key(
            "search", request.query, request.top_k, request.project_id or "global-only",
            request.retrieval_scope, len(memories),
        )

        def compute_results():
            return hybrid_engine.search(
                request.query, memories, top_k=request.top_k,
                project_id=request.project_id,
                retrieval_scope=request.retrieval_scope,
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
async def rank_results(request: RankRequest):
    """
    ML-based ranking: applies 5-feature weighting to candidates

    Features: search_relevance, memory_quality, recency, novelty, match_type
    """
    try:
        # Load memories for context
        validated_file = vault_path / ".claude/validated-memory.json"
        with open(validated_file) as f:
            data = json.load(f)
            memories = filter_memories(
                data.get("validated_memory", []),
                project_id=request.project_id,
                retrieval_scope=request.retrieval_scope,
            )

        # Apply the same visibility policy to the candidate set itself. The
        # context corpus alone is not enough: otherwise a caller could send a
        # foreign project's candidate directly to /rank and bypass retrieval.
        candidates = filter_memories(
            request.candidates,
            project_id=request.project_id,
            retrieval_scope=request.retrieval_scope,
        )
        ranked = ranker.rank(request.query, candidates, memories)

        return {
            "results": ranked,
            "query": request.query,
            "count": len(ranked),
            "timestamp": datetime.now().isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
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

        cache_key = CacheManager.make_key("embed", query)

        def compute_embedding():
            gen = EmbeddingGenerator(str(vault_path))
            return gen.embed_text(query).tolist()

        embedding = cache.get_or_compute(cache_key, compute_embedding) if cache else compute_embedding()

        return {
            "text": query,
            "embedding": embedding,
            "dimension": len(embedding),
            "model": "text-embedding-3-small"
        }
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Memory Endpoints
# ============================================================================

@app.get("/memories")
async def list_memories(
    skip: int = 0,
    limit: int = 100,
    project_id: Optional[str] = None,
    retrieval_scope: Literal["default", "global", "project", "all"] = "default",
):
    """List all memories"""
    try:
        validated_file = vault_path / ".claude/validated-memory.json"
        if not validated_file.exists():
            return {"memories": [], "total": 0}

        with open(validated_file) as f:
            data = json.load(f)
            memories = filter_memories(
                data.get("validated_memory", []),
                project_id=project_id,
                retrieval_scope=retrieval_scope,
            )

        # Pagination
        total = len(memories)
        memories = memories[skip:skip + limit]

        return {
            "memories": memories,
            "total": total,
            "skip": skip,
            "limit": limit
        }
    except Exception as e:
        logger.error(f"List memories error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/memories")
async def create_memory(memory: MemoryCreate):
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
async def get_memory(memory_id: str):
    """Get specific memory"""
    try:
        validated_file = vault_path / ".claude/validated-memory.json"
        if not validated_file.exists():
            raise HTTPException(status_code=404, detail="Memory not found")

        with open(validated_file) as f:
            data = json.load(f)
            memories = data.get("validated_memory", [])

        memory = next((m for m in memories if m.get("memory_id") == memory_id), None)
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")

        return memory
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get memory error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/memories/{memory_id}")
async def update_memory(memory_id: str, update: MemoryUpdate):
    """Update memory"""
    try:
        if update.content is not None:
            safety = evaluate_capture(update.content)
            if not safety.accepted:
                raise HTTPException(status_code=422, detail=safety.to_dict())
        store = MemoryStore(vault_path)

        def mutate(data):
            memories = data.get("validated_memory", [])
            memory = next((m for m in memories if m.get("memory_id") == memory_id), None)
            if not memory:
                raise HTTPException(status_code=404, detail="Memory not found")

            if update.content:
                memory["content"] = update.content
            if update.confidence is not None:
                memory["confidence"] = update.confidence
            if update.status:
                memory["status"] = update.status

            scope, _project, project_id = infer_memory_scope(memory)
            memory["scope"] = scope
            memory["project_id"] = project_id
            memory["dedup_fingerprint"] = scoped_fingerprint(
                memory.get("content", ""), scope, project_id, memory.get("type", "")
            )
            memory["updated_at"] = datetime.now().isoformat()
            return memory

        memory, persisted = store.transact(
            mutate,
            expected_revision=update.expected_revision,
        )

        if cache:
            cache.clear()
        _rebuild_graph()

        logger.info(f"Updated memory: {memory_id}")
        return {**memory, "store_revision": persisted["revision"]}
    except HTTPException:
        raise
    except MemoryStoreConflict as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MEMORY_STORE_REVISION_CONFLICT",
                "expected_revision": e.expected_revision,
                "actual_revision": e.actual_revision,
            },
        )
    except Exception as e:
        logger.error(f"Update memory error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str, expected_revision: Optional[int] = Query(default=None, ge=0)):
    """Delete memory (soft delete - mark as deleted)"""
    try:
        store = MemoryStore(vault_path)

        def mutate(data):
            memories = data.get("validated_memory", [])
            memory = next((m for m in memories if m.get("memory_id") == memory_id), None)
            if not memory:
                raise HTTPException(status_code=404, detail="Memory not found")
            memory["status"] = "deleted"
            memory["deleted_at"] = datetime.now().isoformat()
            return memory

        _memory, persisted = store.transact(mutate, expected_revision=expected_revision)

        if cache:
            cache.clear()
        _rebuild_graph()

        logger.info(f"Deleted memory: {memory_id}")
        return {
            "status": "deleted",
            "memory_id": memory_id,
            "store_revision": persisted["revision"],
        }
    except HTTPException:
        raise
    except MemoryStoreConflict as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MEMORY_STORE_REVISION_CONFLICT",
                "expected_revision": e.expected_revision,
                "actual_revision": e.actual_revision,
            },
        )
    except Exception as e:
        logger.error(f"Delete memory error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
    try:
        summarizer = MemorySummarizer(str(vault_path))
        digest = summarizer.generate_digest(
            days=days,
            top_n_per_type=top_n,
            project_id=project_id,
            retrieval_scope=retrieval_scope,
        )
        return digest
    except Exception as e:
        logger.error(f"Digest error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/anomalies")
async def get_anomalies():
    """
    Scan the memory store for structural anomalies: duplicates, stale
    open loops, broken supersession links, scoring inconsistencies, etc.
    """
    try:
        detector = AnomalyDetector(str(vault_path))
        report = detector.detect_all()
        return report
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
    type: Optional[str] = None,
    name_contains: Optional[str] = None,
    project_id: Optional[str] = None,
    retrieval_scope: Literal["default", "global", "project", "all"] = "default",
):
    """List entities, optionally filtered by type and/or name substring."""
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialized")
    current_graph = _ensure_graph_current()
    return {
        "entities": current_graph.find_entities(
            entity_type=type,
            name_contains=name_contains,
            project_id=project_id,
            retrieval_scope=retrieval_scope,
        )
    }

@app.get("/graph/entities/{entity_id}/relationships")
async def graph_entity_relationships(
    entity_id: str,
    direction: str = "both",
    project_id: Optional[str] = None,
    retrieval_scope: Literal["default", "global", "project", "all"] = "default",
):
    """Relationships for one entity. direction: out | in | both."""
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialized")
    current_graph = _ensure_graph_current()
    if not current_graph.is_entity_visible(entity_id, project_id, retrieval_scope):
        raise HTTPException(status_code=404, detail="Entity not found")
    return {
        "entity_id": entity_id,
        "relationships": current_graph.get_relationships(
            entity_id,
            direction=direction,
            project_id=project_id,
            retrieval_scope=retrieval_scope,
        ),
    }

@app.get("/graph/traverse/{entity_id}")
async def graph_traverse(
    entity_id: str,
    depth: int = 2,
    project_id: Optional[str] = None,
    retrieval_scope: Literal["default", "global", "project", "all"] = "default",
):
    """Subgraph reachable from an entity within `depth` hops (either direction)."""
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialized")
    current_graph = _ensure_graph_current()
    if not current_graph.is_entity_visible(entity_id, project_id, retrieval_scope):
        raise HTTPException(status_code=404, detail="Entity not found")
    return current_graph.traverse(
        entity_id,
        max_depth=depth,
        project_id=project_id,
        retrieval_scope=retrieval_scope,
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
    project_id: Optional[str] = None
    retrieval_scope: Literal["default", "global", "project", "all"] = "default"

@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Rule-based chat over the memory system (see chat_interface.py) -
    answers are grounded in real search/digest/anomaly/graph results, not
    LLM-generated free text, since no LLM is configured.
    """
    if not chat_agent:
        raise HTTPException(status_code=503, detail="Chat agent not initialized")
    try:
        _ensure_graph_current()
        return chat_agent.chat(
            request.message,
            conversation_id=request.conversation_id,
            project_id=request.project_id,
            retrieval_scope=request.retrieval_scope,
        )
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
            "⚠️  BRAIN_ELEVEN_API_KEY is not set - every endpoint except "
            "/health is unauthenticated. Fine for 127.0.0.1-only local use; "
            "set it before binding to anything else reachable off this machine."
        )

    # Default to loopback-only: memory CRUD, cache clear, and graph rebuild
    # have no access control beyond the API key gate above, so binding
    # 0.0.0.0 without also setting BRAIN_ELEVEN_API_KEY exposes all of it
    # to the network. Override via BRAIN_ELEVEN_HOST - docker-compose.yml
    # sets it to 0.0.0.0 explicitly, since container network isolation is
    # the real boundary there, not the bind address.
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
