---
type: decision
title: Query Execution Plans - Understanding PostgreSQL Performance
category: Database Architecture & Optimization
status: active
created: 2026-08-28
source: postgres/postgres (Hamle 5)
tags: [postgresql, query-optimization, execution-plan, performance, explain]
---

# Understanding Query Execution Plans

**Pattern:** Reading and Optimizing PostgreSQL Plans

## EXPLAIN Basics

```sql
-- Get query plan WITHOUT executing
EXPLAIN
SELECT * FROM users WHERE id = 1;

-- Output:
-- Seq Scan on users  (cost=0.00..35.50 rows=1)
--   Filter: (id = 1)

-- With execution stats
EXPLAIN ANALYZE
SELECT * FROM users WHERE id = 1;

-- Execution time: 0.123 ms
```

## Plan Node Types

```
Seq Scan:       Full table scan (slow for large tables)
Index Scan:     Use index to find rows (fast)
Bitmap Scan:    Multiple indexes combined
Hash Join:      Join using hash table (fast)
Nested Loop:    For each row, scan other table (slow)
Sort:           Order results (expensive!)
Aggregate:      COUNT, SUM, etc
```

## Common Problem: Missing Index

```sql
-- ❌ Slow query
EXPLAIN ANALYZE
SELECT * FROM orders WHERE user_id = 123 AND status = 'pending';

-- Seq Scan on orders (cost=0.00..450.00 rows=50)
--   Filter: user_id = 123 AND status = 'pending'
-- Execution time: 45ms

-- Add index
CREATE INDEX idx_orders_user_status ON orders(user_id, status);

-- ✓ Fast query
EXPLAIN ANALYZE
SELECT * FROM orders WHERE user_id = 123 AND status = 'pending';

-- Bitmap Index Scan (cost=2.50..45.00 rows=50)
-- Execution time: 0.5ms
```

## Reading Cost Estimates

```
cost=startup..end rows=estimated_count

Example:
  cost=0.00..35.50 rows=1
  
  startup: 0.00 (no startup cost)
  end: 35.50 (total cost estimate)
  rows: 1 (estimated rows returned)
  
Rule of thumb:
  If cost > 1000 → likely too slow
  If actual rows >> estimated → index not selective enough
```

## Join Performance

```sql
-- ❌ Nested loop (slow for large inner table)
Nested Loop Join (cost=0.00..500.00)
  -> Seq Scan on users (cost=0.00..100.00 rows=1000)
  -> Seq Scan on orders (cost=0.00..50.00 rows=50)
-- For each of 1000 users, scan 50 orders = 50,000 scans!

-- ✓ Hash join (fast for large tables)
Hash Join (cost=100.00..200.00)
  -> Seq Scan on users (cost=0.00..100.00 rows=1000)
  -> Hash (cost=50.00..50.00 rows=50)
       -> Seq Scan on orders (cost=0.00..50.00 rows=50)
-- Load orders into hash table once, lookup per user
```

## Tuning Parameters

```sql
-- If too many seq scans, increase this
SET random_page_cost = 1.0; -- SSD (was 4.0 default)

-- Force planner to avoid seq scans
SET seq_page_cost = 1.0;

-- Increase work memory for large sorts
SET work_mem = '256MB';

-- Query optimization hints
SET enable_seqscan = off; -- Force index use (debug only)
```

## Optimization Checklist

```
1. EXPLAIN ANALYZE (see actual vs estimated)
2. Look for: Seq Scan, Nested Loop, Sort
3. Add index on WHERE clause columns
4. Add index on JOIN columns
5. Recheck with EXPLAIN ANALYZE
6. Verify cost reduced and rows accurate
```

---

**Bağlantılar:** [[hamle5-database-002-indexing-strategy]]
