---
type: decision
title: Testing Patterns - Test Isolation and Independence
category: Code Quality & Testing
status: active
created: 2026-08-27
source: goldbergyoni/javascript-testing-best-practices (Hamle 4)
tags: [testing, isolation, quality, patterns]
---

# Testing Best Practices

**Pattern:** Isolated, Independent, Reproducible Tests

## Test Independence Rules

```
❌ Coupled Tests (anti-pattern):
  test 1: Create user → User ID = 1
  test 2: Assume User ID 1 exists
          → Fails if test 1 skipped!

✓ Independent Tests:
  test 1: Create user A, test A
  test 2: Create user B, test B
          → Both pass independently
```

## Mock/Stub Usage Guidelines

| Scenario | Tool | Rationale |
|----------|------|-----------|
| Unit test DB call | Mock | Test app logic, not DB |
| Integration test | Real DB (in-memory) | Verify schema |
| E2E test | Real services | Verify end-to-end |
| 3rd party API | Mock | API unavailable, expensive |

## Common Pitfalls

```
❌ Over-mocking (tests pass, prod fails)
   → Solution: Mock only external dependencies

❌ Shared test data (interdependent)
   → Solution: Each test owns its data

❌ Flaky tests (sometimes pass)
   → Solution: Eliminate timing, async waits

❌ No error testing (only happy path)
   → Solution: Test error scenarios

✓ Test error cases
  - Network timeout
  - Invalid input
  - Resource exhaustion
  - Concurrent access
```

## Error Message Standards

```
❌ Generic: "Test failed"
✓ Specific: "OrderService.calculate() expected 150 but got 140 (tax not applied)"

Assert structure:
  message: What? (the value)
  expected: What should be?
  actual: What is?
```

---

**Bağlantılar:** [[github-harvest-006-testing-pyramid]]
