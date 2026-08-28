---
type: decision
title: Graceful Shutdown - Preventing Data Loss and Cascade Failures
category: Backend Patterns & Architecture
status: active
created: 2026-08-28
source: google/sanitizers (Hamle 5)
tags: [graceful-shutdown, reliability, distributed-systems, zero-downtime]
---

# Graceful Shutdown Pattern

**Pattern:** Safe Termination Under Load

## The Problem

```
Hard shutdown (kill -9):
  1. In-flight requests discarded
  2. Database transactions rolled back
  3. Message queues lose data
  4. Load balancer sees failures → health check fails
  5. Client sees "Connection reset"
  
Graceful shutdown (SIGTERM):
  1. Stop accepting new requests
  2. Drain existing connections
  3. Commit in-flight work
  4. Clean close
```

## Shutdown Sequence

```javascript
// 1. Signal handler
process.on('SIGTERM', () => {
  console.log('Graceful shutdown initiated')
  
  // 2. Stop accepting new connections
  server.close()
  
  // 3. Drain existing requests (timeout: 30s)
  setTimeout(() => {
    console.error('Forced shutdown timeout')
    process.exit(1)
  }, 30000)
})

// 4. On request completion, exit
server.on('close', async () => {
  // Drain database connections
  await db.pool.end()
  
  // Close message queues
  await queue.disconnect()
  
  // Exit cleanly
  process.exit(0)
})
```

## Health Check Coordination

```
Load balancer polling:
  GET /health
  
Graceful shutdown:
  1. SIGTERM received
  2. /health immediately returns 503 (sick)
  3. Load balancer drains traffic (within 5-30s)
  4. Server closes after timeout
  
Result: Zero data loss, smooth failover
```

## Message Queue Safety

```javascript
// Message processing with graceful shutdown
const processMessage = async (msg) => {
  let acknowledged = false
  
  try {
    // Process
    await handleMessage(msg)
    
    // Only ACK after success
    await msg.ack()
    acknowledged = true
    
  } catch (err) {
    // On error: requeue (if not acknowledged)
    if (!acknowledged) {
      await msg.nack(true) // requeue
    }
    throw err
  }
}

// On shutdown: drain queue before closing
process.on('SIGTERM', async () => {
  await queue.drain() // Wait for current messages
  await queue.close()
  process.exit(0)
})
```

## Kubernetes Orchestration

```yaml
spec:
  terminationGracePeriodSeconds: 30
  
  containers:
  - name: app
    lifecycle:
      preStop:
        exec:
          command: ["/bin/sh", "-c", "sleep 15"]
  
  # Sequence:
  # 1. SIGTERM sent (with 30s grace period)
  # 2. preStop sleep 15s (gives health checks time to drain)
  # 3. App has 15s to gracefully shutdown
  # 4. If still running at 30s: SIGKILL
```

## Timeout Strategy

```
Shutdown phases:
  Phase 1 (0-5s): Stop accepting, return 503
  Phase 2 (5-25s): Drain connections
  Phase 3 (25-30s): Force close (SIGKILL incoming)
  
Calculation:
  grace_period = P95(request_duration) + 5s buffer
  
Example:
  P95 request = 20s → grace_period = 25-30s
```

---

**Bağlantılar:** [[hamle5-backend-004-middleware-patterns]]
