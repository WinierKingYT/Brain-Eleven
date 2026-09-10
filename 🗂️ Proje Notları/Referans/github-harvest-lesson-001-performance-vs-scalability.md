---
type: lesson
title: Performance vs Scalability - Foundational Distinction
category: System Design & Architecture
status: active
created: 2026-08-27
source: donnemartin/system-design-primer
tags: [system-design, performance, scalability, metrics, optimization]
---

# Performance vs Scalability

## Prensip

**Performance Problem:** Sistem bir user için yavaş  
**Scalability Problem:** Sistem çok user altında slow hale gelir

## Örnek Senaryo

**Same Application:**

Performance issue:
- 1 user: Response 5 seconds (CPU intensive)
- Optimization: Query optimize → 500ms (OK)
- 10 users: Hala 500ms each (good)

Scalability issue:
- 1 user: Response 100ms (fast!)
- 10 users: Response 100ms (good!)
- 1000 users: Response 2 seconds (BAD)
- Optimization: Caching, load balancer → scales

## Diagnosis Fark

| Problem | Symptom | Fix |
|---------|---------|-----|
| Performance | Single user slow | Optimize code, query, algorithm |
| Scalability | Many users slow | Add servers, caching, sharding |

## Optimization Stratejileri

**Performance (Single User):**
- Algorithm optimization (O(n) → O(log n))
- Database query tuning (indexes)
- Code profiling (hot spots)
- Memory management

**Scalability (Multiple Users):**
- Load balancing (horizontal scale)
- Caching layers (Redis)
- Database partitioning (sharding)
- Async processing (queues)

## Kombinasyon

Optimal sistem: Performance + Scalability

```
❌ High perf, low scalability
   1 user: 10ms ✓
   1000 users: 10 seconds ✗

❌ Low perf, high scalability
   1 user: 5 seconds ✗
   1000 users: 5 seconds ✓

✓ High perf + high scalability
   1 user: 10ms ✓
   1000 users: 50ms ✓
```

---

**Bağlantılar:** [[github-harvest-001-cap-theorem]], [[github-harvest-002-sharding]]
