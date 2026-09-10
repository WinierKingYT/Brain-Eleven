---
type: decision
title: State Machines - Predictable UI State Management
category: Frontend Performance & Patterns
status: active
created: 2026-08-28
source: statelyai/xstate (Hamle 5)
tags: [state-machines, xstate, state-management, fsm, reliability]
---

# Finite State Machines for UI

**Pattern:** Eliminating Impossible States

## Traditional useState Problems

```javascript
// ❌ Possible impossible states
const [loading, setLoading] = useState(false)
const [error, setError] = useState(null)
const [data, setData] = useState(null)

// Bug: loading=true AND error="failed" (impossible)
// Bug: data exists AND loading=true (confusing)

// Human must enforce invariants:
if (loading) return <Spinner />
if (error) return <Error msg={error} />
if (data) return <Display data={data} />
```

## State Machine Approach

```javascript
import { createMachine, useMachine } from 'xstate'

const fetchMachine = createMachine({
  initial: 'idle',
  states: {
    idle: {
      on: { FETCH: 'loading' }
    },
    loading: {
      on: {
        SUCCESS: { target: 'success', actions: 'setData' },
        ERROR: { target: 'error', actions: 'setError' }
      }
    },
    success: {
      on: { RESET: 'idle' }
    },
    error: {
      on: { RETRY: 'loading', RESET: 'idle' }
    }
  }
}, {
  actions: {
    setData: (ctx, event) => { ctx.data = event.data },
    setError: (ctx, event) => { ctx.error = event.error }
  }
})

function DataFetcher() {
  const [state, send] = useMachine(fetchMachine)
  
  // Only valid states reachable!
  if (state.matches('idle')) return <button onClick={() => send('FETCH')}>Load</button>
  if (state.matches('loading')) return <Spinner />
  if (state.matches('success')) return <Display />
  if (state.matches('error')) return <Error />
}
```

## Guarded Transitions

```javascript
const loginMachine = createMachine({
  initial: 'form',
  states: {
    form: {
      on: {
        SUBMIT: [
          {
            target: 'validating',
            cond: ({ email }) => isValidEmail(email)
          },
          { target: 'formError' }
        ]
      }
    },
    validating: { ... },
    success: { ... },
    formError: { ... }
  }
})

// Only valid transitions allowed by condition
```

## Context (Data) vs State (Flow)

```
State: idle, loading, success, error (behavior)
Context: data, error, userId (values)

Separation of concerns:
  Machine defines transitions (what's possible)
  Context carries values (what's the data)
```

## Integration with React

```javascript
function UserProfile({ userId }) {
  const [state, send] = useMachine(profileMachine, {
    services: {
      fetchUser: () => api.getUser(userId)
    }
  })
  
  // state.matches('loading') → sending to API
  // state.context.user → loaded user data
  
  return (
    state.matches('loading') ? <Spinner /> :
    state.matches('success') ? <Profile user={state.context.user} /> :
    <Error error={state.context.error} />
  )
}
```

## Benefits

```
✓ Impossible states eliminated (compiler-enforced)
✓ All transitions visible in machine definition
✓ Testable logic (no UI, just state)
✓ Visual debugging (visualize.xstate.io)
✓ Prevents race conditions (serializes events)
```

---

**Bağlantılar:** [[hamle5-frontend-003-bundle-splitting]]
