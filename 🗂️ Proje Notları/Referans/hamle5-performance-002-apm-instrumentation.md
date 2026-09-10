---
type: decision
title: APM Instrumentation - Distributed Tracing at Scale
category: Performance Engineering & Profiling
status: active
created: 2026-08-28
source: open-telemetry/opentelemetry (Hamle 5)
tags: [apm, tracing, observability, distributed-systems, performance]
---

# Application Performance Monitoring (APM)

**Pattern:** Distributed Tracing for Production Performance

## Core Concepts

```
Trace: Single user request across all services
Span: One operation within a service

Example:
  User clicks → API Gateway [span] 
              → Backend [span] 
                → Database [span]
                → Cache [span]
              → Response [span]
```

## OpenTelemetry (Standard)

```javascript
import { NodeTracerProvider } from '@opentelemetry/node'
import { JaegerExporter } from '@opentelemetry/exporter-jaeger'
import { BatchSpanProcessor } from '@opentelemetry/tracing'

// Setup provider
const provider = new NodeTracerProvider()

// Export to Jaeger
const exporter = new JaegerExporter({
  host: 'localhost',
  port: 6831
})

provider.addSpanProcessor(new BatchSpanProcessor(exporter))
provider.register()

// Get tracer
const tracer = provider.getTracer('my-app')

// Create spans
const span = tracer.startSpan('fetch-user')
try {
  const user = await db.getUser(123)
  span.setStatus({ code: SpanStatusCode.OK })
} catch (err) {
  span.recordException(err)
  span.setStatus({ code: SpanStatusCode.ERROR })
} finally {
  span.end()
}
```

## Automatic Instrumentation

```javascript
// Most frameworks auto-instrument with OpenTelemetry
// npm install @opentelemetry/auto

// No code changes needed - automatically traces:
// - HTTP requests
// - Database queries
// - External API calls
// - Message queues
```

## Key Metrics to Trace

```
1. Request Latency (P50, P95, P99)
   └─ Where is time spent?
   └─ Database? API call? JSON parsing?

2. Error Rate
   └─ Which service is failing?
   └─ What's the error?
   └─ How many users affected?

3. Dependency Latency
   └─ Database: 50ms
   └─ Cache: 2ms
   └─ External API: 200ms

4. Throughput
   └─ Requests per second
   └─ Database queries per second
   └─ Cache hits vs misses
```

## Common Issues Found by APM

**Slow Database Query**
```
Trace shows:
  API response: 1000ms
  Database query: 950ms (95%)
  
Action:
  1. Use EXPLAIN ANALYZE
  2. Add index
  3. Recheck trace (verify 100x improvement)
```

**N+1 Query Problem**
```
Trace shows:
  GET /users/123/posts
  Query: SELECT users WHERE id=123     (1ms)
  Query: SELECT posts WHERE user=123   (5ms)
  Query: SELECT comments WHERE post=1  (2ms)  ← 10 per post!
  Query: SELECT comments WHERE post=2  (2ms)
  ...
  Total: 100+ queries (100ms+)
  
Action:
  1. Use JOIN
  2. Use batch query
  3. Implement dataloader
```

**Cascading Timeouts**
```
Trace shows:
  API → Service A (timeout)  → cascades to Service B
                             → cascades to Service C
                             → client gets timeout at 30s
                             → Service A still processing
  
Action:
  1. Implement circuit breaker
  2. Set timeout < upstream timeout
  3. Return fallback data
```

## Jaeger UI Exploration

```
1. Click on trace ID
2. View timeline of spans
3. Identify:
   - Longest spans (bottlenecks)
   - Parallel vs sequential operations
   - Error spans (red highlights)
   - Service dependencies
```

---

**Bağlantılar:** [[hamle5-performance-003-bottleneck-identification]]
