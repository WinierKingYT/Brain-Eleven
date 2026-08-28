---
type: decision
title: Floating-Point Precision - Common Traps
category: Engineering Mindset & Foundations
status: active
created: 2026-08-27
source: mtdvio/every-programmer-should-know (Hamle 4)
tags: [floating-point, precision, mathematics, numerical-errors]
---

# Floating-Point Precision Issues

**Pattern:** Binary Representation Mismatches

## Classic Problems

**1. Equality Comparison**
```
❌ Direct comparison:
  if (0.1 + 0.2 == 0.3) // False!
     (0.1 + 0.2 = 0.30000000000000004)

✓ Epsilon comparison:
  const EPSILON = 1e-10
  if (abs(0.1 + 0.2 - 0.3) < EPSILON) // True!
```

**2. Accumulation Errors**
```
Sum calculation:
  sum = 0
  for i in 1 to 1000000:
    sum += 0.0001

Result: sum ≈ 99.99900400000151 (not 100!)

Why: Each addition introduces rounding error
```

**3. Currency/Money Calculations**
```
❌ Floating-point for money:
  $19.99 * 2 = $39.98000000000001 (wrong!)

✓ Use integers (cents):
  1999 * 2 = 3998 (100 cents = $39.98)
  
Or use Decimal library:
  from decimal import Decimal
  Decimal('19.99') * 2 = Decimal('39.98')
```

## IEEE 754 Standard

```
64-bit float:
- Sign: 1 bit
- Exponent: 11 bits
- Mantissa: 52 bits (precision)

Precision: ~15-17 significant digits

Examples:
  0.1 cannot represent exactly (binary fraction)
  1.0 can represent exactly
  1e16 and 1e16 + 1 are equal (precision lost)
```

## Best Practices

```
✓ Use Decimal for financial calculations
✓ Use integers when possible (multiply by 100)
✓ Round explicitly before display
✓ Test equality with epsilon
✓ Be aware of accumulation errors

Example:
  // Calculate total price
  unit_price = Decimal('19.99')
  quantity = 3
  tax_rate = Decimal('0.08')
  
  subtotal = unit_price * quantity
  tax = subtotal * tax_rate
  total = subtotal + tax
```

---

**Bağlantılar:** 
- [[hamle4-023-utf8-encoding-pitfalls]] (other foundational issues)
- [[hamle6-testing-001-test-pyramid]] (numeric edge case testing)
- [[hamle5-database-004-connection-tuning]] (numeric precision in queries)
- [[hamle5-performance-004-benchmarking-methodology]] (accurate benchmarking)
