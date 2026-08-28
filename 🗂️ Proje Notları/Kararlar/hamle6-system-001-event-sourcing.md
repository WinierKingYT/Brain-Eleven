---
type: decision
title: Event Sourcing - Immutable Audit Trail & State Reconstruction
category: System Design Patterns
status: active
created: 2026-08-28
source: EventStoreDB & DDD Community (Hamle 6)
tags: [system-design, event-sourcing, audit, cqrs, distributed-systems]
---

# Event Sourcing Pattern

**Pattern:** Immutable Event Stream as Source of Truth

## Core Concept

```
Traditional CRUD:
  User table:
    { id: 1, name: 'Alice', status: 'active', balance: 100 }
  
  History: None (only current state)
  Issues: Can't see how we got here, can't audit changes, can't undo

Event Sourcing:
  Events (append-only log):
    1. UserCreated { userId: 1, name: 'Alice', email: 'alice@ex.com' }
    2. UserStatusChanged { userId: 1, status: 'active' }
    3. MoneyDeposited { userId: 1, amount: 100 }
    4. MoneyTransferred { userId: 1, toUserId: 2, amount: 30 }
  
  Current state (derived from events):
    { id: 1, name: 'Alice', status: 'active', balance: 70 }
  
  History: Complete audit trail
  Replay: Can reconstruct state at any point in time
```

## Implementation

```javascript
// Event store
class EventStore {
  constructor() {
    this.events = []
  }
  
  // Append-only: new events never overwrite
  append(aggregateId, event) {
    this.events.push({
      aggregateId,
      timestamp: new Date(),
      eventType: event.constructor.name,
      data: event,
      version: this.events.filter(e => e.aggregateId === aggregateId).length + 1
    })
  }
  
  // Get all events for an aggregate
  getEvents(aggregateId) {
    return this.events.filter(e => e.aggregateId === aggregateId)
  }
  
  // Reconstruct state at any point
  getStateAt(aggregateId, version) {
    const events = this.getEvents(aggregateId).slice(0, version)
    return this.rebuild(events)
  }
}

// Domain model
class User {
  constructor(id) {
    this.id = id
    this.name = null
    this.balance = 0
    this.status = 'inactive'
  }
  
  // Commands (intent)
  create(name, email) {
    this.applyEvent(new UserCreated(this.id, name, email))
  }
  
  deposit(amount) {
    this.applyEvent(new MoneyDeposited(this.id, amount))
  }
  
  transfer(toUserId, amount) {
    if (this.balance < amount) {
      throw new Error('Insufficient funds')
    }
    this.applyEvent(new MoneyTransferred(this.id, toUserId, amount))
  }
  
  // Events (what happened)
  applyEvent(event) {
    if (event instanceof UserCreated) {
      this.name = event.name
      this.status = 'active'
    } else if (event instanceof MoneyDeposited) {
      this.balance += event.amount
    } else if (event instanceof MoneyTransferred) {
      this.balance -= event.amount
    }
  }
  
  // Replay
  loadFromHistory(events) {
    events.forEach(e => this.applyEvent(e.data))
  }
}

// Usage
const eventStore = new EventStore()
const user = new User(1)

user.create('Alice', 'alice@ex.com')
eventStore.append(1, new UserCreated(1, 'Alice', 'alice@ex.com'))

user.deposit(100)
eventStore.append(1, new MoneyDeposited(1, 100))

// Reconstruct state at any point
const events = eventStore.getEvents(1)
const reconstructedUser = new User(1)
reconstructedUser.loadFromHistory(events)
console.log(reconstructedUser.balance)  // 100
```

## Snapshots (Performance)

```
Problem: Replaying 1 million events slow
Solution: Periodically save snapshots

// Take snapshot every 100 events
if (version % 100 === 0) {
  snapshots[aggregateId] = { version: 100, state: currentState }
}

// Load state: start from snapshot, replay rest
snapshot = snapshots[aggregateId]  // version 100
remainingEvents = getEvents(aggregateId, 100, 150)
state = rebuild(snapshot.state, remainingEvents)
```

## Temporal Queries

```
"Show me all transfers on 2024-01-15"
  Filter events: 
    WHERE eventType = 'MoneyTransferred'
    AND timestamp LIKE '2024-01-15%'

"How much did user 1 have on 2024-01-10?"
  Replay events until 2024-01-10
  Return balance

"Who changed user status most frequently?"
  GROUP BY userId
  WHERE eventType = 'UserStatusChanged'
  ORDER BY COUNT DESC
```

## Event Versioning

```
Event schema evolves, old events still in store

Event v1:
  { type: 'Deposit', amount: 100 }

Event v2 (new field):
  { type: 'Deposit', amount: 100, accountType: 'checking' }

Handling v1 events:
  {
    type: 'Deposit',
    version: 1,
    apply(state) {
      state.balance += this.amount
      state.accountType = state.accountType || 'default'
    }
  }
```

---

**Bağlantılar:** [[hamle6-system-002-cqrs]]
