---
type: decision
title: Saga Pattern - Distributed Transactions
category: Design Patterns & Microservices
status: active
created: 2026-08-27
source: mehdihadeli/awesome-software-architecture
tags: [design-patterns, saga, microservices, transactions, compensation]
---

# Saga Pattern

**Pattern:** Managing Distributed Transactions Without ACID

## Karar

Microservices dünyasında distributed transaction koordine et, herbir servis local transaction yap ve başarısız olursa compensate et.

## İki Varyant

**1. Choreography (Event-Driven)**
```
OrderService
  ├─ creates Order
  ├─ publishes OrderCreated
  │   ├─ PaymentService listens
  │   │   └─ processes payment
  │   │   └─ publishes PaymentProcessed
  │   │
  │   └─ InventoryService listens
  │       └─ reserves items
  │       └─ publishes InventoryReserved
```
- ✓ Decoupled
- ✗ Hard to track flow

**2. Orchestration (Central Coordinator)**
```
OrderSaga (Orchestrator)
  1. Command PaymentService.pay()
  2. If OK → Command InventoryService.reserve()
  3. If OK → Command ShippingService.schedule()
  4. If any fail → Compensate all previous
```
- ✓ Clear flow
- ✗ Central bottleneck

## Compensation Logic

```
// Success path
order.place() → payment.charge() → inventory.reserve()

// Failure at inventory.reserve()
// Compensate backwards:
inventory.release() ← [no-op]
payment.refund() ← [reverse charge]
order.cancel() ← [mark cancelled]
```

## Zorluklar

1. **Idempotency:** Multiple calls same result
   - Every step must be idempotent
   - Use idempotency key

2. **Compensation Logic:** Reverse operations not always possible
   - Refund OK
   - Delete not OK (audit trail)
   - → Soft delete / status change

3. **Timeout Handling:** What if PaymentService down?
   - Retry with exponential backoff
   - Circuit breaker
   - Manual intervention (alerts)

---

**Bağlantılar:** [[github-harvest-003-circuit-breaker]], [[github-harvest-013-bulkhead-pattern]]
