---
type: decision
title: Rate Limiting - Strategies and Implementation
category: Security & DevOps
status: active
created: 2026-08-27
source: shieldfy/API-Security-Checklist (Hamle 4)
tags: [security, rate-limiting, api, resilience]
---

# Rate Limiting Strategies

**Pattern:** Prevent Abuse and Ensure Fairness

## Three Algorithms

**1. Token Bucket**
```
Capacity: 100 tokens
Refill: 10 tokens/second

Request arrives:
  If tokens > 0: grant, tokens--
  Else: reject (429 Too Many Requests)
```

**2. Sliding Window**
```
Track: requests in last 60 seconds
Limit: 100 requests/minute

Each request:
  Check count in [now-60s, now]
  If >= 100: reject
  Else: allow
```

**3. Leaky Bucket**
```
Queue requests at fixed rate
Excess: dropped or rejected
Steady output: prevents bursts
```

## Rate Limit Headers

```
HTTP/1.1 200 OK
RateLimit-Limit: 100
RateLimit-Remaining: 42
RateLimit-Reset: 1693158900
```

## Per-Resource Limits

```
Public API:
  /users: 1000 req/hour
  /orders: 10 req/second (sensitive)
  /search: 100 req/hour

Authenticated API:
  /admin: 50 req/hour (privileged)
  /data: 1000 req/hour
```

## Bypass Risks

- ❌ Client-side checking only (trivial to bypass)
- ❌ Global limit (single user takes all quota)
- ❌ No persistence (restart = reset limits)
- ✓ Server-side enforcement (Redis/DB)
- ✓ Per-user limits
- ✓ Distributed rate limiting

---

**Bağlantılar:** [[hamle4-008-owasp-checklist]]
