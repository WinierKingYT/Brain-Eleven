---
type: decision
title: Systems Thinking - Emergent Behavior and Feedback Loops
category: Engineering Mindset
status: active
created: 2026-08-27
source: lucasviola/awesome-mental-models (Hamle 4)
tags: [systems-thinking, architecture, feedback, emergence, complexity]
---

# Systems Thinking for Architecture

**Pattern:** Understanding Complexity and Interconnection

## Components vs System

```
Component: Database performs well in isolation
System: When request volume doubles, cascading failures occur

Why: Feedback loops not visible at component level
```

## Feedback Loops

**Positive Feedback (Amplifying)**
```
1 slow request
  ↓
2 retries queued
  ↓
3 more requests (backlog)
  ↓
4 system gets slower
  ↓
5 more retries
  └─→ Spiral of doom (overload)

Solution: Circuit breaker breaks the loop
```

**Negative Feedback (Stabilizing)**
```
Inventory runs low
  ↓
Auto-reorder triggers
  ↓
Inventory replenished
  ↓
System stabilizes

Self-healing system (desired)
```

## Emergence

```
Individual component: Thread pools, load balancer, cache
Emergent property: System becomes "flaky under load"

Can't predict emergent behavior by analyzing components!
Solution: Load testing reveals emergence
```

## Architecture Resilience Patterns

```
Single Responsibility:
  Each component has one reason to change
  → Reduces complexity
  → Eases troubleshooting

Decoupling:
  Event-driven, async messaging
  → Breaks problematic feedback loops
  → Allows independent scaling

Observability:
  Metrics, logs, traces
  → Understand system behavior at scale
  → Detect feedback loops early
```

## Example: Cascading Failure

```
System architecture:
  Frontend → API (10 threads) → DB (50 connections)

Load: 100 requests/sec
  
Emergence:
- API threads exhaust (wait for DB)
- Frontend retries (adds more load)
- DB connections pool empty (no new queries)
- Entire system collapses

Solution: Circuit breaker + graceful degradation
  → System degrades smoothly instead of catastrophic failure
```

---

**Bağlantılar:** [[hamle4-016-mental-models-for-architecture]], [[hamle4-003-circuit-breaker]]
