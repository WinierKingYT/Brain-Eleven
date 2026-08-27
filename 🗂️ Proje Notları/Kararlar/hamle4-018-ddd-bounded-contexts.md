---
type: decision
title: DDD - Bounded Context Boundaries
category: Architecture & API Design
status: active
created: 2026-08-27
source: kgrzybek/modular-monolith-with-ddd (Hamle 4)
tags: [ddd, bounded-contexts, architecture, domains]
---

# Bounded Context Design

**Pattern:** Domain Partitioning for Modularity

## What is a Bounded Context?

```
Business domain split by ubiquitous language

E-commerce system:
- Order Context: Order, OrderItem, OrderStatus
- Payment Context: Payment, Invoice, Refund (different meanings!)
- Inventory Context: Stock, Reservation, SKU

Same entity different meaning:
- Order context: "Product" = what's in order
- Inventory context: "Product" = stock level, reorder point
```

## Context Boundaries

**Order Context:**
```
Entities: Order (root), OrderItem, Shipment
Values: Money, OrderStatus (pending, shipped, delivered)
Events: OrderCreated, OrderShipped, OrderCancelled

Responsibility: Order lifecycle management
```

**Payment Context:**
```
Entities: Payment (root), Transaction, Refund
Values: Amount, PaymentMethod, PaymentStatus

Responsibility: Payment processing and reconciliation
```

## Anti-Pattern: Shared Model

```
❌ Global Product entity used everywhere
   Order sees: price, SKU
   Inventory sees: stock, warehouse
   Pricing sees: cost, margin

Result: "Product" has 20 fields, unclear meaning
```

## Correct: Context-Specific Models

```
✓ Each context models what it needs

Order Context:
  class Product { SKU, productId, name, price }

Inventory Context:
  class Product { productId, stock, reorderPoint, location }

Communication: Events
  ProductStockChanged event → Order subscribes to update availability
```

## Context Mapping (Communication Patterns)

| Pattern | Direction | Use |
|---------|-----------|-----|
| Partnership | Bidirectional | Teams coordinate |
| Customer/Supplier | Upstream→Downstream | Dependency |
| Conformist | Downstream accepts | Legacy system |
| Anti-corruption | Adapter | Isolate legacy |

---

**Bağlantılar:** [[github-harvest-007-aggregate-root]], [[hamle4-014-design-document-template]]
