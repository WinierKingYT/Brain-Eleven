---
type: decision
title: REST Resource Design - Noun-Based URLs & HTTP Semantics
category: API Design
status: active
created: 2026-08-28
source: RESTful Web API Design Best Practices (Hamle 6)
tags: [api-design, rest, resources, http-semantics, discoverability]
---

# REST Resource Design Fundamentals

**Pattern:** Resource-Centric API with HTTP Verbs as Operations

## Right Way (Noun-Based)

```
Noun-based resource URLs:
  GET    /users              → List users
  POST   /users              → Create user
  GET    /users/123          → Get user 123
  PATCH  /users/123          → Update user 123
  DELETE /users/123          → Delete user 123

Nested resources (relationships):
  GET    /users/123/posts    → Get posts by user 123
  POST   /users/123/posts    → Create post for user 123
  GET    /users/123/posts/5  → Get post 5 by user 123
  DELETE /users/123/posts/5  → Delete post 5
```

## Wrong Way (Verb-Based)

```
❌ Verb-based URLs:
  GET    /getUser/123
  POST   /createUser
  PUT    /updateUser/123
  DELETE /deleteUser/123
  
  Problems:
  - Violates REST conventions
  - Can't cache POST requests (caching based on method + URL)
  - Doesn't scale (new action = new URL)
  - Not discoverable
```

## HTTP Semantics Matter

```
GET: Safe, idempotent, retrieve data
  ✓ No side effects
  ✓ Can cache indefinitely
  ✓ Can retry on failure
  ✗ Payload in query string (size limit)

POST: Not idempotent, create new resource
  ✓ Payload in body (unlimited size)
  ✓ Creates new resource each time
  ✗ Cannot cache
  ✗ Retries cause duplicates (need idempotency key)

PUT: Idempotent, full replacement
  ✓ Idempotent (can retry safely)
  ✓ Replaces entire resource
  ✗ Rarely used (partial updates more common)

PATCH: Idempotent, partial update
  ✓ Update specific fields
  ✓ Idempotent
  ✓ Safe to retry

DELETE: Idempotent, remove resource
  ✓ Idempotent (delete twice = same result)
  ✗ No response body (usually)
```

## Nested Resource Limits

```
Good (2 levels):
  GET /users/123/posts
  
  Clear relationship: posts belong to user 123
  
Acceptable (3 levels):
  GET /teams/5/projects/8/tasks
  
  Hierarchy: teams > projects > tasks
  Make sense semantically

Bad (4+ levels):
  GET /orgs/1/teams/2/projects/3/repos/4/branches/5/commits
  
  Too deep, ambiguous
  Better: GET /commits?repo=4&branch=5
```

## Filtering & Sorting

```
Query parameters for non-resource operations:
  GET /users?status=active&sort=-created_at
  
  Meanings:
  - status=active:    Filter by status
  - sort=-created_at: Sort descending by created_at
  - limit=20:         Page size
  - offset=40:        Pagination offset

Collection operations:
  GET /users?email=alice@example.com  → Search
  GET /users?created_after=2024-01-01 → Range query
  GET /posts?tags=python,javascript   → Multiple values
```

## Status Codes Matter

```
Success (2xx):
  200 OK              ← GET, PUT, PATCH, DELETE
  201 Created         ← POST (new resource created)
  202 Accepted        ← Async operation queued
  204 No Content      ← DELETE (no response body)

Client Error (4xx):
  400 Bad Request     ← Malformed request
  401 Unauthorized    ← Missing auth
  403 Forbidden       ← Authenticated but no permission
  404 Not Found       ← Resource doesn't exist
  422 Unprocessable   ← Validation failed (vs 400)
  429 Too Many        ← Rate limited

Server Error (5xx):
  500 Internal Error  ← Unexpected error
  503 Service Unavail ← Temporarily down
```

---

**Bağlantılar:** 
- [[hamle6-api-002-graphql-schema]] (schema design patterns)
- [[hamle6-security-001-argon2-password-hashing]] (auth endpoint security)
- [[hamle6-security-004-rate-limiting-distributed]] (API rate limiting)
- [[hamle6-testing-001-test-pyramid]] (E2E testing API endpoints)
