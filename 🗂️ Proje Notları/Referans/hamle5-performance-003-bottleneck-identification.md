---
type: decision
title: Bottleneck Identification - Systematic Performance Analysis
category: Performance Engineering & Profiling
status: active
created: 2026-08-28
source: brendangregg/systems-performance (Hamle 5)
tags: [performance, bottleneck, analysis, methodology, optimization]
---

# Identifying Performance Bottlenecks

**Pattern:** Systematic Method for Finding Root Causes

## The Golden Path (USE Method)

```
For each resource:
  U = Utilization (how busy is it?)
  S = Saturation (how much queue depth?)
  E = Errors (what's failing?)

Resources to check:
  1. CPU
  2. Memory
  3. Disk I/O
  4. Network
  5. Database connections
```

## CPU Analysis

```
High CPU (>80%):
  ❌ Problem: CPU-bound bottleneck
  
  Check flame graph:
    - Is it algorithm inefficiency?
    - Is it regex or string manipulation?
    - Is it garbage collection?
    
  Solutions:
    ✓ Optimize algorithm (change O(n²) to O(n log n))
    ✓ Cache results (avoid re-computation)
    ✓ Parallelize (use multiple cores)
    ✓ Move to Worker Thread

Low CPU (<20%):
  ❌ Problem: Not CPU-bound (I/O bound instead)
  
  Check what's waiting:
    - Disk I/O? (check disk utilization)
    - Network? (check network latency)
    - Database? (check query performance)
    - Lock contention? (check traces)
```

## Memory Analysis

```
High Memory Usage:
  ❌ Problem: Memory leak or inefficient data structures
  
  Check:
    1. Heap snapshot (Chrome DevTools)
    2. Find largest objects
    3. Is it holding onto stale references?
    
  Solutions:
    ✓ Remove event listeners
    ✓ Clear caches periodically
    ✓ Use WeakMap for caches
    ✓ Implement object pooling

Memory Pressure:
  ❌ If memory near limit:
    - GC pauses increase
    - VM swapping to disk
    - Overall system slows
    
  Solutions:
    ✓ Increase available memory
    ✓ Reduce memory footprint
    ✓ Implement caching more aggressively
```

## Disk I/O Analysis

```
High Disk Wait (iostat -x 1):
  await > 10ms: slow disk or queue

  Check:
    1. What's reading/writing?
    2. Is it database WAL?
    3. Is it log files?
    4. Is it temporary files?
    
  Solutions:
    ✓ Move database to SSD
    ✓ Batch writes (reduce I/O calls)
    ✓ Implement cache layer
    ✓ Use async writes (write buffer)
```

## Database Bottleneck

```
Check sequence:
  1. Query latency (EXPLAIN ANALYZE)
     └─ Add index? Rewrite query?
  
  2. Connection pool saturation
     └─ Increase pool size?
     └─ Close idle connections?
  
  3. Lock contention
     └─ Simplify transactions?
     └─ Reduce transaction duration?
  
  4. Memory (shared_buffers, cache hit ratio)
     └─ Increase shared_buffers?
     └─ Cache more data?
```

## Network Bottleneck

```
Check:
  1. Bandwidth (netstat -i)
     └─ Is network saturated?
  
  2. Latency (traceroute, mtr)
     └─ Where's the delay?
  
  3. Packet loss (ping, mtr)
     └─ Is network unstable?

Solutions:
  ✓ Compress responses (gzip)
  ✓ Cache at edge (CDN)
  ✓ Reduce payload size
  ✓ Use connection pooling (HTTP keep-alive)
```

## The Right Order

```
1. Profile CPU (flame graph)
   └─ If high CPU: optimize algorithm
   └─ If low CPU: investigate I/O

2. Check database (query plans, lock waits)
   └─ If slow queries: add index, rewrite
   └─ If lock waits: simplify transaction

3. Monitor memory (heap snapshots)
   └─ If leaking: find references
   └─ If insufficient: add memory or cache

4. Check network (latency, bandwidth)
   └─ If slow: compress, cache, reduce payload

5. Iterate: re-profile after each fix
```

---

**Bağlantılar:** [[hamle5-performance-004-benchmarking-methodology]]
