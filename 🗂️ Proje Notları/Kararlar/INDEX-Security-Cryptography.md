---
type: reference
title: Security & Cryptography Hub
category: Navigation Index
status: active
created: 2026-08-28
tags: [index, security, cryptography, authentication, authorization]
---

# Security & Cryptography Index

Quick navigation to all security patterns across Hamle 3-6.

## By Topic

### Authentication & Authorization
- **JWT & Tokens**: [[hamle6-security-002-jwt-refresh-tokens]] (refresh token rotation)
- **Password Hashing**: [[hamle6-security-001-argon2-password-hashing]] (memory-hard hashing)
- **OAuth & Auth Flows**: [[hamle4-009-jwt-validation]] (JWT validation)

### Secret Management
- **Secret Rotation**: [[hamle6-security-003-secret-rotation]] (versioned rotation)
- **Key Hierarchy**: [[hamle4-007-error-handling-philosophy]] (secure patterns)

### API Security
- **Rate Limiting**: [[hamle6-security-004-rate-limiting-distributed]] (sliding window, DDoS)
- **CORS & CSRF**: [[hamle4-008-owasp-checklist]] (OWASP Top 10)

### Database & Query Security
- **SQL Injection Prevention**: [[hamle4-008-owasp-checklist]] (parameterized queries)
- **Input Validation**: [[hamle4-008-owasp-checklist]] (schema enforcement)

## By Hamle

| Hamle | Notes | Focus |
|-------|-------|-------|
| **Hamle 3** | Foundational patterns from GitHub harvest | Industry standards |
| **Hamle 4** | [[hamle4-008-owasp-checklist]], [[hamle4-009-jwt-validation]] | OWASP, JWT, security checklist |
| **Hamle 5** | (Covered in other domains) | Performance-aware security |
| **Hamle 6** | [[hamle6-security-001-argon2-password-hashing]], [[hamle6-security-002-jwt-refresh-tokens]], [[hamle6-security-003-secret-rotation]], [[hamle6-security-004-rate-limiting-distributed]] | Deep security patterns (4 notes) |

## Cross-Domain Connections

- **Security → API**: [[hamle6-api-001-rest-resource-design]] (secure endpoints)
- **Security → DevOps**: [[hamle6-devops-001-structured-logging-json]] (audit trails)
- **Security → Testing**: [[hamle6-testing-001-test-pyramid]] (security test coverage)

## Quick Start

**New to security patterns?**
1. Start: [[hamle4-008-owasp-checklist]] (foundational checklist)
2. Deep dive: [[hamle6-security-001-argon2-password-hashing]] (password hashing)
3. Production: [[hamle6-security-004-rate-limiting-distributed]] (DDoS protection)

**Building secure APIs?**
1. Auth design: [[hamle6-security-002-jwt-refresh-tokens]] (token strategy)
2. API design: [[hamle6-api-001-rest-resource-design]] (resource design)
3. Rate limit: [[hamle6-security-004-rate-limiting-distributed]] (protection)

---

**Last updated:** 2026-08-28
**Total patterns:** 8+ across Hamle 3-6
