---
type: reference
title: Hamle 7 Summary - 20 Ultra-Specialized Patterns
category: Architecture Decision Record Summary
status: active
created: 2026-08-28
tags: [hamle7, summary, architecture, patterns, cross-domain]
---

# Hamle 7: Ultra-Specialization in 5 New Domains

**Objective:** Extract 10-15 deep production patterns from 5 entirely new specialization domains.

**Result:** 20 ultra-specialized decision notes across 5 domains (4 patterns each).

---

## 📊 Patterns by Domain

### 🗄️ Data Engineering (4 patterns)

1. **[[hamle7-data-001-idempotent-etl-partition-replacement]]**
   - Pattern: Atomic DELETE+INSERT for time-windowed data
   - Use: Batch ETL, analytical warehouses, backfill recovery
   - Key insight: Partition replacement guarantees exactly-once without dedup overhead

2. **[[hamle7-data-002-schema-evolution-medallion]]**
   - Pattern: Three-layer governance (Bronze permissive → Silver moderate → Gold strict)
   - Use: Multi-source data lakes, evolving APIs, schema changes
   - Key insight: Progressive strictness prevents cascading failures

3. **[[hamle7-data-003-slowly-changing-dimensions-type2]]**
   - Pattern: Effective/expiry dates track complete change history
   - Use: Dimensional modeling, audit trails, temporal analysis (GDPR/SOX)
   - Key insight: Current + historical access via `WHERE is_current = true` flag

4. **[[hamle7-data-004-dead-letter-queue-dlq]]**
   - Pattern: Route failures to separate queue with full context
   - Use: High-volume pipelines, graceful degradation, CDC replication
   - Key insight: DLQ enables replay without stopping main pipeline

### 📬 Messaging & Events (4 patterns)

5. **[[hamle7-messaging-001-exactly-once-semantics]]**
   - Pattern: Kafka transactions vs RabbitMQ application-level dedup
   - Use: Financial transactions, inventory (exactly-once); analytics (at-least-once)
   - Key insight: Exactly-once costs 2-3x latency; use judiciously

6. **[[hamle7-messaging-002-consumer-group-rebalancing]]**
   - Pattern: Sticky assignment minimizes partition movement
   - Use: Dynamic scaling, hot partitions, production Kafka
   - Key insight: Rebalancing causes 30-90s pause; tune timeouts to prevent false failures

7. **[[hamle7-messaging-003-partitioning-ordering]]**
   - Pattern: Partition by entity ID (user, order) for per-entity ordering
   - Use: E-commerce, event sourcing, stateful processing
   - Key insight: Composite keys prevent hotspots; can't reduce partitions after creation

8. **[[hamle7-messaging-004-prefetch-backpressure]]**
   - Pattern: QoS prefetch limits prevent consumer overload
   - Use: All production systems; memory-constrained environments
   - Key insight: Find sweet spot: prefetch=100 typical; too low = underutilization, too high = hides slow consumers

### 🔍 Search & Indexing (4 patterns)

9. **[[hamle7-search-001-inverted-index]]**
   - Pattern: Map terms to posting lists (doc IDs) for sub-millisecond lookup
   - Use: Full-text search, every search system >100K docs
   - Key insight: Delta encoding saves 40% space; WAND skips non-competitive docs

10. **[[hamle7-search-002-vector-search-embeddings]]**
    - Pattern: Dense embeddings + HNSW index for semantic search
    - Use: Intent matching, cross-lingual, e-commerce recommendations
    - Key insight: Hybrid search (BM25 + vector) outperforms either alone

11. **[[hamle7-search-003-bm25-relevance]]**
    - Pattern: Probabilistic ranking with TF saturation + length normalization
    - Use: Default for full-text; tune k1/b per domain
    - Key insight: Global IDF (not per-shard) prevents inconsistent scores

12. **[[hamle7-search-004-faceting-aggregation]]**
    - Pattern: Fast facet counts via aggregations with sub-filters
    - Use: E-commerce filters, drill-down browsing, analytics dashboards
    - Key insight: Use .keyword suffix; limit cardinality; cache facets with TTL

### 📱 Mobile Development (4 patterns)

13. **[[hamle7-mobile-001-mvvm-viewmodel]]**
    - Pattern: ViewModels survive rotation; Observable bindings auto-update
    - Use: Screen with business logic, configuration changes
    - Key insight: Never hold UI references in ViewModel (memory leak)

14. **[[hamle7-mobile-002-offline-first-sync]]**
    - Pattern: Local-first storage + sync queue + conflict resolution
    - Use: Unreliable networks, collaborative features, offline-critical
    - Key insight: Soft deletes safer than hard; merge independent fields; user-decides on true conflicts

15. **[[hamle7-mobile-003-image-caching]]**
    - Pattern: Memory LRU cache + disk cache two-tier architecture
    - Use: Any image-heavy app (feeds, galleries); memory-constrained devices
    - Key insight: NSCache auto-evicts on pressure; clean disk cache by TTL

16. **[[hamle7-mobile-004-deep-linking]]**
    - Pattern: Deep links + deferred (pre-install) link handling
    - Use: Marketing campaigns, referral programs, app integrations
    - Key insight: Validate deep links; handle deferred links after setup; avoid back stack corruption

### 🤖 Machine Learning & LLMs (4 patterns)

17. **[[hamle7-ml-001-back-translation-augmentation]]**
    - Pattern: Translate EN → FR → EN for natural paraphrases
    - Use: Limited labeled data, multilingual models, robustness
    - Key insight: Validate similarity threshold (>0.7 typical); domain-specific terms may break

18. **[[hamle7-ml-002-smote-imbalanced-classification]]**
    - Pattern: Synthetically oversample minority via k-NN interpolation
    - Use: Fraud detection, disease diagnosis, rare events (>1:10 imbalance)
    - Key insight: Apply SMOTE AFTER train-test split (no data leakage); combine with regularization

19. **[[hamle7-ml-003-stratified-kfold-validation]]**
    - Pattern: K-fold preserving class distribution per fold
    - Use: Imbalanced classification, stable evaluation, <10k samples
    - Key insight: Use F1/PR-AUC (not accuracy) for imbalanced; use stratification by default

20. **[[hamle7-ml-004-early-stopping]]**
    - Pattern: Monitor validation metric; stop when no improvement
    - Use: Deep learning, prevent overfitting, production models
    - Key insight: `restore_best_weights=True`; monitor metric you care about (not just loss)

---

## 🔗 Cross-Domain Connections

| Connection | Patterns | Why |
|-----------|----------|-----|
| **Data Eng ↔ Messaging** | Schema evolution + consumer rebalancing | Schema changes trigger DLQ routing |
| **Search ↔ Mobile** | Vector embeddings + offline-first | Cached embeddings enable offline semantic search |
| **ML ↔ Data Eng** | SMOTE augmentation + partition replacement | Synthetic data stored via idempotent ETL |
| **Messaging ↔ ML** | Exactly-once delivery + early stopping | Training correctness requires perfect event ordering |
| **All Domains** | DLQ pattern + early stopping | Both handle failures gracefully via monitoring |

---

## 📈 Coverage Summary

```
Data Engineering:    4/5 ✓  (ETL, schemas, dimensions, errors)
Messaging & Events:  4/5 ✓  (semantics, coordination, partitioning, backpressure)
Search & Indexing:   4/5 ✓  (indexing, vectors, scoring, faceting)
Mobile Development:  4/5 ✓  (architecture, sync, caching, navigation)
Machine Learning:    4/5 ✓  (augmentation, imbalance, validation, training)

Total Patterns:      20
Total Notes:         20
Deployment:          Production-ready with gotchas documented
```

---

**Last updated:** 2026-08-28
**Hamle 7 Status:** Complete ✅
**Next:** Update navigation hubs; prepare Hamle 8 (if needed)

---

**Related Summaries:**
- [[hamle6-summary]] (Hamle 6: 9 ultra-specialized notes)
- [[INDEX-Security-Cryptography]] (Security domain hub)
- [[INDEX-API-Design]] (API domain hub)
- [[INDEX-Testing-Quality]] (Testing domain hub)
- [[INDEX-System-Design]] (System design domain hub)
