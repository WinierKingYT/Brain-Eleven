---
type: decision
title: Clean Code Checklist - Readability First
category: Code Quality & Testing
status: active
created: 2026-08-27
source: ryanmcdermott/clean-code-javascript (Hamle 4)
tags: [code-quality, clean-code, readability, refactoring]
---

# Clean Code Checklist

**Pattern:** Single Responsibility + Naming Excellence

## Function Checklist

```
Before shipping:

□ Name describes WHAT it does (calculateOrderTotal, not calcOT)
□ One responsibility only (not validateAndSaveAndEmail)
□ <= 20 lines (preferably <= 10)
□ <= 3 parameters (use object for > 3)
□ No side effects (pure functions preferred)
□ No magic numbers (use named constants)
□ Error handling explicit (throw or return Result)

❌ Bad:
function p(u) {
  // 50 lines of logic
  // query DB, send email, update cache
}

✓ Good:
function calculateOrderTotal(order) {
  return order.items.reduce(
    (sum, item) => sum + (item.price * item.qty),
    0
  );
}
```

## Variable Naming

| Bad | Good | Why |
|-----|------|-----|
| `d` | `daysSinceLast` | Context clear |
| `getValue()` | `getOrderTotal()` | Specific |
| `isValid` | `isOrderValid` | Scope clear |
| `x` | `userBalance` | No abbreviations |

## Class Size Limits

- File: < 800 lines (extract modules)
- Class: < 200 lines (too many responsibilities)
- Method: < 50 lines (split logic)
- Nesting: < 4 levels (use early return)

## Anti-Patterns

```
❌ God Objects (100+ fields)
❌ Long Parameter Lists (>3)
❌ Magic Numbers (hardcoded 86400)
❌ Nested Conditionals (>3 levels)
❌ Comments explaining code (fix the code!)
```

---

**Bağlantılar:** [[hamle4-007-error-handling-philosophy]]
