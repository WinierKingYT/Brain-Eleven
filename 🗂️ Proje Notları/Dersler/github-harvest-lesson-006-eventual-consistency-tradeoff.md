---
type: lesson
title: Eventual Consistency - Loose Coupling Tradeoff
category: System Design & Architecture
status: active
created: 2026-08-27
source: donnemartin/system-design-primer
tags: [system-design, consistency, eventual-consistency, tradeoff, microservices]
---

# Eventual Consistency

## Prensip

Distributed systems'de strong consistency (ACID) vs loose coupling arasında seç. Eventual consistency = loose coupling.

## Consistency Spektrumu

**Strong Consistency (ACID)**
```
Write → Immediate read sees update
✓ Simple programming model
✗ Slow (must coordinate)
✗ Vulnerable to failures

Example: Banking (transfer)
  Account A -$100 → DB
  Account B +$100 → DB
  → Immediately visible to all
```

**Eventual Consistency**
```
Write → May take time to propagate
✓ Fast (no coordination)
✓ Resilient (can fail independently)
✗ Temporary inconsistency

Example: Social media (like counter)
  Like → Cached locally
  → Propagates to followers (seconds)
  → OK if short-term inconsistent
```

## Real-World Gap

```
Order Service         Payment Service
  ├─ Order created
  ├─ OrderPlaced event sent
  │
  └─ [network lag: 100ms]
     
       └─ Payment processing
       └─ Email sending
       └─ Inventory reserved

User checks: "Is my order paid?"
  ↓ Sees: "Pending" (not yet consistent)
  ↓ Few seconds later: "Paid" (now consistent)
```

**This is acceptable!** vs **ACID mode would:**
- Lock everything
- Wait for consistency
- User gets response in 1-2 seconds
- But scales to millions harder

## When to Use Each

**Strong Consistency (CP):**
- ✓ Financial transactions (account transfers)
- ✓ Inventory stock (oversell prevention)
- ✓ Authorization (security critical)

**Eventual Consistency (AP):**
- ✓ Like counts (socials don't mind 5s lag)
- ✓ Order status (user checks manually)
- ✓ Read-heavy analytics
- ✓ Distributed cache

## Implementation Pattern

```
Write model (ACID):
  Account.transfer() → consistent immediately

Read model (eventual):
  Get cached balance
  Background sync updates cache
  
User sees:
  Real account balance: correct
  Cached display: may be 5s old
  → Acceptable tradeoff
```

## Monitoring Eventual Consistency

Watch for:
- Event delivery latency (ideally <100ms)
- Replication lag (should be <1s)
- Inconsistency window (acceptable?)
- Failure recovery time (propagate after fix?)

---

**Bağlantılar:** [[github-harvest-001-cap-theorem]], [[github-harvest-008-cqrs-pattern]]
