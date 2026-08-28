---
type: decision
title: Render Optimization - Memoization and Reconciliation
category: Frontend Performance & Patterns
status: active
created: 2026-08-28
source: facebook/react (Hamle 5)
tags: [react, memoization, rendering, performance, memo]
---

# Advanced Render Optimization

**Pattern:** Preventing Unnecessary Re-renders

## The Problem

```javascript
// ❌ All children re-render when parent updates
function Parent() {
  const [count, setCount] = useState(0)
  
  return (
    <>
      <button onClick={() => setCount(c => c + 1)}>Count: {count}</button>
      <ExpensiveChild /> {/* Re-renders even though props didn't change */}
    </>
  )
}

Performance: 100ms per render × 10 children = 1000ms (frame budget exceeded)
```

## Solution 1: React.memo

```javascript
// ✓ Skip re-render if props same
const ExpensiveChild = React.memo(({ id, name }) => {
  console.log('ExpensiveChild rendered')
  return <div>Expensive computation...</div>
})

// Only re-renders if `id` or `name` changes
<ExpensiveChild id={userId} name={userName} />
```

## Solution 2: useMemo for Derived State

```javascript
function DataProcessor({ data }) {
  // ❌ Recalculated on every render
  const sorted = data.sort((a, b) => a - b)
  
  // ✓ Only recalculated when `data` changes
  const sorted = useMemo(() => 
    data.sort((a, b) => a - b),
    [data]
  )
  
  return <List items={sorted} />
}
```

## Solution 3: useCallback for Stable Functions

```javascript
// ❌ New function reference every render
function Parent() {
  const handleClick = () => { /* ... */ }
  return <ExpensiveChild onClick={handleClick} />
}

// ✓ Stable function reference
function Parent() {
  const handleClick = useCallback(() => {
    // ...
  }, [/* dependencies */])
  
  return <ExpensiveChild onClick={handleClick} />
}
```

## Solution 4: Virtualization for Large Lists

```javascript
import { FixedSizeList } from 'react-window'

function LargeList({ items }) {
  // ❌ Render all 10,000 items (DOM nodes)
  // <div>{items.map(i => <Item key={i} />)}</div>
  
  // ✓ Render only visible 20 items
  return (
    <FixedSizeList
      height={600}
      itemCount={items.length}
      itemSize={35}
    >
      {({ index, style }) => (
        <div style={style}>
          <Item data={items[index]} />
        </div>
      )}
    </FixedSizeList>
  )
}
```

## Profiling with React DevTools

```
React DevTools → Profiler tab:

1. Start recording
2. Interact with app
3. Stop recording
4. View:
   - Render time per component
   - Why component re-rendered
   - Props changes
```

## When to Optimize

```
❌ Too early (premature optimization)
  Don't memo everything

✓ Profile first
  Find actual bottlenecks
  Apply optimization only there

Example:
  Render time: 1ms → memo saves 0.8ms (not worth)
  Render time: 100ms → memo saves 95ms (worth it!)
```

---

**Bağlantılar:** [[hamle5-database-001-query-plans]]
