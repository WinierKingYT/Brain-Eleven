---
type: decision
title: Structured Logging with JSON Envelope - Correlation & Context
category: DevOps & Observability
status: active
created: 2026-08-28
source: OpenTelemetry Logging Spec (Hamle 6)
tags: [devops, logging, structured, json, observability, tracing]
---

# Structured Logging Pattern

**Pattern:** JSON Envelope + Context Propagation for Request Tracing

## The Problem

```
Unstructured logs:
  "User 123 logged in at 2024-01-15T10:30:45Z from 192.168.1.1"
  
  ✗ Can't parse programmatically
  ✗ Correlating request across 5 services = manual grep
  ✗ Timestamps inconsistent format
  ✗ No trace ID → can't connect logs to metrics/traces
```

## Solution: JSON Envelope

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "service": "auth-service",
  "traceId": "550e8400-e29b-41d4-a716-446655440000",
  "spanId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "userId": "user123",
  "ipAddress": "192.168.1.1",
  "action": "login",
  "duration_ms": 145,
  "http_status": 200,
  "message": "User successfully authenticated"
}
```

## Implementation

```javascript
// Create structured logger
const createLogger = (serviceName) => {
  return {
    info: (message, context = {}) => {
      const logEntry = {
        timestamp: new Date().toISOString(),
        level: 'INFO',
        service: serviceName,
        traceId: context.traceId || generateId(),
        spanId: context.spanId || generateId(),
        userId: context.userId,
        message,
        ...context
      }
      console.log(JSON.stringify(logEntry))
    }
  }
}

// Middleware: Context propagation via AsyncLocalStorage
const { AsyncLocalStorage } = require('async_hooks')
const requestContext = new AsyncLocalStorage()

app.use((req, res, next) => {
  const context = {
    traceId: req.headers['x-trace-id'] || generateId(),
    spanId: generateId(),
    userId: req.user?.id,
    ipAddress: req.ip,
    method: req.method,
    path: req.path
  }
  
  requestContext.run(context, () => {
    res.setHeader('X-Trace-ID', context.traceId)
    next()
  })
})

// Use in handlers
app.post('/login', (req, res) => {
  const ctx = requestContext.getStore()
  const logger = createLogger('auth')
  
  const startTime = Date.now()
  
  try {
    const user = authenticate(req.body)
    const duration = Date.now() - startTime
    
    logger.info('User login successful', {
      ...ctx,
      userId: user.id,
      duration_ms: duration,
      http_status: 200
    })
    
    res.json({ token: issueToken(user) })
  } catch (err) {
    logger.info('Login failed', {
      ...ctx,
      error: err.message,
      duration_ms: Date.now() - startTime,
      http_status: 401
    })
    res.status(401).json({ error: err.message })
  }
})

// Call downstream service
app.post('/transfer', async (req, res) => {
  const ctx = requestContext.getStore()
  
  const response = await fetch('http://payment-service/pay', {
    method: 'POST',
    headers: {
      'X-Trace-ID': ctx.traceId,  // Propagate trace
      'X-Span-ID': ctx.spanId
    },
    body: JSON.stringify(req.body)
  })
})
```

## Correlation Across Services

```
Flow:
  Client → API Gateway
           X-Trace-ID: 550e8400-e29b-41d4-a716-446655440000
  
  → Auth Service
    X-Trace-ID: 550e8400-e29b-41d4-a716-446655440000
    log: traceId: 550e8400-e29b-41d4-a716-446655440000
  
  → Payment Service (via HTTP header)
    X-Trace-ID: 550e8400-e29b-41d4-a716-446655440000
    log: traceId: 550e8400-e29b-41d4-a716-446655440000
  
Query all logs for request:
  cat logs/* | jq 'select(.traceId == "550e8400-...")'
  
Result: Complete request flow across all services
```

## Filtering PII

```javascript
const sanitizeLog = (entry) => {
  const patterns = [
    { regex: /password["\s:]*"?[^"]*"?/gi, replacement: 'password:***' },
    { regex: /token["\s:]*"?[^"]*"?/gi, replacement: 'token:***' },
    { regex: /email["\s:]*"?[^\s,}"]*"?/gi, replacement: 'email:***' },
    { regex: /ssn["\s:]*"?[\d-]*"?/gi, replacement: 'ssn:***' }
  ]
  
  let sanitized = JSON.stringify(entry)
  patterns.forEach(({ regex, replacement }) => {
    sanitized = sanitized.replace(regex, replacement)
  })
  
  return JSON.parse(sanitized)
}
```

---

**Bağlantılar:** [[hamle6-devops-002-prometheus-metrics]]
