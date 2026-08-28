---
type: decision
title: Benchmarking Methodology - Rigorous Performance Testing
category: Performance Engineering & Profiling
status: active
created: 2026-08-28
source: brendangregg/systems-performance (Hamle 5)
tags: [benchmarking, performance-testing, methodology, measurement]
---

# Rigorous Benchmarking

**Pattern:** Scientific Approach to Performance Measurement

## Benchmark Design Principles

```
1. Isolate what you're measuring
   └─ Benchmark JSON parsing alone (not HTTP + parsing + response)

2. Warm up before measuring
   └─ JIT compilation, cache population
   └─ First 100 iterations are slow (skip them)

3. Run multiple times (sample size)
   └─ Report: min, max, average, median, stddev
   └─ Not just one run (variability!)

4. Control for noise
   └─ Stop background processes
   └─ Disable CPU frequency scaling
   └─ Pin to specific CPU core
   └─ Disable hyperthreading

5. Test realistic data
   └─ Don't benchmark with empty arrays
   └─ Use production-sized datasets
```

## Incorrect vs Correct Benchmark

**❌ Incorrect:**
```javascript
const start = Date.now()
for (let i = 0; i < 1000000; i++) {
  JSON.parse('{"x": 1}')
}
const elapsed = Date.now() - start
console.log(`${elapsed}ms`)
// Problem: Only one run, overhead included
```

**✓ Correct:**
```javascript
const iterations = 1000000

// Warm up (JIT compilation)
for (let i = 0; i < 10000; i++) {
  JSON.parse('{"x": 1}')
}

// Actual benchmark
const times = []
for (let run = 0; run < 10; run++) {
  const start = performance.now()
  for (let i = 0; i < iterations; i++) {
    JSON.parse('{"x": 1}')
  }
  const elapsed = performance.now() - start
  times.push(elapsed)
}

// Statistics
times.sort((a, b) => a - b)
const avg = times.reduce((a, b) => a + b) / times.length
const median = times[Math.floor(times.length / 2)]
const min = times[0]
const max = times[times.length - 1]
const stddev = Math.sqrt(times.reduce((sq, n) => sq + Math.pow(n - avg, 2)) / times.length)

console.log(`
  Iterations: ${iterations}
  Min:    ${min.toFixed(2)}ms
  Max:    ${max.toFixed(2)}ms
  Avg:    ${avg.toFixed(2)}ms
  Median: ${median.toFixed(2)}ms
  Stddev: ${stddev.toFixed(2)}ms
`)
```

## Load Testing (ab, wrk, k6)

```bash
# ApacheBench: Simple HTTP benchmark
ab -n 10000 -c 100 http://localhost:3000/

# Output:
# Requests per second: 5000 [#/sec]
# Time per request: 20 [ms]
# 99% complete in: 50ms

# wrk: Modern load testing
wrk -t12 -c400 -d30s http://localhost:3000/

# k6: Scripted load testing
k6 run script.js
```

## k6 Benchmark Script

```javascript
import http from 'k6/http'
import { check } from 'k6'

export const options = {
  stages: [
    { duration: '5m', target: 100 },   // Ramp up
    { duration: '10m', target: 100 },  // Stay
    { duration: '5m', target: 0 }      // Ramp down
  ]
}

export default function() {
  const res = http.get('http://localhost:3000/api/data')
  
  check(res, {
    'status is 200': (r) => r.status === 200,
    'response < 200ms': (r) => r.timings.duration < 200,
    'body not empty': (r) => r.body.length > 0
  })
}
```

## Before/After Comparison

```
Algorithm v1 (baseline):
  Iterations: 1000000
  Avg: 50.23ms
  Median: 49.95ms
  Stddev: 2.15ms

Algorithm v2 (optimized):
  Iterations: 1000000
  Avg: 15.42ms
  Median: 15.18ms
  Stddev: 0.98ms

Improvement:
  Speedup: 50.23 / 15.42 = 3.26x (226% faster)
  
Statistical Significance:
  Stddev v1: 2.15ms
  Stddev v2: 0.98ms
  Difference: 34.81ms >> 2 * sqrt(2.15² + 0.98²) = 5.1ms
  → Difference is statistically significant
```

## Gotchas

```
❌ Benchmark on laptop (too noisy)
  ✓ Use dedicated bare-metal server
  
❌ Only test 1% of the data
  ✓ Test production scale
  
❌ Optimize for benchmark but not real-world
  ✓ Include realistic overhead (network, I/O)
  
❌ Run once and declare victory
  ✓ Run 10+ times, report distribution
  
❌ Ignore tail latencies (p99)
  ✓ Report min, max, p50, p95, p99
```

---

**Bağlantılar:** [[hamle5-backend-001-event-loop-optimization]]
