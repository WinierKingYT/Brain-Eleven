---
type: decision
title: Dense Vector Search & Embedding-Based Relevance
category: Search & Indexing
status: active
created: 2026-08-28
source: search-indexing-systems (Hamle 7)
tags: [search, vector-search, embeddings, semantic-search, hnsw]
---

# Vector Search with Embeddings

**Pattern:** Semantic search capturing intent via dense vectors (embeddings) + approximate nearest neighbor indexing.

## The Problem

Lexical search (BM25) misses semantic intent:
- "headache cure" should match "pain relief" (semantically similar but different keywords)
- "cat" (animal) vs "CAT" (Caterpillar machinery) treated same
- Typos and synonyms not captured

## Solution: Dense Embeddings + HNSW Index

```python
from sentence_transformers import SentenceTransformer
from elasticsearch import Elasticsearch

# 1. Generate embeddings at index time
model = SentenceTransformer('all-MiniLM-L6-v2')  # 384-dim embeddings

documents = [
  {"id": 1, "text": "paracetamol for headaches"},
  {"id": 2, "text": "aspirin pain relief"},
  {"id": 3, "text": "ibuprofen anti-inflammatory"}
]

for doc in documents:
  embedding = model.encode(doc['text']).tolist()
  es.index(index='medicines', doc_type='_doc', id=doc['id'], body={
    'text': doc['text'],
    'embedding': embedding  # Dense vector
  })

# 2. Query with same embedding model
query = "pain relief medication"
query_embedding = model.encode(query).tolist()

# 3. Search via Elasticsearch dense vector
results = es.search(index='medicines', body={
  'query': {
    'script_score': {
      'query': {'match_all': {}},
      'script': {
        'source': "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
        'params': {'query_vector': query_embedding}
      }
    }
  }
})

# Results ranked by cosine similarity
# Doc 2 ("aspirin pain relief") has highest similarity to "pain relief medication"
```

## HNSW Indexing (Hierarchical Navigable Small World)

```
HNSW structure (simplified):
  Level 2:    A -----> C
              |        |
  Level 1:  A -- B -- C -- D
            |  \ | / |  /
  Level 0: A -- B -- C -- D -- E

Benefits:
- Logarithmic search complexity: O(log N)
- Fast approximate nearest neighbor search
- Scales to billions of documents
```

**Elasticsearch HNSW Configuration:**

```bash
PUT medicines
{
  "mappings": {
    "properties": {
      "embedding": {
        "type": "dense_vector",
        "dims": 384,
        "index": true,
        "similarity": "cosine"  # or "l2", "inner_product"
      }
    }
  },
  "settings": {
    "index.vector.hnsw.ef_construction": 200,  # Higher = better recall, slower build
    "index.vector.hnsw.max_connections": 16     # Connections per node
  }
}
```

## Hybrid Search: BM25 + Vector

```python
# Combine lexical (BM25) + semantic (vector) scores
results = es.search(index='medicines', body={
  "query": {
    "bool": {
      "should": [
        {
          "multi_match": {
            "query": "pain relief",
            "fields": ["text"],
            "boost": 2  # Weight lexical 2x
          }
        },
        {
          "script_score": {
            "query": {"match_all": {}},
            "script": {
              "source": "cosineSimilarity(params.query_vector, 'embedding')",
              "params": {"query_vector": query_embedding}
            },
            "boost": 1  # Weight vector 1x
          }
        }
      ]
    }
  }
})

# RRF (Reciprocal Rank Fusion): normalize and combine ranks
# Doc A: BM25 rank=1, Vector rank=3 → RRF = 1/2 + 1/4 = 0.75
# Doc B: BM25 rank=5, Vector rank=1 → RRF = 1/6 + 1/2 = 0.667
# Doc A ranks higher (0.75 > 0.667)
```

## When to Use

✓ **Semantic search** (intent matching, cross-lingual)
✓ **E-commerce** (product recommendations)
✓ **Content discovery** (similar articles, documents)
✓ **Hybrid search** (combine with BM25 for best precision)

✗ **Exact match search** (SKU lookup; use keyword fields)
✗ **Real-time latency <10ms** (embeddings add 100-500ms)

## Production Gotchas

**1. Embedding Model Inference Latency**
- Generating embedding takes 100-500ms
- **Fix:** Batch inference; use smaller models (MiniLM vs BERT); cache frequent queries

**2. Vector Dimension Affects Memory**
- 384-dim × 1B docs = 1.5TB memory
- **Fix:** Use smaller dimensions (96-dim for fast search, 768-dim for precision); quantize to int8

**3. Different Models Produce Incompatible Vectors**
- Embedding from BERT ≠ from MiniLM; can't mix in same index
- **Fix:** Keep model version in metadata; version indexes separately

**4. HNSW Index Building is CPU-Intensive**
- Building index for 1B docs takes hours
- **Fix:** Build offline; use pre-built indexes; incrementally add documents

---

**Bağlantılar:**
- [[hamle7-search-001-inverted-index]] (lexical search foundation)
- [[hamle7-search-005-bm25-scoring]] (combining with BM25)
- [[hamle5-performance-002-apm-instrumentation]] (monitoring search latency)
