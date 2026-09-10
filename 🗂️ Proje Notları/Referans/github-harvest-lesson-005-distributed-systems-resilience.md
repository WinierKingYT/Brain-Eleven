---
type: lesson
title: Distributed Systems Resilience - Cascading Failures
category: System Design & Architecture
status: active
created: 2026-08-27
source: donnemartin/system-design-primer
tags: [system-design, resilience, distributed-systems, failure, cascading]
---

# Cascading Failures in Distributed Systems

## Prensip

Tek bir service failure → chain reaction → entire system down

## Örnek Senaryosu

```
User Request → Order Service → Payment Service (FAILS)
                              ↓
                         Timeout waiting
                              ↓
                    Thread pool exhausted
                              ↓
                    Order Service down
                              ↓
                        API Gateway 503
                              ↓
                     Entire system unavailable
```

## Failure Cascade Mekanizması

**1. Initial Failure**
```
Payment Service down
  → Requests timeout (30s each)
```

**2. Resource Exhaustion**
```
Order Service: 
  Thread pool (100 threads) all waiting for Payment
  → No threads for other requests
  → Queue growing (memory)
```

**3. System-Wide Impact**
```
Order Service down
  ↑ dependency from:
  - API Gateway (can't route)
  - Mobile App (fails)
  - Web App (fails)
```

## Kontrol Stratejileri

**1. Circuit Breaker**
```
✓ Detect: Payment failures > threshold
✓ Stop: Don't send more requests
✓ Fail fast: Immediate error, not 30s timeout
✓ Recover: Retry after timeout
```

**2. Bulkhead**
```
✓ Isolate: Payment has own thread pool (5)
✓ Limit: Payment failures don't touch Order (100)
✓ Degrade: PaymentService fails → OrderService continues
```

**3. Timeout + Retry**
```
✓ Timeout: 5s (not infinite)
✓ Retry: Exponential backoff (1s, 2s, 4s)
✓ Limit: Max 3 retries
✓ Fail fast: After retries → error response
```

**4. Graceful Degradation**
```
Payment down:
  ✗ Don't: Crash app
  ✓ Do: 
    - Cache last price
    - Return "payment pending" status
    - Manual review later
```

## Monitoring

Essential metrics:
- Error rate per service (SLA violations?)
- Response time (timeout approaching?)
- Thread pool utilization (exhaustion risk?)
- Circuit breaker state (cascading?)

---

**Bağlantılar:** [[github-harvest-003-circuit-breaker]], [[github-harvest-013-bulkhead-pattern]]
