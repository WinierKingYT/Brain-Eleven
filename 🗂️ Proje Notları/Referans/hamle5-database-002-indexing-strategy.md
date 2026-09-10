---
type: decision
title: Indexing Strategy - Composite vs Single Indexes
category: Database Architecture & Optimization
status: active
created: 2026-08-28
source: postgres/postgres (Hamle 5)
tags: [postgresql, indexing, query-optimization, btree, performance]
---

# Strategic Indexing

**Pattern:** Creating Efficient Composite Indexes

## Index Basics

```sql
-- Single index
CREATE INDEX idx_user_email ON users(email);

-- Query:
SELECT * FROM users WHERE email = 'test@example.com';
-- Uses idx_user_email (fast: O(log n))

-- Without index (full table scan):
SELECT * FROM users WHERE name = 'John';
-- Seq Scan (slow: O(n))
```

## Composite Index Rules

```sql
-- Composite index: (user_id, status, created_at)
CREATE INDEX idx_orders_lookup ON orders(user_id, status, created_at);

Rule: Column order in WHERE clause = index column order

✓ Good queries:
  WHERE user_id = 1
  WHERE user_id = 1 AND status = 'pending'
  WHERE user_id = 1 AND status = 'pending' AND created_at > '2024-01-01'

❌ Bad queries:
  WHERE status = 'pending' (skips user_id, can't use index efficiently)
  WHERE created_at = '2024-01-01' (skips user_id and status)
```

## Index Column Order Strategy

```
Rule: Equality → Range → Sort

Example: (user_id, status, created_at)
  Equality: user_id = 123     (narrows down)
  Range: status IN (...)      (filters results)
  Sort: created_at DESC       (orders remaining)

Result: Index traversal directly finds and sorts results
```

## Covering Indexes (Index-Only Scan)

```sql
-- Query needs: user_id, status, email
CREATE INDEX idx_users_covering ON users(user_id, status) INCLUDE (email);

Query:
  SELECT email FROM users WHERE user_id = 1 AND status = 'active';
  
Result: Index-Only Scan (no need to access table!)
```

## Common Anti-Patterns

```sql
-- ❌ Too many indexes (maintenance overhead)
CREATE INDEX idx_name ON users(name);
CREATE INDEX idx_email ON users(email);
CREATE INDEX idx_created ON users(created_at);
-- Insertion = 3 index updates

-- ✓ One composite index
CREATE INDEX idx_users_main ON users(email, name, created_at);

-- ❌ Indexing low-cardinality columns
CREATE INDEX idx_status ON orders(status);  -- Only 5 values!
-- Index less useful than full table scan

-- ✓ Combine with high-cardinality
CREATE INDEX idx_orders ON orders(user_id, status, created_at);
```

## Partial Indexes

```sql
-- Only index active users (saves space, improves performance)
CREATE INDEX idx_active_users ON users(id)
  WHERE status = 'active';

Query:
  SELECT * FROM users WHERE status = 'active' AND email = 'test@example.com';
  -- Uses partial index (smaller, faster)
```

## Maintenance

```sql
-- Find unused indexes
SELECT relname FROM pg_stat_user_indexes
WHERE idx_scan = 0;

-- Remove unused
DROP INDEX idx_old_lookup;

-- Reindex (optimize)
REINDEX INDEX idx_users_main;

-- Check bloat
VACUUM ANALYZE users;
```

---

**Bağlantılar:** [[hamle5-database-003-transaction-isolation]]
