---
type: decision
title: Node.js Event Loop - Deep Optimization for Production
category: Backend Patterns & Architecture
status: active
created: 2026-08-27
source: goldbergyoni/nodejs-best-practices (Hamle 5)
tags: [nodejs, event-loop, performance, production, optimization]
---

# Event Loop Optimization Deep Dive

**Pattern:** Preventing Event Loop Starvation in Production

## The Problem

```javascript
// ❌ Production issue
app.get('/api/data', async (req, res) => {
  // High CPU work blocks other requests
  const hash = hashLargeDataset(req.body)
  res.json({ hash })
})

// Result at 1000 req/sec:
// - Request latency: 50ms → 5000ms
// - Other requests queue up
// - Health checks timeout (circuit breaker opens)
```

## Solution 1: Worker Threads (CPU Work)

```javascript
// cpu-task.js (Worker)
import { parentPort } from 'worker_threads'
parentPort.on('message', (data) => {
  const result = expensiveCalc(data)
  parentPort.postMessage(result)
})

// main.js
import { Worker } from 'worker_threads'
const worker = new Worker('./cpu-task.js')

app.get('/expensive', (req, res) => {
  worker.postMessage(req.body)
  worker.once('message', (result) => {
    res.json(result)
  })
})
```

## Solution 2: Batching (I/O Work)

```javascript
// ❌ Individual DB calls
for (const item of items) {
  await db.insert(item) // 100 queries
}

// ✓ Batch operations
await db.insertMany(items) // 1 query
```

## Solution 3: Microtask Queue Management

```javascript
// ❌ Microtask queue saturates
setInterval(() => {
  Promise.all(bigArrayOfPromises).then(...)
}, 0) // Every tick

// ✓ Queue management
setImmediate(() => {
  // Runs AFTER I/O operations
  // Doesn't starve the poll phase
})
```

## Monitoring Event Loop Health

```javascript
import toobusy from 'toobusy-js'

// If event loop lag > 50ms, reject new requests
app.use((req, res, next) => {
  if (toobusy()) {
    res.status(503).send('Server too busy')
  } else {
    next()
  }
})

// Track lag metric
setInterval(() => {
  console.log(`Event loop lag: ${toobusy.lag()}ms`)
}, 1000)
```

## Gotchas

```
❌ setImmediate inside setImmediate (recursive starvation)
❌ Unhandled promise rejections (hangs event loop)
❌ Large JSON parsing (use streaming parsers)
❌ Synchronous file reads in request handlers

✓ Use --inspect flag to profile
✓ Monitor event loop lag in production
✓ Queue health checks separately (don't starve them)
```

---

**Bağlantılar:** [[hamle5-backend-002-connection-pooling]]
