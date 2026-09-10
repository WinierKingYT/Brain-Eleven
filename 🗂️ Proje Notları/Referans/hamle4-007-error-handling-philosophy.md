---
type: decision
title: Error Handling - Operational vs Programmer Errors
category: Code Quality & Testing
status: active
created: 2026-08-27
source: Raynos/error-handling-philosophy (Hamle 4)
tags: [error-handling, reliability, patterns, decisions]
---

# Error Handling Philosophy

**Pattern:** Distinguish Operational from Programmer Errors

## Two Error Types

### Operational Errors (Expected, Recoverable)
```
- Network timeout → retry with backoff
- File not found → use default
- Invalid input → return error response
- Database down → circuit breaker
- Rate limit → queue and retry

Handling: return Result<T, Err> or throw specific error
```

### Programmer Errors (Bugs, Unrecoverable)
```
- Null pointer dereference
- Array index out of bounds
- Type mismatch
- Logic bug
- Invalid state transition

Handling: let crash (developer fixes), don't retry
```

## Decision Matrix

| Scenario | Type | Handle | Example |
|----------|------|--------|---------|
| User inputs invalid data | Operational | Return error | 400 Bad Request |
| Network call fails | Operational | Retry/fallback | Circuit Breaker |
| Null reference | Programmer | Let crash | Fix code |
| DB constraint violation | Operational | Return error | 409 Conflict |
| Off-by-one bug | Programmer | Let crash | Fix code |

## Error Response Pattern

```javascript
// Return Result type
function processOrder(data) {
  if (!data.orderId) 
    return { error: "Missing orderId", status: 400 }
  
  try {
    const order = await db.getOrder(data.orderId)
    return { success: true, data: order }
  } catch (e) {
    if (e.isNetworkError)
      return { error: "Database unavailable", status: 503 }
    throw e  // Programmer error, crash
  }
}
```

## Anti-Patterns

- ❌ Catch everything (hides bugs)
- ❌ Retry programmer errors (infinite loop)
- ❌ Silent failures (hard to debug)
- ❌ Generic error messages (no context)

---

**Bağlantılar:** [[hamle4-006-clean-code-checklist]]
