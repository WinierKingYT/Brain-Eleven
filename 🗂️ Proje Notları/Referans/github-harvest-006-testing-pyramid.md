---
type: decision
title: Testing Pyramid - Test Distribution Strategy
category: Testing & TDD
status: active
created: 2026-08-27
source: shrop/automated-testing-best-practices
tags: [testing, tdd, quality, pyramid, coverage]
---

# Testing Pyramid

**Pattern:** Optimal Test Distribution for Speed and Coverage

## Karar

Test suiti'ni hızlı (unit) → orta (service) → yavaş (UI) şeklinde organize et. Ideal orantı:

```
         ▲ E2E/UI (5-10%)
        ╱ ╲
       ╱   ╲  Service/Integration (15-25%)
      ╱     ╲
     ╱       ╲ Unit Tests (70-80%)
    ╱_________╲
```

## Her Katmanın Rolü

**Unit Tests (70-80%)**
- Hız: < 1ms per test
- Scope: Single function/component
- Tools: Jest, Pytest, xUnit
- Mocking: External dependencies

**Service Tests (15-25%)**
- Hız: 10-100ms per test
- Scope: Service method + domain entities
- Tools: WebApplicationFactory, TestContainers
- Amaç: Component interactions verify

**UI/E2E Tests (5-10%)**
- Hız: 1000ms+ per test
- Scope: Critical user workflows
- Tools: Playwright, Cypress, Selenium
- Amaç: Real user scenarios

## Neden Bu Oran?

**Ekonomi:**
- Unit test: 1 saniyede 1000+ test (hızlı feedback)
- Service test: 1 saniyede 10-100 test (orta feedback)
- UI test: 1 saniyede 1 test (yavaş feedback)

**Total Build Time:** < 10 dakika (CI/CD feasible)

## Anti-Pattern

```
❌ Test pyramid ters: UI tests çoğunluk
   → Slow feedback loop (saatler)
   → Brittle (UI changes → cascading failures)
   → Expensive (maintenance nightmare)
```

---

**Bağlantılar:** [[github-harvest-007-tdd-cycle]], [[github-harvest-008-aaa-structure]]
