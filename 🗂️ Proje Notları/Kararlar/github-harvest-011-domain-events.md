---
type: decision
title: Domain Events - Cross-Boundary Communication
category: Clean Architecture & DDD
status: active
created: 2026-08-27
source: TuralSuleymani/the-real-DDD-CQRS
tags: [ddd, domain-events, event-sourcing, bounded-contexts, decoupling]
---

# Domain Events

**Pattern:** Bounded Contexts Decouple Through Events

## Karar

Aggregate state değiştiğinde, domain event'i raise et. Diğer bounded contexts bu event'leri subscribe edip, kendi state'lerini update eder.

## Event Flow

```
Order Aggregate           (Order Context)
  └─ OrderPlaced event
       ├─→ Payment context: Payment.create()
       ├─→ Inventory context: Inventory.reserve()
       └─→ Notification context: Email.send()
```

## Event vs Command

| Command | Event |
|---------|-------|
| Request (may fail) | Fact (happened) |
| Future tense | Past tense |
| "CreateOrder" | "OrderCreated" |
| Can be rejected | Can't be undone |

## Implementasyon Pattern

```java
// Domain event definition
public class OrderPlaced {
  OrderId orderId;
  CustomerId customerId;
  List<Item> items;
  Money total;
  Instant timestamp;
}

// Aggregate raises event
class Order {
  static Order place(CustomerId, items) {
    // Validation, calc total
    Order order = new Order(...)
    order.addDomainEvent(new OrderPlaced(...))
    return order;
  }
}

// Application service publishes
@Transactional
void placeOrder(PlaceOrderCmd cmd) {
  Order order = Order.place(...)
  repository.save(order)
  eventPublisher.publish(order.getDomainEvents())
}
```

## Avantajları

- ✅ Loose coupling between contexts
- ✅ Easy to add new subscribers (no changes to domain)
- ✅ Full audit trail (event = history)
- ✅ Event replay for recovery

## Eventual Consistency

Domain events sirasında → temporal gap açılabilir:
- OrderPlaced event fired
- Payment pending
- Customer checks: order status = pending (normal)
- 2 seconds later: payment complete

→ Acceptable tradeoff for loose coupling

---

**Bağlantılar:** [[github-harvest-008-cqrs-pattern]], [[github-harvest-012-saga-pattern]]
