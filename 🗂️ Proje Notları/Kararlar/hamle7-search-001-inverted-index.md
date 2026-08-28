---
type: decision
title: Inverted Index Construction & Posting Lists
category: Search & Indexing
status: active
created: 2026-08-28
source: search-indexing-systems (Hamle 7)
tags: [search, elasticsearch, indexing, inverted-index, full-text-search]
---

# Inverted Index & Posting Lists

**Pattern:** Mapping terms to document IDs for millisecond full-text search across billions of documents.

## The Problem

Raw documents are unstructured. Queries like "elasticsearch cluster" need to find matching documents in milliseconds from billions of docs.

Forward index (doc → terms) is useless for search; need reverse lookup (term → docs).

## Solution: Inverted Index

```
Document collection:
  Doc 1: "elasticsearch distributed search"
  Doc 2: "elasticsearch cluster configuration"
  Doc 3: "distributed systems design"

Inverted index (term → posting list):
  "elasticsearch" → {docs: [1, 2], positions: [[0], [0]], freq: [1, 1]}
  "distributed" → {docs: [1, 3], positions: [[1], [0]], freq: [1, 1]}
  "search" → {docs: [1], positions: [[2]], freq: [1]}
  "cluster" → {docs: [2], positions: [[1]], freq: [1]}
  "configuration" → {docs: [2], positions: [[2]], freq: [1]}
  "systems" → {docs: [3], positions: [[1]], freq: [1]}
  "design" → {docs: [3], positions: [[2]], freq: [1]}

Query: "elasticsearch cluster"
  Intersection: [1,2] ∩ [2] = [2]  (Doc 2 matches both terms)
```

## Efficient Posting List Storage

```python
# Delta encoding: store differences instead of absolute doc IDs
# Posting list [1, 5, 12, 18] → [1, 4, 7, 6] (deltas)
# Saves ~40% space; decompresses to same order

def encode_posting_list(doc_ids):
  """Convert [1, 5, 12, 18] to deltas [1, 4, 7, 6]"""
  deltas = [doc_ids[0]]
  for i in range(1, len(doc_ids)):
    deltas.append(doc_ids[i] - doc_ids[i-1])
  return deltas

def decode_posting_list(deltas):
  """Reverse: [1, 4, 7, 6] to [1, 5, 12, 18]"""
  doc_ids = [deltas[0]]
  for i in range(1, len(deltas)):
    doc_ids.append(doc_ids[-1] + deltas[i])
  return doc_ids
```

## Multi-Term Query: Intersection Algorithm

```python
# Naive intersection: too slow for large posting lists
def naive_intersection(posting_lists):
  result = set(posting_lists[0])
  for posting_list in posting_lists[1:]:
    result = result.intersection(set(posting_list))
  return result

# Better: merge sorted lists
def sorted_intersection(posting_lists):
  """Merge n sorted posting lists; O(n*log_n * max_list_size)"""
  if not posting_lists:
    return []
  
  # Sort by list size (smallest first = fewer comparisons)
  sorted_lists = sorted(posting_lists, key=len)
  
  result = set(sorted_lists[0])
  for posting_list in sorted_lists[1:]:
    result = result.intersection(set(posting_list))
    if not result:
      return []
  
  return sorted(result)

# Best (production): WAND (Weak AND) skips non-competitive docs
def wand_intersection(posting_lists, k=10):
  """Skip documents that can't make top-k results"""
  # E.g., if doc 5 has low score, skip it even if term matches
  # Essential for high-recall queries on large datasets
  pass
```

## Production: Elasticsearch Inverted Index

```bash
# Elasticsearch stores inverted index automatically
curl -X PUT "localhost:9200/products" -H 'Content-Type: application/json' -d '{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "standard"  # Inverted index on tokenized text
      },
      "sku": {
        "type": "keyword"  # No tokenization; exact match only
      }
    }
  }
}'

# Query uses inverted index
curl -X GET "localhost:9200/products/_search" -H 'Content-Type: application/json' -d '{
  "query": {
    "multi_match": {
      "query": "elasticsearch cluster",
      "fields": ["title", "description"]  # Search both fields' inverted indexes
    }
  }
}'
```

## When to Use

✓ **Full-text search** (every search system)
✓ **Scalable beyond 100K documents** (inverted index required)
✓ **Multi-term queries** (phrase queries need position data)

## Production Gotchas

**1. Large Posting Lists Slow Down Intersection**
- "elasticsearch" appears in 1M docs; intersection with "cluster" (50 docs) still scans 1M
- **Fix:** Use WAND algorithm; rearrange query (filter rare terms first)

**2. Position Data Increases Memory**
- Phrase queries ("elasticsearch distributed") need positions
- Adds 2-3x memory per term
- **Fix:** Only store positions for fields needing phrase queries

**3. Posting List Compression Loss**
- Delta encoding + compression; decompression adds latency
- **Fix:** Cache frequently accessed posting lists in-memory

---

**Bağlantılar:**
- [[hamle7-search-002-analyzer-chain]] (tokenization for indexing)
- [[hamle7-search-003-vector-search]] (semantic search alternative)
- [[hamle7-search-005-bm25-scoring]] (ranking indexed results)
