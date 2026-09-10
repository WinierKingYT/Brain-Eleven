---
type: decision
title: React Fiber - Understanding Incremental Rendering
category: Frontend Performance & Patterns
status: active
created: 2026-08-28
source: facebook/react (Hamle 5)
tags: [react, fiber, reconciliation, rendering, performance]
---

# React Fiber Architecture

**Pattern:** Incremental Rendering and Scheduling

## The Problem (Pre-Fiber)

```
Stack-based reconciliation:
  1. Start rendering component tree
  2. Cannot pause (blocks main thread)
  3. Long trees = long frames = janky UI
  
Example:
  Render 1000 components = 16ms frame budget exceeded
  Result: 60fps → 30fps (scrolling stutters)
```

## Fiber Solution

```
Fiber = work unit (single component or element)
Scheduler = prioritizes which fiber to work on next

Execution:
  1. Work on one fiber (milliseconds)
  2. Check: did higher-priority work arrive? (user input)
  3. If yes: pause, handle input, resume later
  4. If no: continue to next fiber
```

## Fiber Phases

```
Render Phase (pausable):
  ├─ beginWork (component's constructor/hooks)
  ├─ processUpdateQueue (state updates)
  └─ completeWork (reconciliation, no DOM changes yet)

Commit Phase (non-pausable):
  ├─ DOM mutations
  ├─ Lifecycle methods (componentDidMount, useLayoutEffect)
  └─ Effects scheduling (useEffect)
```

## Performance Implications

```javascript
// ❌ Large tree renders at once
function ExpensiveComponent() {
  return (
    <div>
      {Array.from({ length: 1000 }, (_, i) => (
        <Item key={i} data={hugeProp} />  // Re-renders all 1000
      ))}
    </div>
  )
}

// ✓ Break into suspendable chunks
function VirtualizedList() {
  const [visible, setVisible] = useState(0)
  const scrollHandler = () => setVisible(prev => prev + 50)
  
  return (
    <div onScroll={scrollHandler}>
      {Array.from({ length: visible }, (_, i) => (
        <Item key={i} data={data[i]} />
      ))}
    </div>
  )
}
```

## Fiber Priority Levels

```
1. Immediate (events like clicks)
2. User-blocking (animations)
3. Normal (data fetching)
4. Low (Suspense fallbacks)
5. Idle (prefetching)

Scheduler queues work by priority:
  High-priority work → interrupt low-priority work
  Low-priority work → resumes when free
```

## Optimization: useDeferredValue

```javascript
import { useDeferredValue } from 'react'

function SearchResults() {
  const [query, setQuery] = useState('')
  const deferredQuery = useDeferredValue(query)
  
  // Typing updates UI instantly (high priority)
  // Filtering results updates async (low priority)
  const results = useMemo(
    () => filter(allItems, deferredQuery),
    [deferredQuery]
  )
  
  return (
    <>
      <input
        value={query}
        onChange={e => setQuery(e.target.value)}
      />
      {results.map(r => <Result key={r.id} item={r} />)}
    </>
  )
}
```

---

**Bağlantılar:** 
- [[hamle5-frontend-002-state-machines]] (predictable state)
- [[hamle5-performance-001-flame-graphs]] (profile render time)
- [[hamle5-performance-002-apm-instrumentation]] (trace React performance)
- [[hamle6-testing-001-test-pyramid]] (component testing)
