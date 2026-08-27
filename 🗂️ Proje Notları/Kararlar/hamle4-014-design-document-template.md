---
type: decision
title: Design Document (RFC) Template
category: Engineering Mindset
status: active
created: 2026-08-27
source: jordan-cutler/path-to-senior-engineer-handbook (Hamle 4)
tags: [design, documentation, architecture, decision-making]
---

# Design Document Template

**Pattern:** Structured Technical Decision Making

## Sections

### 1. PROBLEM STATEMENT
```
What are we solving? Why now?

Example:
- Order processing takes 30 seconds
- Customers see stale inventory
- Team doesn't agree on solution
```

### 2. PROPOSED SOLUTION
```
High-level overview before details

Example:
"Move order processing to async queue with Redis"
```

### 3. ARCHITECTURE DIAGRAM
```
OrderService
  ├─ POST /orders → Queue job
  ├─ OrderProcessor (worker) ← reads queue
  └─ Webhook (client gets update)
```

### 4. DETAILED DESIGN
```
- Component interactions
- Data flow (input → processing → output)
- Error scenarios
- Edge cases
```

### 5. ALTERNATIVES CONSIDERED
```
Option A: Synchronous (rejected - slow)
Option B: Async queue + Redis (chosen - fast)
Option C: Message broker + Kafka (overkill initially)

Tradeoffs: Complexity vs benefit
```

### 6. TESTING STRATEGY
```
- Unit: Queue serialization
- Integration: End-to-end order flow
- Load: 10k orders/hour
- Failure: Lost message recovery
```

### 7. ROLLOUT PLAN
```
Week 1: Shadow mode (new code, old path active)
Week 2: Canary (5% traffic)
Week 3: 50% traffic
Week 4: 100% traffic
```

### 8. RISKS & MITIGATION
```
Risk: Message loss
→ Mitigation: Persist to DB, Kafka backup

Risk: Performance regression
→ Mitigation: p99 latency monitoring, alert at 500ms
```

### 9. SUCCESS METRICS
```
- Order processing: 5s (from 30s)
- Inventory freshness: <1s (from 5s)
- Team velocity: +20% (less blocking)
```

---

**Bağlantılar:** [[hamle4-013-technical-debt-matrix]]
