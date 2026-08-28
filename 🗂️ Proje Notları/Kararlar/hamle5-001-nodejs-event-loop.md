---
type: decision
title: Node.js Event Loop - Understanding and Optimization
category: Backend Patterns & Architecture
status: active
created: 2026-08-27
source: goldbergyoni/nodejs-best-practices (Hamle 5)
tags: [nodejs, event-loop, async, performance, patterns]
---

# Node.js Event Loop Deep Dive

**Pattern:** Non-blocking I/O and Asynchronous Execution

## Event Loop Phases

```
┌─ timers: execute callbacks from setTimeout/setInterval
├─ pending callbacks: deferred to next iteration
├─ idle, prepare: internal use
├─ poll: retrieve new I/O events
├─ check: execute setImmediate callbacks
└─ close callbacks: close event callbacks
```

## Critical Insights

**Blocking the event loop:**
```javascript
// ❌ CPU-intensive work blocks everything
while (true) {
  calculateHash(); // All other requests wait!
}

// ✓ Use Worker Threads
import { Worker } from 'worker_threads'
const worker = new Worker('./cpu-task.js')
```

**Promise microtasks vs macrotasks:**
```javascript
console.log(1)
Promise.resolve().then(() => console.log(2))
setTimeout(() => console.log(3), 0)
// Output: 1, 2, 3
// Microtasks (promises) execute before macrotasks (timers)
```

## Performance Bottlenecks

1. **Synchronous operations**
   - fs.readFileSync (blocks entire server)
   - Parsing large JSON
   - Encryption/hashing without async

2. **Too many timers**
   - setInterval leaks if not cleared
   - setTimeout accumulates in queue

3. **Memory accumulation**
   - Event listeners not removed
   - Callbacks keeping references

## Optimization Techniques

```
1. Use async/await (cleaner than callbacks)
2. Worker Threads for CPU work
3. Stream large files (not all-at-once)
4. Batch operations (reduce event loop pressure)
5. Profile with --inspect flag
```

---

**Bağlantılar:** [[hamle5-002-go-goroutines]]
