---
type: reference
title: System Design Patterns Hub
category: Navigation Index
status: active
created: 2026-08-28
tags: [index, system-design, distributed-systems, event-sourcing, cqrs, saga]
---

# System Design Patterns Index

Navigation to advanced distributed systems patterns: event sourcing, CQRS, saga, outbox, bulkhead.

## By Topic

### Event-Driven Architecture
- **Event Sourcing**: [[hamle6-system-001-event-sourcing]] (immutable event log, replay)
- **CQRS**: [[hamle6-system-002-cqrs]] (command/query separation)

### Distributed Transactions
- **Saga Pattern**: [[hamle6-system-003-saga-pattern]] (distributed transactions, compensation)
- **Outbox Pattern**: [[hamle6-system-004-outbox-pattern]] (dual-write solution, exactly-once)

### Resilience & Failures
- **Circuit Breaker**: [[github-harvest-003-circuit-breaker]] (handle service failures)
- **Bulkhead**: [[hamle5-cloud-002-kubernetes-hpa]] (fault isolation)

### Foundational Concepts
- **CAP Theorem**: [[github-harvest-001-cap-theorem]] (consistency vs availability tradeoff)
- **Sharding**: [[github-harvest-002-sharding]] (data distribution)

## By Hamle

| Hamle | Focus |
|-------|-------|
| **Hamle 3** | Foundations: CAP theorem, sharding, circuit breaker |
| **Hamle 6** | Deep patterns: event sourcing, CQRS, saga, outbox |

## Cross-Domain Connections

- **System Design ← Backend**: [[hamle5-backend-001-event-loop-optimization]] (async task handling)
- **System Design ← Testing**: [[hamle6-testing-001-test-pyramid]] (distributed system testing)
- **System Design ← DevOps**: [[hamle6-devops-001-structured-logging-json]] (tracing across services)
- **System Design ← Database**: [[hamle5-database-003-transaction-isolation]] (isolation levels matter)

## Quick Start: Choosing a Pattern

**Building event-driven system?**
1. Start: [[hamle6-system-001-event-sourcing]] (immutable log)
2. Queries: [[hamle6-system-002-cqrs]] (read models)
3. Consistency: [[hamle6-system-003-saga-pattern]] (distributed transactions)

**Handling failures in distributed system?**
1. Learn: [[github-harvest-003-circuit-breaker]] (pattern basics)
2. Apply: [[hamle5-cloud-002-kubernetes-hpa]] (scale on failure)
3. Observe: [[hamle6-devops-001-structured-logging-json]] (trace across services)

**Solving dual-write problem?**
1. Pattern: [[hamle6-system-004-outbox-pattern]] (transactional outbox)
2. Guarantee: Exactly-once delivery
3. Coordinate: With [[hamle6-system-001-event-sourcing]] (event log)

---

**Last updated:** 2026-08-28
**Total patterns:** 8+ across Hamle 3-6
