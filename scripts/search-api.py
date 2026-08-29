#!/usr/bin/env python3
"""
Brain-Eleven v3 REST API
Complete API server with hybrid search, ML ranking, and memory management
"""

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional, Dict
import json
import sys
from pathlib import Path
import logging

# Setup path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Import our components
try:
    from memory_retriever import MemoryRetriever, SearchResult
    from hybrid_search import HybridSearchEngine
    from ml_ranker import MLRanker
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
    timestamp: Optional[str] = None

class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    confidence: Optional[float] = None
    status: Optional[str] = None

class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    top_k: int = Field(default=5, ge=1, le=100)
    hybrid: bool = Field(default=True, description="Use hybrid search")

class RankRequest(BaseModel):
    query: str
    candidates: List[Dict]

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str = "3.0.0"
    services: Dict[str, str]

# ============================================================================
# FastAPI App Setup
# ============================================================================

app = FastAPI(
    title="Brain-Eleven v3",
    description="Advanced memory system with semantic search and ML ranking",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
vault_path = Path.home() / "Documents/Brain-Eleven"
memory_store = None
hybrid_engine = None
ranker = None

# ============================================================================
# Initialization
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global memory_store, hybrid_engine, ranker

    logger.info("🚀 Starting Brain-Eleven API...")

    try:
        # Load memory store
        memory_store = MemoryRetriever(str(vault_path))
        logger.info("✅ Memory store initialized")

        # Initialize hybrid search
        hybrid_engine = HybridSearchEngine(str(vault_path))
        logger.info("✅ Hybrid search engine initialized")

        # Initialize ML ranker
        ranker = MLRanker()
        logger.info("✅ ML ranker initialized")

        logger.info("✅ All services ready!")
    except Exception as e:
        logger.error(f"❌ Startup error: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 Shutting down Brain-Eleven API...")

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
        validated_file = vault_path / ".claude/validated-memory.json"
        if validated_file.exists():
            with open(validated_file) as f:
                data = json.load(f)
                memory_count = len(data.get("validated_memory", []))
        else:
            memory_count = 0

        return {
            "status": "operational",
            "timestamp": datetime.now().isoformat(),
            "memory_count": memory_count,
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
            memories = data.get("validated_memory", [])

        if not memories:
            return {"results": [], "query": request.query, "count": 0}

        # Perform hybrid search
        results = hybrid_engine.search(request.query, memories, top_k=request.top_k)

        logger.info(f"Search returned {len(results)} results")

        return {
            "results": results,
            "query": request.query,
            "count": len(results),
            "timestamp": datetime.now().isoformat()
        }
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
            memories = data.get("validated_memory", [])

        # Rank candidates
        ranked = ranker.rank(request.query, request.candidates, memories)

        return {
            "results": ranked,
            "query": request.query,
            "count": len(ranked),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Ranking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/embed")
async def embed_text(query: str = Query(..., description="Text to embed")):
    """
    Generate embedding for text using text-embedding-3-small
    """
    try:
        from embedding_generator import EmbeddingGenerator

        gen = EmbeddingGenerator(str(vault_path))
        embedding = gen.embed_text(query)

        return {
            "text": query,
            "embedding": embedding.tolist(),
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
async def list_memories(skip: int = 0, limit: int = 100):
    """List all memories"""
    try:
        validated_file = vault_path / ".claude/validated-memory.json"
        if not validated_file.exists():
            return {"memories": [], "total": 0}

        with open(validated_file) as f:
            data = json.load(f)
            memories = data.get("validated_memory", [])

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
    """Create new memory"""
    try:
        # Load current memories
        validated_file = vault_path / ".claude/validated-memory.json"
        if validated_file.exists():
            with open(validated_file) as f:
                data = json.load(f)
                memories = data.get("validated_memory", [])
        else:
            memories = []

        # Create new memory with ULID
        from datetime import datetime
        memory_id = f"mem_{datetime.now().timestamp():.0f}"

        new_memory = {
            "memory_id": memory_id,
            "type": memory.type,
            "content": memory.content,
            "confidence": memory.confidence,
            "timestamp": memory.timestamp or datetime.now().isoformat(),
            "status": "active"
        }

        memories.append(new_memory)

        # Save back
        data = {"validated_memory": memories}
        with open(validated_file, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Created memory: {memory_id}")

        return {
            "memory_id": memory_id,
            "status": "created",
            "timestamp": datetime.now().isoformat()
        }
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
        validated_file = vault_path / ".claude/validated-memory.json"
        with open(validated_file) as f:
            data = json.load(f)
            memories = data.get("validated_memory", [])

        memory = next((m for m in memories if m.get("memory_id") == memory_id), None)
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")

        # Update fields
        if update.content:
            memory["content"] = update.content
        if update.confidence is not None:
            memory["confidence"] = update.confidence
        if update.status:
            memory["status"] = update.status

        memory["updated_at"] = datetime.now().isoformat()

        # Save back
        with open(validated_file, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Updated memory: {memory_id}")
        return memory
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update memory error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str):
    """Delete memory (soft delete - mark as deleted)"""
    try:
        validated_file = vault_path / ".claude/validated-memory.json"
        with open(validated_file) as f:
            data = json.load(f)
            memories = data.get("validated_memory", [])

        memory = next((m for m in memories if m.get("memory_id") == memory_id), None)
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")

        # Soft delete
        memory["status"] = "deleted"
        memory["deleted_at"] = datetime.now().isoformat()

        with open(validated_file, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Deleted memory: {memory_id}")
        return {"status": "deleted", "memory_id": memory_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete memory error: {e}")
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

    uvicorn.run(
        "search_api:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        access_log=True
    )
