---
type: decision
title: Test Pyramid - Balanced Test Distribution Strategy
category: Testing & Quality
status: active
created: 2026-08-28
source: Google Testing Blog & Martin Fowler (Hamle 6)
tags: [testing, test-pyramid, unit-tests, integration, e2e, quality]
---

# Test Pyramid: 70/20/10 Distribution

**Pattern:** Layered Test Strategy for Speed & Confidence

## The Pyramid

```
       ▲
      ╱ ╲
     ╱   ╲
    ╱  E2E ╲        10% (~100-500 tests)
   ╱ 2-5 min ╲      - End-to-end user flows
  ╱___________╲     - Selenium/Cypress/Playwright
 ╱             ╲    - Slow but high confidence
╱  Integration  ╲   20% (~400-1000 tests)
╱    5-30 sec   ╲   - API + Database integration
╱_______________╲  - Docker/Testcontainers
╱                 ╲ - Test real behavior
╱ Unit Tests      ╲ 70% (~2000-5000 tests)
╱ <100ms each    ╲ - Individual functions
╱_________________╲ - No external deps (mocked)
                    - Fast feedback loop
```

## Why 70/20/10?

```
Unit Tests (70%):
  ✓ Fast: 1000 tests in 5 seconds
  ✓ Cheap: No external resources
  ✓ Frequent: Run on every change
  ✓ Feedback: Quick bug detection
  
  Examples:
  - Math functions
  - String parsing
  - Business logic
  - Validation rules

Integration Tests (20%):
  ✓ Real database (not mocked)
  ✓ Real APIs (via testcontainers)
  ✓ Confidence: Tests actual behavior
  
  Cost:
  - Slower: 10-100ms per test
  - Resource intensive: Database, containers
  - Run less frequently: On push, before merge
  
  Examples:
  - Data access layer
  - Cache invalidation
  - Message queue processing
  - External API integration (via mocks)

E2E Tests (10%):
  ✓ Complete user journey
  ✓ Browser automation
  ✓ Highest confidence
  
  Cost:
  - Slowest: 2-5 minutes per suite
  - Flaky: Timing issues, UI changes
  - Expensive: Browsers, infrastructure
  - Run rarely: Nightly, before release
  
  Examples:
  - Login flow
  - Create order + payment
  - Search + filter results
```

## Common Mistakes

```
❌ Inverted Pyramid (too many E2E)
  - 50% E2E, 30% integration, 20% unit
  - Test suite takes 2 hours
  - Flaky tests every run
  - False confidence (passes when broken)

❌ All Unit Tests (no E2E)
  - Tests all pass
  - Integration broken in production
  - Mock drift: mocks behave differently than real

❌ Skipping Integration
  - Unit tests too isolated
  - Integration issues not caught
  - False sense of coverage
```

## Test Organization

```
Project structure:
  src/
  ├── math.js
  ├── user.js
  └── ...
  
  __tests__/
  ├── unit/
  │   ├── math.test.js
  │   └── user.test.js
  ├── integration/
  │   └── user.db.test.js
  └── e2e/
      └── login.spec.js

Jest config:
  projects: [
    {
      displayName: 'unit',
      testMatch: ['**/__tests__/unit/**'],
      testTimeout: 5000
    },
    {
      displayName: 'integration',
      testMatch: ['**/__tests__/integration/**'],
      testTimeout: 30000,
      setupFilesAfterEnv: ['./setup-db.js']
    },
    {
      displayName: 'e2e',
      testMatch: ['**/__tests__/e2e/**'],
      testTimeout: 120000,
      runner: 'jest-e2e'
    }
  ]
```

## Running Tests

```
Local development:
  npm test -- --watch unit
  → 5 seconds, immediate feedback

Before commit:
  npm test
  → 10 seconds (unit + quick integration)

Pre-merge:
  npm test:all
  → 5 minutes (all layers including E2E)

Nightly CI:
  npm test:e2e -- --verbose
  → Full suite, capture screenshots on failure
```

---

**Bağlantılar:** [[hamle6-testing-002-mock-patterns]]
