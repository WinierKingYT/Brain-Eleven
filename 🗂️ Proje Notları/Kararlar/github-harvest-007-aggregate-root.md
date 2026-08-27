---
type: decision
title: Aggregate Root Pattern - Consistency Boundary
category: Clean Architecture & DDD
status: active
created: 2026-08-27
source: TuralSuleymani/the-real-DDD-CQRS
tags: [ddd, clean-architecture, aggregate, consistency, domain-driven]
---

# Aggregate Root Pattern

**Pattern:** Transactional Consistency Boundary

## Karar

Complex domain logic içinde, grup ilişkili entities'i **Aggregate** olarak ele al ve tek bir **Aggregate Root** entity'nin kontrolü altında tut. Root dışındaki entity'lere direkt erişim yapılmaz.

## Örnek: Basket Aggregate

```
Basket (Aggregate Root)
  ├── items: BasketItem[]
  ├── coupon: Coupon (Value Object)
  └── seller: Seller (reference)

Basket.addItem(product, quantity)
  → Tüm business rules check
  → Inventory validate
  → Price calculate
  → Consistency ensure
```

## Neden Aggregate?

1. **Consistency:** Root hep invariants'ı enforce eder
2. **Boundaries:** Diğer aggregates bağımsız kalır
3. **Transaction:** Her operation atomic
4. **Testing:** Isolated, testable

## Anti-Pattern: Gods Aggregate

```
❌ Huge Aggregate
User.create() → creates Order → creates Invoice → ...
→ Transaction çok büyük
→ Memory pressure
→ Deadlock riski
```

## Doğru Yaklaşım

```
✓ Small, focused Aggregates
Order (Root)
  ├── OrderItem[]
  └── OrderStatus

Invoice (kendi Root'u)
  → OrderCreated event'i dinler
  → Invoice.create()
```

## Aggregate Size Kuralı

- < 10 entities per aggregate
- < 20 properties per entity
- Single use case complete
- Independent persistence possible

---

**Bağlantılar:** [[github-harvest-009-value-objects]], [[github-harvest-010-domain-events]]
