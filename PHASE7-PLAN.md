# Phase 7: Advanced Retrieval & Semantic Search

**Objective:** Implement semantic search with embeddings + ML-based ranking

## Architecture Overview

```
Daily Notes / Prior Memories
        ↓
Memory Compiler (extracts)
        ↓
Memory Validator (scores)
        ↓
Embedding Generator ← (NEW) OpenAI API
        ↓
Embedding Store (Vector DB)
        ↓
Query → [Lexical Search] + [Semantic Search] → Hybrid Results
        ↓
ML Ranker ← (NEW) Feature-based ranking
        ↓
Top-K Results (Ranked by relevance + recency + novelty)
```

## Phase 7 Components

### 1. Embedding Generator
**File:** `scripts/embedding-generator.py`

```python
class EmbeddingGenerator:
    """Generate and store vector embeddings for memories"""
    
    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        
    def embed_memory(self, memory_id: str, content: str) -> np.ndarray:
        """Generate embedding for a memory"""
        response = self.client.embeddings.create(
            input=content,
            model=self.model
        )
        return np.array(response.data[0].embedding)
    
    def batch_embed(self, memories: List[Dict]) -> Dict[str, np.ndarray]:
        """Batch embed multiple memories"""
        embeddings = {}
        for mem in memories:
            embeddings[mem['memory_id']] = self.embed_memory(
                mem['memory_id'],
                mem['content']
            )
        return embeddings
```

**Features:**
- OpenAI embeddings (ada-002, 1536 dimensions)
- Batch processing for efficiency
- Embedding cache (JSON store)
- Error handling for API failures

### 2. Embedding Store
**File:** `scripts/embedding-store.py`

```python
class EmbeddingStore:
    """Persistent storage for embeddings"""
    
    def __init__(self, vault_path: str):
        self.store_file = Path(vault_path) / ".claude/embeddings.json"
        self.embeddings = {}
        self._load()
    
    def save_embedding(self, memory_id: str, embedding: np.ndarray):
        """Save embedding (store as list for JSON)"""
        self.embeddings[memory_id] = embedding.tolist()
        self._persist()
    
    def get_embedding(self, memory_id: str) -> np.ndarray:
        """Retrieve embedding as numpy array"""
        if memory_id in self.embeddings:
            return np.array(self.embeddings[memory_id])
        return None
```

**Structure:**
```json
{
  "embeddings": {
    "01M155WB9AKKTCZWTFRDDZR4W7": [0.123, -0.456, ...],
    "01M155WB9FCSPSFQCFM8NVATS8": [-0.789, 0.234, ...]
  },
  "metadata": {
    "model": "text-embedding-3-small",
    "dimension": 1536,
    "last_updated": "2026-08-29T12:00:00"
  }
}
```

### 3. Semantic Search Engine
**File:** `scripts/semantic-search.py`

```python
class SemanticSearchEngine:
    """Semantic similarity search using embeddings"""
    
    def __init__(self, embedding_store: EmbeddingStore):
        self.store = embedding_store
        self.generator = EmbeddingGenerator()
    
    def search(self, query: str, memories: List[Dict], top_k: int = 5):
        """Semantic search: embed query, find similar memories"""
        # Generate query embedding
        query_embedding = self.generator.embed_memory("query", query)
        
        # Compute similarity with all memories
        similarities = []
        for mem in memories:
            embedding = self.store.get_embedding(mem['memory_id'])
            if embedding is not None:
                sim = self._cosine_similarity(query_embedding, embedding)
                similarities.append({
                    'memory_id': mem['memory_id'],
                    'similarity': sim,
                    'type': 'semantic'
                })
        
        # Return top-k
        return sorted(similarities, key=lambda x: x['similarity'], reverse=True)[:top_k]
    
    @staticmethod
    def _cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
        """Cosine similarity between two vectors"""
        return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
```

**Features:**
- Query embedding generation
- Cosine similarity matching
- Top-K result ranking
- Handles missing embeddings gracefully

### 4. Hybrid Search Engine
**File:** `scripts/hybrid-search.py`

```python
class HybridSearchEngine:
    """Combine lexical + semantic search"""
    
    def __init__(self, embedding_store: EmbeddingStore, retriever: MemoryRetriever):
        self.semantic = SemanticSearchEngine(embedding_store)
        self.lexical = retriever  # Use Phase 4 retriever
    
    def search(self, query: str, memories: List[Dict], top_k: int = 5):
        """Hybrid search with weighted combination"""
        # Lexical results (40% weight)
        lexical_results = self.lexical.retrieve(query, memories, top_k=10)
        
        # Semantic results (60% weight)
        semantic_results = self.semantic.search(query, memories, top_k=10)
        
        # Merge and rerank
        merged = self._merge_results(lexical_results, semantic_results)
        
        # Apply ML ranking
        ranked = self._rank_results(merged, query)
        
        return ranked[:top_k]
    
    def _merge_results(self, lexical: List, semantic: List) -> List[Dict]:
        """Combine results from both search methods"""
        combined = {}
        
        # Add lexical (40% weight)
        for i, result in enumerate(lexical):
            mem_id = result['memory_id']
            combined[mem_id] = {
                'memory_id': mem_id,
                'lexical_score': result.get('score', 0),
                'lexical_rank': i,
                'semantic_score': 0
            }
        
        # Add semantic (60% weight)
        for i, result in enumerate(semantic):
            mem_id = result['memory_id']
            if mem_id in combined:
                combined[mem_id]['semantic_score'] = result['similarity']
                combined[mem_id]['semantic_rank'] = i
            else:
                combined[mem_id] = {
                    'memory_id': mem_id,
                    'lexical_score': 0,
                    'semantic_score': result['similarity'],
                    'semantic_rank': i
                }
        
        return list(combined.values())
```

**Ranking Formula:**
```
score = (lexical_score × 0.4) + (semantic_similarity × 0.6)
```

### 5. ML Ranking Engine
**File:** `scripts/ml-ranker.py`

```python
class MLRanker:
    """Machine learning-based ranking using multiple features"""
    
    def __init__(self):
        self.weights = {
            'search_relevance': 0.40,  # Combined lex + semantic
            'memory_quality': 0.20,    # Quality score from validator
            'recency': 0.15,           # How recent
            'novelty': 0.15,           # Novelty score
            'match_type': 0.10         # Exact, partial, fuzzy
        }
    
    def rank(self, query: str, candidates: List[Dict], memories: List[Dict]) -> List[Dict]:
        """Rank candidates using ML features"""
        
        ranked = []
        for candidate in candidates:
            features = self._extract_features(query, candidate, memories)
            score = self._compute_score(features)
            candidate['ml_score'] = score
            ranked.append(candidate)
        
        return sorted(ranked, key=lambda x: x['ml_score'], reverse=True)
    
    def _extract_features(self, query: str, candidate: Dict, memories: List[Dict]) -> Dict:
        """Extract ranking features"""
        
        # Find full memory record
        memory = next((m for m in memories if m['memory_id'] == candidate['memory_id']), None)
        
        return {
            'search_relevance': candidate.get('similarity', 0),
            'memory_quality': memory.get('quality_score', 0.5) if memory else 0.5,
            'recency': self._recency_score(memory) if memory else 0.5,
            'novelty': memory.get('novelty', 0.5) if memory else 0.5,
            'match_type': self._match_type_score(query, candidate)
        }
    
    def _compute_score(self, features: Dict) -> float:
        """Weighted combination of features"""
        score = 0
        for key, weight in self.weights.items():
            score += features[key] * weight
        return score
    
    def _recency_score(self, memory: Dict) -> float:
        """Score based on how recent the memory is"""
        try:
            timestamp = datetime.fromisoformat(memory['timestamp'])
            days_old = (datetime.now() - timestamp).days
            # Decay: 1.0 today, 0.5 at 30 days, 0.1 at 100 days
            return max(0.1, 1.0 - (days_old / 100))
        except:
            return 0.5
    
    def _match_type_score(self, query: str, candidate: Dict) -> float:
        """Score based on match type (exact > partial > fuzzy)"""
        content = candidate.get('content', '').lower()
        query_lower = query.lower()
        
        if query_lower == content[:len(query_lower)]:
            return 1.0  # Exact match
        elif query_lower in content:
            return 0.8  # Partial match
        else:
            return 0.6  # Fuzzy match
```

## Implementation Tasks

### Week 1: Core Embeddings
- [ ] Implement `EmbeddingGenerator` with OpenAI API
- [ ] Create `EmbeddingStore` for persistence
- [ ] Add embedding caching layer
- [ ] Create `.env` template for API keys
- [ ] Test with 46 sample memories

### Week 2: Semantic Search
- [ ] Implement `SemanticSearchEngine`
- [ ] Create `HybridSearchEngine` combining lexical + semantic
- [ ] Implement cosine similarity matching
- [ ] Test semantic vs lexical results
- [ ] Benchmark: speed, quality, relevance

### Week 3: ML Ranking
- [ ] Implement `MLRanker` with feature extraction
- [ ] Create ranking feature matrix
- [ ] Tune weighting parameters
- [ ] Add recency decay function
- [ ] Test ranking quality

### Week 4: Integration & Tests
- [ ] Integrate with existing retriever
- [ ] Create comprehensive test suite (30+ tests)
- [ ] Performance benchmarks
- [ ] Add to SessionStart bootstrap
- [ ] Documentation

## API Integration

### OpenAI Setup
```bash
# Install dependency
pip install openai numpy

# Set API key
export OPENAI_API_KEY="sk-..."
```

### Model Selection
- **text-embedding-3-small** (default)
  - 1536 dimensions
  - Fast & cost-effective
  - 99.9% performance of large
  
- **text-embedding-3-large** (optional)
  - 3072 dimensions
  - More expensive
  - Marginal quality improvement

## Data Structure Updates

### embeddings.json (NEW)
```json
{
  "embeddings": {
    "01M155WB9AKKTCZWTFRDDZR4W7": [0.123, -0.456, ...],
    "01M155WB9FCSPSFQCFM8NVATS8": [-0.789, 0.234, ...]
  },
  "metadata": {
    "model": "text-embedding-3-small",
    "dimension": 1536,
    "last_updated": "2026-08-29T12:00:00"
  }
}
```

### validated-memory.json (UPDATED)
Add to each memory:
```json
{
  "embedding_id": "01M155WB9AKKTCZWTFRDDZR4W7",
  "has_embedding": true,
  "embedding_generated_at": "2026-08-29T10:00:00"
}
```

## Performance Targets

| Operation | Target | Acceptable |
|-----------|--------|------------|
| Generate 1 embedding | < 100ms | < 200ms |
| Query embedding | < 100ms | < 200ms |
| Semantic search (100 memories) | < 500ms | < 1s |
| Hybrid search (100 memories) | < 1s | < 2s |
| ML ranking (10 candidates) | < 100ms | < 200ms |
| Full pipeline (query to top-5) | < 2s | < 5s |

## Testing Strategy

### Unit Tests
- Embedding generation
- Similarity computation
- Feature extraction
- Ranking logic

### Integration Tests
- Hybrid search end-to-end
- Cache behavior
- Error handling (API failures)
- Embedding persistence

### Performance Tests
- Batch embedding speed
- Large memory store queries
- Concurrent requests

## Deployment Checklist

- [ ] OpenAI API key configured
- [ ] Embedding cache working
- [ ] Semantic search tested
- [ ] Hybrid search balanced
- [ ] ML ranking tuned
- [ ] All 40+ tests passing
- [ ] Performance targets met
- [ ] Documentation complete

---

**Estimated Duration:** 3-4 sessions  
**Complexity:** High (3rd party integration + ML)  
**Risk:** Medium (API rate limits, costs)  
**Value:** Very High (10x better search quality)
