---
type: lesson
title: Domain-Driven Design - Ubiquitous Language
category: Clean Architecture & DDD
status: active
created: 2026-08-27
source: TuralSuleymani/the-real-DDD-CQRS
tags: [ddd, domain-driven, ubiquitous-language, communication, business]
---

# Ubiquitous Language

## Prensip

Domain eksperleri ve developers aynı dili konuşmalı. Business terminology direkt code'a yansısın.

## Problem: Language Gap

```
❌ Misalignment
Business: "Customer places an order"
Code: "User.createPurchaseTransaction()"

vs

✓ Alignment
Business: "Customer places an order"
Code: class Order { place(); }
```

## Örnek: E-Commerce Domain

**Ubiquitous Language:**
- Order (business concept)
- OrderItem (order içinde product)
- Coupon (discount)
- Seller (payment receiver)
- Quantity, Amount (value objects)

**Code (aligns with language):**
```java
class Order {
  List<OrderItem> items;
  Coupon appliedCoupon;
  Seller seller;
  
  void addItem(Product product, Quantity qty) { }
  void applyCoupon(Coupon c) { }
  Money totalWithTax() { }
}

class OrderItem {
  Product product;
  Quantity quantity;
  Amount price;
}
```

**Anti-pattern (generic names):**
```java
class Purchase {  // ← Not in business language
  List<Item> lst;  // ← Generic
  Discount d;      // ← Abbreviated
  
  void add(Product p, int q) { }  // ← Generic naming
}
```

## Communication Impact

**Ubiquitous Language Sağladığında:**
- ✓ Business analyst → Code readable
- ✓ Developer → Understands domain intent
- ✓ PR reviews → Domain-centric feedback
- ✓ Bugs → Domain-level root cause

**Language Gap Olduğunda:**
- ✗ Misunderstandings frequent
- ✗ Code doesn't reflect intent
- ✗ Expensive refactoring
- ✗ High turnover (new devs lost)

## Establishing Language

1. **Workshop:** Gather domain experts, developers
2. **Glossary:** Document all terms
3. **Bounded Context:** Each domain has own terminology
4. **Code Review:** Enforce language consistency
5. **Evolve:** Language changes as understanding deepens

---

**Bağlantılar:** [[github-harvest-007-aggregate-root]], [[github-harvest-008-cqrs-pattern]]
