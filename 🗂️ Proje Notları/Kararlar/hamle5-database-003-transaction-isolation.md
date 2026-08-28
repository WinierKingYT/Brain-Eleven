---
type: decision
title: Transaction Isolation Levels - Concurrency vs Consistency
category: Database Architecture & Optimization
status: active
created: 2026-08-28
source: postgres/postgres (Hamle 5)
tags: [postgresql, transactions, isolation, acid, concurrency]
---

# Transaction Isolation Levels

**Pattern:** Balancing Consistency and Performance

## The Four Levels

```
READ UNCOMMITTED  (weakest, fastest)
  ↓
READ COMMITTED
  ↓
REPEATABLE READ
  ↓
SERIALIZABLE      (strongest, slowest)
```

## Level 1: READ UNCOMMITTED (Fastest)

```sql
SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;

BEGIN;
  SELECT balance FROM accounts WHERE id = 1;  -- dirty read possible
COMMIT;

Problem: Transaction A reads uncommitted data from Transaction B
  → If B rolls back, A has stale data

Use case: Approximate counts, non-critical reports
```

## Level 2: READ COMMITTED (Default in PostgreSQL)

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

Transaction A:
  BEGIN;
  SELECT balance FROM accounts WHERE id = 1;  -- balance = $100
  -- Meanwhile, Transaction B updates it to $50
  SELECT balance FROM accounts WHERE id = 1;  -- balance = $50 (changed!)
  COMMIT;

Problem: Non-repeatable read (same query returns different results)

Use case: Most web applications (default)
```

## Level 3: REPEATABLE READ

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

Transaction A:
  BEGIN;
  SELECT balance FROM accounts WHERE id = 1;  -- balance = $100
  -- Meanwhile, Transaction B updates to $50 AND commits
  SELECT balance FROM accounts WHERE id = 1;  -- balance = $100 (snapshot)
  COMMIT;

Benefit: Consistent view within transaction

Problem: Phantom reads possible (new rows appear)
  SELECT COUNT(*) FROM accounts;  -- 10
  [Transaction B inserts row]
  SELECT COUNT(*) FROM accounts;  -- Still 10 (same snapshot)
```

## Level 4: SERIALIZABLE (Safest)

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

Guarantee: Transactions run as if executed serially (no concurrency conflicts)

Cost: 10-100x slower (conflicts detected, retried)

Use case: Financial transactions, inventory management
```

## PostgreSQL MVCC (Multi-Version Concurrency Control)

```
Transaction 1: SELECT → gets snapshot at time T1
Transaction 2: UPDATE (commits) → new version created
Transaction 1: SELECT → still sees snapshot at T1 (not T2's changes)

Benefit: Readers don't block writers, writers don't block readers
```

## Lost Update Problem

```javascript
// ❌ Unsafe without isolation
Account balance: $100

Transaction A:
  balance = SELECT balance FROM accounts  -- $100
  balance -= $50
  UPDATE accounts SET balance = balance  -- $50

Transaction B:
  balance = SELECT balance FROM accounts  -- $100
  balance += $25
  UPDATE accounts SET balance = balance  -- $125 (overwrote A's change!)

Final: $125 (should be $75!)

// ✓ Safe with proper locking
BEGIN;
  SELECT balance FROM accounts WHERE id = 1 FOR UPDATE;  -- lock row
  balance -= $50
  UPDATE accounts SET balance = balance
COMMIT;
```

## When to Use Each Level

```
READ COMMITTED:
  ✓ Default, fine for most apps
  ✓ Web applications, APIs

REPEATABLE READ:
  ✓ When same data read multiple times
  ✓ Reports, multi-step workflows

SERIALIZABLE:
  ✓ Financial transactions
  ✓ Inventory management
  ✓ High-value operations only
```

---

**Bağlantılar:** [[hamle5-database-004-connection-tuning]]
