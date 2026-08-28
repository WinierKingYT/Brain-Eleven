---
type: decision
title: BM25 Relevance Scoring & TF-IDF Tuning
category: Search & Indexing
status: active
created: 2026-08-28
source: search-indexing-systems (Hamle 7)
tags: [search, relevance, bm25, scoring, ranking]
---

# BM25 Scoring & Relevance Tuning

**Pattern:** Probabilistic ranking function balancing term frequency with document length normalization.

## The Problem

Raw term frequency (TF) favors long documents; search quality degrades:
- Query "elasticsearch" → long document (10KB) ranks above short (1KB) even if less relevant
- Naive TF-IDF treats all terms equally
- Click-through rates suffer with bad ranking

## Solution: BM25 Algorithm

```
BM25(term, doc) = IDF(term) × (TF × (k1 + 1)) / (TF + k1 × (1 - b + b × (doc_length / avg_doc_length)))

Where:
  IDF(term) = log(N - n + 0.5) / (n + 0.5)  [inverse doc frequency]
  TF = term frequency in document
  k1 = saturation parameter (default 1.2; higher = longer tail)
  b = length normalization (default 0.75; higher = penalize long docs more)
  doc_length = length of document
  avg_doc_length = average document length in corpus
  N = total documents
  n = documents containing term
```

**Intuition:**
- Rare term (low n) → high IDF → high score ✓
- Common term (high n) → low IDF → low score ✓
- TF saturation (k1) prevents high-frequency terms dominating ✓
- Length normalization (b) prevents 10x-longer documents from auto-winning ✓

## Production Example: Elasticsearch

```bash
# Default BM25 in Elasticsearch
GET products/_search
{
  "query": {
    "multi_match": {
      "query": "elasticsearch cluster",
      "fields": ["title^2", "description"]  # title field boosted 2x
    }
  }
}

# Tuning k1 and b
GET products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "title": {
              "query": "elasticsearch",
              "boost": 2
            }
          }
        }
      ]
    }
  }
}

# Advanced: custom BM25 parameters
PUT products/_settings
{
  "index.similarity.default.type": "BM25",
  "index.similarity.default.k1": 1.5,  # Higher saturation
  "index.similarity.default.b": 0.5    # Less length normalization
}
```

## Tuning Parameters by Domain

| Domain | k1 | b | Why |
|--------|-----|-----|------|
| **News articles** | 1.2 | 0.75 | Default; good balance |
| **Product search** | 2.0 | 0.5 | Shorter docs (product pages); emphasize exact match |
| **Academic papers** | 1.5 | 0.9 | Longer docs (papers); penalize length less |
| **Log search** | 3.0 | 0.2 | Very short logs; TF more important |

## Measuring Ranking Quality

```python
def measure_ranking_quality(queries_judgments):
  """
  queries_judgments = [
    {"query": "elasticsearch", "relevant": [1, 3, 5]},  # Doc 1,3,5 relevant
    {"query": "search", "relevant": [2, 4]}
  ]
  """
  
  mrr = []  # Mean Reciprocal Rank
  for q in queries_judgments:
    results = es.search(q['query'], top_k=10)
    for i, doc_id in enumerate(results):
      if doc_id in q['relevant']:
        mrr.append(1 / (i + 1))  # Reciprocal of rank
        break
  
  return sum(mrr) / len(mrr)  # Average MRR

# Industry targets: MRR > 0.8 (first relevant result in top 1-2)
```

## When to Use

✓ **Default for all full-text search** (Elasticsearch uses BM25 by default)
✓ **News, e-commerce, product search**
✓ **Multi-field queries** (with field-level boosting)

## Production Gotchas

**1. Field Boosting Overrides Relevance**
- Boost title 10x → title matches always top even if less relevant
- **Fix:** Use moderate boosts (1.5-2x); validate with A/B testing

**2. IDF Per-Shard Inconsistency**
- Index split across 5 shards; shard 1 has "elasticsearch" in 100 docs
- Shard 2 has "elasticsearch" in 10 docs
- Same query gets different IDF per shard → inconsistent scores
- **Fix:** Use global term statistics (not per-shard) in Elasticsearch 7.x+

**3. Length Normalization Can Backfire**
- Very short documents (summaries) vs full documents scored unfairly
- **Fix:** Adjust b parameter; test on your content; consider using separate indexes

**4. TF Saturation (k1) Masks Relevance**
- Multiple occurrences of term have diminishing returns
- Query "elasticsearch elasticsearch" shouldn't score 2x higher
- **Fix:** k1=1.2 is reasonable; monitor query behavior

---

**Bağlantılar:**
- [[hamle7-search-001-inverted-index]] (term frequencies for BM25)
- [[hamle7-search-004-boost-personalization]] (applying custom scoring)
- [[hamle5-performance-002-apm-instrumentation]] (monitoring search quality)
