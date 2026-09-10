---
type: decision
title: Caching Strategy Selection Matrix
category: Architecture & API Design
status: active
created: 2026-08-27
source: donnemartin/system-design-primer (Hamle 4)
tags: [architecture, caching, performance, redis, memcached, cdn]
---

# Caching Strategy Matrix

**Pattern:** Tier-Based Cache Selection

## Karar

Caching'de tek çözüm yok. Her tier için uygun tool seç:

| Cache Layer | Tool | Use Case | TTL | Eviction |
|-------------|------|----------|-----|----------|
| **Browser** | localStorage/sessionStorage | User preferences, auth tokens | 7 days | Manual clear |
| **CDN** | CloudFlare, Akamai | Static assets, HTML | 24h-30d | Origin purge |
| **App Memory** | In-process cache | Config, rarely-changing data | Minutes-hours | LRU |
| **Distributed** | Redis, Memcached | Session, hot data, leaderboards | Seconds-minutes | LRU/LFU |
| **Database** | Query caching | Expensive queries | Query-specific | Invalidation |

## Redis vs Memcached

**Redis seç:** Complex data (Streams, Sets), persistence gerekli, transactions
**Memcached seç:** Simple key-value, ultra-high throughput, failover tolerate

## Caching Invalidation Stratejileri

1. **TTL-based:** Simple, eventual consistency OK
2. **Event-based:** OrderCreated event → clear cart cache
3. **Write-through:** Update cache when writing DB
4. **Write-behind:** Batch cache updates async
5. **Manual:** Admin dashboard cache clear

## Anti-Pattern

```
❌ Cache everything
   → Memory explosion
   → Stale data problems
   → Cache coherency nightmare

✓ Cache strategically
   → Hot data only (user sessions, product catalog)
   → Unimportant data (profile photo, statistics)
   → Not: passwords, credit cards, real-time inventory
```

---

**Bağlantılar:** [[github-harvest-002-sharding]]
