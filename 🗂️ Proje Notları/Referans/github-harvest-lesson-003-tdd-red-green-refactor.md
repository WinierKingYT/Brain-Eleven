---
type: lesson
title: Test-Driven Development - Red/Green/Refactor Cycle
category: Testing & TDD
status: active
created: 2026-08-27
source: mehdihadeli/tdd-sample
tags: [testing, tdd, quality, design, red-green-refactor]
---

# Red/Green/Refactor TDD Cycle

## Prensip

Test yazma → fail → implement → pass → refactor → repeat

Kod tasarımı test requirements'den emerge eder.

## Üç Faz

**1. RED: Failing Test Yaz**
```typescript
test('should calculate order total with tax', () => {
  const order = new Order([
    { price: 100, quantity: 2 },
    { price: 50, quantity: 1 }
  ])
  
  expect(order.totalWithTax()).toBe(330) // 250 * 1.32
})

// → TEST FAILS (function doesn't exist)
```

**2. GREEN: Minimal Implementation**
```typescript
class Order {
  totalWithTax() {
    return 330; // Hardcoded to pass test!
  }
}

// → TEST PASSES (but obviously wrong)
```

**3. REFACTOR: Improve While Tests Pass**
```typescript
class Order {
  calculateSubtotal() {
    return this.items
      .reduce((sum, item) => sum + (item.price * item.quantity), 0);
  }
  
  totalWithTax() {
    return this.calculateSubtotal() * 1.32;
  }
}

// → TESTS STILL PASS, code improved
```

## Neden Başarılı?

1. **Design Emerges:** Testten başlayınca API doğal olur
2. **Coverage Guaranteed:** Test yaz önce → 100% coverage
3. **Confidence:** Refactor sırasında regresyon impossible
4. **Documentation:** Tests = living documentation
5. **30-50% Fewer Bugs:** Studies show fewer defects

## Anti-Pattern: Test After

```
❌ Code first → Write test for written code
   → Test passes (designed to pass)
   → Coverage false sense of security
   → Real bugs uncovered in production
```

## Uygulanabilirlik

TDD ideal durumlar:
- ✓ Complex business logic (order calculation)
- ✓ Critical code paths (payment processing)
- ✓ Refactoring legacy code (safety net)
- ✓ Learning new domain

TDD less ideal:
- ✗ UI code (too brittle)
- ✗ Prototyping (too slow initially)
- ✗ Infrastructure (hard to test)

---

**Bağlantılar:** [[github-harvest-006-testing-pyramid]], [[github-harvest-015-vertical-slice]]
