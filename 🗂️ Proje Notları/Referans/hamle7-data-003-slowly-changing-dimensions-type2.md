---
type: decision
title: Slowly Changing Dimensions - Type 2 (Full History Tracking)
category: Data Engineering & Dimensional Modeling
status: active
created: 2026-08-28
source: data-engineering-production-systems (Hamle 7)
tags: [dimensional-modeling, scd-type2, temporal, data-warehouse, audit-trail]
---

# Slowly Changing Dimensions Type 2

**Pattern:** Track complete history of dimension changes while maintaining efficient queries on current state.

## The Problem

Analytical queries need temporal context: *"What was the customer's status when they made this purchase?"*

Without Type 2:
- Old approach overwrites status → lose history
- Can't answer: "How many active customers on 2026-01-01?"
- Audit trails missing

## Solution: Effective/Expiry Date Columns

Track both historical and current state via date ranges:

```sql
-- Customer dimension with Type 2 tracking
CREATE TABLE dim_customer (
  customer_id INT,
  customer_name VARCHAR(100),
  status VARCHAR(20),  -- 'active', 'inactive', 'churned'
  effective_date DATE,  -- when change became active
  expiry_date DATE,     -- when superseded by new row (NULL = current)
  is_current BOOLEAN,   -- flag for quick filtering
  PRIMARY KEY (customer_id, effective_date)
);

-- Initial load (2026-01-01)
INSERT INTO dim_customer VALUES 
  (1, 'Acme Corp', 'active', '2026-01-01', NULL, true),
  (2, 'Beta Inc', 'active', '2026-01-01', NULL, true);

-- On 2026-06-15: Acme downgrades to 'inactive'
BEGIN TRANSACTION
  -- Expire old record
  UPDATE dim_customer 
  SET expiry_date = '2026-06-14', is_current = false
  WHERE customer_id = 1 AND is_current = true;
  
  -- Insert new record
  INSERT INTO dim_customer VALUES
    (1, 'Acme Corp', 'inactive', '2026-06-15', NULL, true);
COMMIT;
```

## Querying: Point-in-Time Analysis

```sql
-- What was status of each customer on 2026-03-15?
SELECT customer_id, status
FROM dim_customer
WHERE '2026-03-15' BETWEEN effective_date AND COALESCE(expiry_date, CURRENT_DATE);

-- Current status (fast path)
SELECT customer_id, status
FROM dim_customer
WHERE is_current = true;  -- or WHERE expiry_date IS NULL

-- History of Acme Corp
SELECT effective_date, expiry_date, status
FROM dim_customer
WHERE customer_id = 1
ORDER BY effective_date;
```

## Production Pattern: Merge-Based CDC

```python
# Incrementally load customer changes
source_data = spark.read.format("csv").load("s3://customer-updates/")

# MERGE handles SCD Type 2 automatically
spark.sql("""
MERGE INTO dim_customer d
USING source_data s
ON d.customer_id = s.customer_id AND d.is_current = true
WHEN MATCHED AND s.status != d.status THEN
  UPDATE SET expiry_date = current_date - 1, is_current = false
  -- Insert new row in separate step (MERGE doesn't INSERT matched + old rows)
WHEN NOT MATCHED THEN
  INSERT (customer_id, customer_name, status, effective_date, expiry_date, is_current)
  VALUES (s.customer_id, s.name, s.status, current_date, NULL, true)
""")

# Insert new versions for changed records
changed = spark.sql("SELECT * FROM source_data s WHERE EXISTS (SELECT 1 FROM dim_customer d WHERE d.customer_id = s.customer_id AND d.status != s.status)")
changed.write.insertInto("dim_customer")
```

## When to Use

✓ **Customer, product, geography dimensions** (changes frequently)
✓ **Audit trails & compliance** (GDPR, SOX require history)
✓ **Temporal analysis** ("How many active in each month?")
✓ **Customer 360** (full history of status changes)

✗ **High-velocity streams** (real-time Type 2 is expensive)
✗ **Dimensions with 1000+ attribute changes/day** (storage explodes)

## Production Gotchas

**1. Queries Forget `WHERE is_current = true`**
- Query joins old + new records → 2x result size
- **Fix:** Create view filtering `is_current = true` as default; require explicit `IGNORE CURRENT` to see history

**2. Storage Doubles/Triples with Complete History**
- Acme Corp with 50 status changes = 50 rows in dim_customer
- **Fix:** Partition table by `effective_date`; archive old partitions to cold storage after 7 years

**3. Hash Collisions Create False Updates**
- Small random fluctuation triggers new row even though status didn't actually change
- **Fix:** Validate changes with strict logic; compare actual business fields, not raw data

**4. Late-Arriving Dimension Updates**
- Status change at 2026-06-15 arrives at 2026-06-17
- Dates are wrong; historical queries give wrong results
- **Fix:** Use event timestamp (when change occurred) not insertion timestamp; handle late arrivals via `UPDATE` on expiry_date

---

**Bağlantılar:**
- [[hamle6-system-001-event-sourcing]] (immutable event log for audit)
- [[hamle5-database-003-transaction-isolation]] (transactional consistency)
- [[hamle6-testing-001-test-pyramid]] (testing temporal queries)
