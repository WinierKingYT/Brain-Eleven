---
type: decision
title: Flame Graphs - Visualizing CPU Profiling Data
category: Performance Engineering & Profiling
status: active
created: 2026-08-28
source: brendangregg/perf-tools (Hamle 5)
tags: [performance, profiling, flame-graphs, cpu, profiling]
---

# Flame Graphs for Performance Analysis

**Pattern:** Identifying Performance Bottlenecks Visually

## What Flame Graphs Show

```
Each stack frame = one function call
Width = time spent in that function
Height = call stack depth

Wide frame = bottleneck
Narrow frame = quick operation
```

## Reading a Flame Graph

```
           [main]
        /    |     \
    [init] [loop] [cleanup]
      |      |      |
    [db]  [api]  [gc]
     /      / \
  [sql] [json] [http]

Width interpretation:
  [loop] is very wide → most time in loop
  [json] is wide → JSON parsing is slow
  [gc] is narrow → garbage collection quick
```

## Generating Flame Graphs (Linux)

```bash
# 1. Install perf and FlameGraph tools
sudo apt install linux-tools
git clone https://github.com/brendangregg/FlameGraph.git

# 2. Record CPU profile
sudo perf record -F 99 -p <pid> -g -- sleep 30

# 3. Convert to readable format
sudo perf script | ./FlameGraph/stackcollapse-perf.pl | \
  ./FlameGraph/flamegraph.pl > flame.svg

# 4. Open flame.svg in browser
```

## Node.js Profiling

```javascript
// Use built-in inspector
// node --prof app.js

// Then:
node --prof-process isolate-*.log > profile.txt

// Or use flamegraph-compatible profiling:
import profiler from '@node-rs/jieba-pro'

// For async/await:
import { performance } from 'perf_hooks'

performance.mark('start')
await expensiveOperation()
performance.mark('end')
performance.measure('operation', 'start', 'end')
```

## Chrome DevTools Profiler

```javascript
// Built-in profiler
// Chrome DevTools → Performance tab → Record

// Manual marks
performance.mark('data-fetch-start')
const data = await fetch('/api/data')
performance.mark('data-fetch-end')
performance.measure('data-fetch', 'data-fetch-start', 'data-fetch-end')

// View in DevTools Performance timeline
```

## Interpreting Common Patterns

**Wide base (bad):**
```
    CPU heavy at main level
    → Algorithm is inefficient
    → Consider optimization
```

**Tall spikes:**
```
    Deep call stacks
    → Function call overhead
    → Consider inlining
```

**Many thin lines:**
```
    Lots of context switches
    → System call overhead
    → Reduce system calls
```

## Common Optimizations Found

```
1. JSON parsing (wide frame)
   → Use streaming parser
   → Cache parsed results

2. String concatenation (wide frame)
   → Use StringBuilder/join
   → Pre-allocate space

3. Regular expressions (wide frame)
   → Cache compiled regex
   → Use faster algorithm

4. Memory allocation (scattered)
   → Reduce allocations
   → Object pooling
```

---

**Bağlantılar:** [[hamle5-performance-002-apm-instrumentation]]
