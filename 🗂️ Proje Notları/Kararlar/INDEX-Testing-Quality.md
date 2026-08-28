---
type: reference
title: Testing & Quality Hub
category: Navigation Index
status: active
created: 2026-08-28
tags: [index, testing, quality, test-pyramid, tdd]
---

# Testing & Quality Index

Navigation to testing patterns: pyramid structure, mocking, integration, E2E, and test quality.

## By Topic

### Test Organization
- **Test Pyramid**: [[hamle6-testing-001-test-pyramid]] (70/20/10 distribution)
- **TDD Cycle**: [[github-harvest-006-testing-pyramid]] (Hamle 3 foundation)
- **Testing Patterns**: [[hamle4-015-testing-patterns-best-practices]] (best practices)

### Test Doubles & Mocking
- **Mock vs Stub vs Spy**: [[hamle6-testing-002-mocking-patterns]] (test double strategy)

### Test Layers
- **Unit Testing**: Test pyramid (70%, <100ms)
- **Integration Testing**: [[hamle6-testing-003-integration-db]] (real databases, transactions)
- **E2E Testing**: [[hamle6-testing-004-e2e-pom]] (Page Object Model, user journeys)

### Quality Metrics
- **Code Coverage**: [[hamle4-006-clean-code-checklist]] (80%+ target)
- **Test Quality**: Mutation testing, flaky detection (prevent false confidence)

## By Hamle

| Hamle | Focus |
|-------|-------|
| **Hamle 3** | Foundation: test pyramid, TDD cycles |
| **Hamle 4** | Patterns, clean code, testing practices |
| **Hamle 6** | Deep patterns: pyramid, mocking, integration, E2E |

## Cross-Domain Connections

- **Testing ← Security**: [[hamle6-security-001-argon2-password-hashing]] (password hashing tests)
- **Testing ← API**: [[hamle6-api-001-rest-resource-design]] (E2E API tests)
- **Testing ← Performance**: [[hamle5-performance-004-benchmarking-methodology]] (perf tests)

## Quick Start: Test Strategy

**Starting new project?**
1. Structure: [[hamle6-testing-001-test-pyramid]] (70/20/10)
2. Unit: [[github-harvest-006-testing-pyramid]] (AAA pattern)
3. Quality: [[hamle4-006-clean-code-checklist]] (80% coverage goal)

**Adding integration tests?**
1. Strategy: [[hamle6-testing-003-integration-db]] (real DB, transactions)
2. Organization: Separate test folders by layer

**Improving test quality?**
1. Read: [[hamle4-015-testing-patterns-best-practices]] (advanced patterns)
2. Focus on mutation testing and flaky detection

---

**Last updated:** 2026-08-28
**Total patterns:** 6+ across Hamle 3-6
