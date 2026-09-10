---
type: decision
title: Faceting & Aggregation Query Optimization
category: Search & Indexing
status: active
created: 2026-08-28
source: search-indexing-systems (Hamle 7)
tags: [search, faceting, aggregation, filtering, analytics]
---

# Faceting & Aggregation Optimization

**Pattern:** Fast document counts per category for browse-and-refine UX without full table scans.

## The Problem

E-commerce: "Filter by size (S, M, L, XL) with counts" requires:
- Naive approach: count documents per size (full scan × 4)
- Result: slow; query time 10s+ for each filter

## Solution: Aggregations with Sub-Filters

```bash
# Elasticsearch: Aggregations on filtered data
POST products/_search
{
  "size": 0,  # Count-only query
  "query": {
    "bool": {
      "filter": {
        "term": {"brand.keyword": "Nike"}  # Pre-filter to Nike
      }
    }
  },
  "aggs": {
    "sizes": {
      "terms": {
        "field": "size.keyword",
        "size": 10  # Top 10 sizes
      }
    },
    "colors": {
      "terms": {
        "field": "color.keyword",
        "size": 100
      }
    }
  }
}

# Response:
{
  "aggregations": {
    "sizes": {
      "buckets": [
        {"key": "M", "doc_count": 450},
        {"key": "L", "doc_count": 380},
        {"key": "S", "doc_count": 290}
      ]
    },
    "colors": {
      "buckets": [
        {"key": "black", "doc_count": 320},
        {"key": "white", "doc_count": 250}
      ]
    }
  }
}
```

## Hierarchical Facets (Drill-Down)

```bash
# Category → Subcategory faceting
POST products/_search
{
  "query": {"match_all": {}},
  "aggs": {
    "categories": {
      "terms": {"field": "category.keyword", "size": 20},
      "aggs": {
        "subcategories": {
          "terms": {"field": "subcategory.keyword", "size": 10}
        }
      }
    }
  }
}

# Response shows category → subcategory hierarchy
# User clicks "Clothing" → API re-queries with filter
# Much faster than flat 5000-option list
```

## Caching Facet Results

```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=1000)
def get_facets(brand_filter, category_filter):
  """Cache facet results by filter combination"""
  cache_key = hashlib.md5(f"{brand_filter}:{category_filter}".encode()).hexdigest()
  
  # Check cache
  if cache_key in facet_cache:
    return facet_cache[cache_key]
  
  # Query Elasticsearch
  result = es.search(index='products', body={
    'size': 0,
    'query': {'bool': {'filter': [
      {'term': {'brand.keyword': brand_filter}},
      {'term': {'category.keyword': category_filter}}
    ]}},
    'aggs': {'sizes': {'terms': {'field': 'size.keyword'}}}
  })
  
  # Cache with TTL (5 minutes)
  facet_cache[cache_key] = result
  return result
```

## Production Issues & Fixes

**1. Aggregation on Text Fields Breaks**
```bash
# ❌ Wrong: text fields tokenized
"aggs": {"sizes": {"terms": {"field": "size"}}}
# Returns ['M', 'L', 'XL', 'x', 'l'] (lowercased tokens!)

# ✓ Correct: use .keyword (non-tokenized)
"aggs": {"sizes": {"terms": {"field": "size.keyword"}}}
# Returns ['M', 'L', 'XL'] (exact values)
```

**2. High Cardinality Aggregations**
- User IDs aggregation: 10M unique users → memory explosion
- **Fix:** Limit to top-N; use approximate cardinality (HyperLogLog)

```bash
"aggs": {
  "user_ids": {
    "terms": {
      "field": "user_id.keyword",
      "size": 100  # Limit to top 100 users
    }
  },
  "unique_users": {
    "cardinality": {
      "field": "user_id.keyword",
      "precision_threshold": 10000  # HyperLogLog approximation
    }
  }
}
```

**3. Nested Aggregations Performance**
- 3+ levels of nesting causes exponential growth
- **Fix:** Flatten hierarchies where possible; use separate queries for drill-down

## When to Use

✓ **E-commerce** (product filters with counts)
✓ **Analytics dashboards** (status distribution, date histogram)
✓ **Browse-and-refine UX** (facet counts update on filter)

✗ **Exact unique counts** (use cardinality agg; approximation ~5% error)
✗ **Real-time aggregations** (cache and invalidate on updates)

## Production Gotchas

**1. Stale Facet Counts**
- Cached facets lag behind new products by 5 minutes
- User filters to "Shoes: 0 results" but items exist
- **Fix:** Invalidate cache on product insert/update

**2. Aggregation Size Limits**
- Elasticsearch default: terms bucket size = 10
- Site shows only "Top 10 colors" but customer wants all 50
- **Fix:** Set explicit size; document limits in UI ("Top 10 colors")

**3. Range Aggregations Require Pre-Defined Buckets**
- Price ranges: $0-10, $10-50, $50-100, etc.
- **Fix:** Use auto_date_histogram for dates; explicit ranges for prices

---

**Bağlantılar:**
- [[hamle7-search-001-inverted-index]] (term collection for aggregations)
- [[hamle7-search-003-bm25-relevance]] (filtering before aggregation)
- [[hamle6-devops-001-structured-logging-json]] (caching metrics)
