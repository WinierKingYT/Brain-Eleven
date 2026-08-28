---
type: reference
title: API Design Hub
category: Navigation Index
status: active
created: 2026-08-28
tags: [index, api-design, rest, graphql, pagination]
---

# API Design Index

Navigation to all API design patterns (REST, GraphQL, versioning, pagination, etc.).

## By Topic

### REST API Design
- **Resource Design**: [[hamle6-api-001-rest-resource-design]] (noun-based URLs, HTTP semantics)
- **Standards & Conventions**: [[hamle4-003-rest-api-standards]] (REST best practices)

### GraphQL
- **Schema Modeling**: [[hamle6-api-002-graphql-schema]] (domain-driven design)

### API Evolution
- **Versioning**: [[hamle6-api-003-api-versioning]] (URL vs header, deprecation)
- **Pagination**: [[hamle6-api-004-pagination]] (offset vs cursor vs keyset)

### API Quality
- **Idempotency**: [[hamle4-004-api-idempotency]] (safe retries)
- **Error Handling**: [[hamle4-007-error-handling-philosophy]] (proper responses)

## By Hamle

| Hamle | Focus |
|-------|-------|
| **Hamle 4** | Standards, idempotency, REST conventions |
| **Hamle 6** | Deep patterns (REST, GraphQL, versioning, pagination) |

## Cross-Domain Connections

- **API ← Security**: [[hamle6-security-001-argon2-password-hashing]] (auth endpoints)
- **API ← Testing**: [[hamle6-testing-001-test-pyramid]] (E2E API testing)
- **API ← Backend**: [[hamle5-backend-001-event-loop-optimization]] (async request handling)

## Quick Start: API Design Decision Tree

**Building REST API?**
1. Design: [[hamle6-api-001-rest-resource-design]] (noun-based resources)
2. Version: [[hamle6-api-003-api-versioning]] (handle evolution)
3. Protect: [[hamle6-security-004-rate-limiting-distributed]] (rate limiting)

**Building GraphQL?**
1. Schema: [[hamle6-api-002-graphql-schema]] (domain modeling)
2. Performance: [[hamle5-performance-002-apm-instrumentation]] (N+1 prevention)

**Handling Pagination?**
1. Read: [[hamle6-api-004-pagination]] (algorithm comparison)
2. Implement: Choose keyset > cursor > offset

---

**Last updated:** 2026-08-28
**Total patterns:** 7+ across Hamle 4-6
