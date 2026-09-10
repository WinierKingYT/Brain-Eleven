---
type: decision
title: Vertical Slice Architecture
category: Clean Architecture & DDD
status: active
created: 2026-08-27
source: mehdihadeli/tdd-sample
tags: [clean-architecture, vertical-slices, feature-driven, modular]
---

# Vertical Slice Architecture

**Pattern:** Feature-Centric Organization vs Layer-Centric

## Karar

Code'u teknik layers'a (Controllers, Services, Models) değil, feature'lere (CreateOrder, GetOrders, CancelOrder) göre organize et.

## Comparison

**Traditional Layered**
```
controllers/
  ├─ OrderController.ts
  ├─ UserController.ts
  └─ PaymentController.ts
services/
  ├─ OrderService.ts
  ├─ UserService.ts
  └─ PaymentService.ts
models/
  ├─ Order.ts
  ├─ User.ts
  └─ Payment.ts
```
- ✗ Find all code for "CreateOrder" feature → 3 folders
- ✗ Feature-level testing hard
- ✗ Team changes cause merge conflicts

**Vertical Slice**
```
features/
  ├─ CreateOrder/
  │   ├─ CreateOrderCommand.ts
  │   ├─ CreateOrderHandler.ts
  │   ├─ CreateOrderValidator.ts
  │   └─ CreateOrder.test.ts
  ├─ GetOrders/
  │   ├─ GetOrdersQuery.ts
  │   ├─ GetOrdersHandler.ts
  │   └─ GetOrders.test.ts
  └─ CancelOrder/
```
- ✓ All "CreateOrder" code in one folder
- ✓ Easy feature-level testing
- ✓ Team owns slice → no merge conflicts

## Implementation Pattern

**Each Slice Contains**
1. **Handler** - Business logic
2. **Request/Command/Query** - Input
3. **Response** - Output
4. **Validator** - Validation
5. **Tests** - Feature tests

## Test Organization

```
CreateOrder.test.ts
  ├─ Unit: CreateOrderHandler validates input
  ├─ Integration: CreateOrderHandler saves to DB
  └─ E2E: POST /orders returns 201
```

## Avantajları

- ✅ Feature discovery (all code together)
- ✅ Parallel development (team per slice)
- ✅ Easy refactoring (scope limited)
- ✅ Feature branch clear
- ✅ Scalable teams

## Şirket Örneği

**Traditional:** Feature needs 3 team members (Controllers owner, Services owner, Models owner)

**Vertical:** Feature needs 1 team → full ownership

---

**Bağlantılar:** [[github-harvest-006-testing-pyramid]], [[github-harvest-014-hexagonal-architecture]]
