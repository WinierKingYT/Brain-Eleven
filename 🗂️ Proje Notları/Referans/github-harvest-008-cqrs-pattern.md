---
type: decision
title: CQRS - Command Query Responsibility Segregation
category: Design Patterns & Architecture
status: active
created: 2026-08-27
source: TuralSuleymani/the-real-DDD-CQRS
tags: [design-patterns, cqrs, command, query, event-sourcing, optimization]
---

# CQRS Pattern

**Pattern:** Separate Read and Write Models

## Karar

Command (writes) ve Query (reads) responsibilities'ini ayırarak, bağımsız şekilde optimize et.

## Konsept

```
Domain Model (Commands)          Read Model (Queries)
  Order.place()                    Select from Order_Materialized
  Order.cancel()                   → Pre-computed, denormalized
  ↓                                
Event Store (Event Log)
  OrderPlaced event
  OrderCancelled event
  ↓
Projection Engine
  → Updates Read Model
```

## Avantajları

1. **Independent Scaling**
   - Read: Elasticsearch, Redis cache
   - Write: Domain logic, consistency

2. **Different Data Shapes**
   - Write: Normalized (ACID)
   - Read: Denormalized (fast queries)

3. **Event Sourcing Integration**
   - Full audit trail
   - Temporal queries
   - Event replay

## Dezavantajları

- ✗ Eventual consistency (gap açılabilir)
- ✗ Complexity (2x models maintain)
- ✗ Testing harder (dual models)

## Implementation Approach

**Simple CQRS (without Event Sourcing):**
```
Commands → Domain → Update DB
                  → Publish Event
                  ↓
           Read Model Updater
             → Denormalized table
```

**Event Sourcing CQRS:**
```
Commands → Domain → Write Event
            ↓
          Event Store (append-only)
            ↓
          Projection Engine
            → Read Model
```

## Kullanım Durumları

- ✅ Read-heavy systems (analytics)
- ✅ Complex write logic (orders, payments)
- ✅ Audit trail required
- ❌ Simple CRUD apps (overkill)

---

**Bağlantılar:** [[github-harvest-009-event-sourcing]], [[github-harvest-010-saga-pattern]]
