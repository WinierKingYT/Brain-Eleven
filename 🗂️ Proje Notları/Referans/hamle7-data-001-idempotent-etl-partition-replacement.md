---
type: decision
title: Idempotent ETL - Partition Replacement Pattern
category: Data Engineering & ETL
status: active
created: 2026-08-28
source: data-engineering-production-systems (Hamle 7)
tags: [etl, data-engineering, idempotency, partition, exactly-once, transactional]
---

# Idempotent ETL via Partition Replacement

**Pattern:** Safe rerunning of pipelines with exactly-once semantics for time-windowed data.

## The Problem

Rerunning failed ETL jobs causes duplicate data or leaves state inconsistent. Recovery from mid-pipeline failures is risky:
- Partial inserts contaminate downstream joins
- Deduplication overhead doesn't justify complexity
- Time windows make it hard to identify what failed

## Solution: Delete + Insert Atomicity

For time-windowed data (daily/hourly partitions), use atomic transactions:

```sql
-- Single transaction: delete entire partition, reload fresh
BEGIN TRANSACTION
  DELETE FROM events WHERE DATE(event_time) = '2026-08-28'
  INSERT INTO events 
    SELECT * FROM staging_events 
    WHERE DATE(event_time) = '2026-08-28'
COMMIT
```

**Why this works:**
- Atomic: all-or-nothing guarantees no incomplete state
- Idempotent: rerunning same partition is safe (overwrites old data)
- Simple: no deduplication logic needed
- Exactly-once: no duplicates from retries

## Production Example: Airflow Backfill

```python
# airflow DAG: parameterized by date
@dag(schedule_interval='@daily')
def etl_pipeline():
  @task
  def load_daily_partition(execution_date):
    date_str = execution_date.strftime('%Y-%m-%d')
    
    # Staging: transform raw data
    staging_query = f"""
      SELECT event_id, event_time, user_id, action
      FROM raw_events 
      WHERE DATE(event_time) = '{date_str}'
      ORDER BY event_time
    """
    
    # Atomic swap
    db.execute(f"DELETE FROM events WHERE DATE(event_time) = '{date_str}'")
    db.execute(f"INSERT INTO events {staging_query}")
    db.commit()
```

**Backfill (reprocess 30 days):**
```bash
airflow dags backfill etl_pipeline -s 2026-07-29 -e 2026-08-28
# Triggers one task per day; each task re-deletes and re-inserts its partition
# Safe to rerun; overwrites broken data
```

## When to Use

✓ **Daily/hourly batch jobs** with clear time windows
✓ **Analytical warehouses** (Snowflake, BigQuery) with partitioned tables
✓ **SLA-critical loads** where duplicates are unacceptable (financial, inventory)
✓ **Bug fixes** requiring historical re-processing

✗ **Append-only logs** (no natural partition boundary)
✗ **Stream processing** (no clear daily windows)
✗ **Systems without transaction support**

## Production Gotchas

**1. Long-Running Deletes Lock Tables**
- For 100M+ rows, DELETE + INSERT can take 1hr+ and lock entire table
- **Fix:** Use staging table + atomic RENAME (zero-downtime swap)

```sql
-- Step 1: build complete new partition in staging
CREATE TABLE events_staging_20260828 AS
  SELECT * FROM events WHERE DATE(event_time) = '2026-08-28'
  UNION ALL
  SELECT * FROM staging_events WHERE DATE(event_time) = '2026-08-28'

-- Step 2: atomic swap (milliseconds)
ALTER TABLE events EXCHANGE PARTITION (date='2026-08-28')
  WITH TABLE events_staging_20260828
```

**2. Concurrent Backfills Cause Lock Contention**
- Two parallel processes trying to DELETE/INSERT same partition → deadlock
- **Fix:** Serialize backfills with mutex or separate staging tables per backfill

**3. Late-Arriving Data Not Included**
- Upstream systems may send data 24-48 hours late
- If backfill runs at 2am but late data arrives at 11am, it won't be included
- **Fix:** Coordinate with upstream SLAs; use cutoff timestamps, not just dates

**4. Duplicate Alerts if Monitoring Uses Absolute Thresholds**
- Backfill re-counts records; alerts fire if daily_event_count > threshold
- **Fix:** Use deltas or percent-change alerting, not absolute thresholds

## Comparison to Alternatives

| Approach | Simplicity | Idempotency | Dedup Overhead | Failure Recovery |
|----------|-----------|------------|-----------------|------------------|
| **Partition Replacement** | Simple SQL | Perfect | None | Rerun entire partition |
| **Incremental + Dedup** | Complex | Requires dedup logic | High (hash checks) | Rerun, skip inserted rows |
| **Event Sourcing** | Very complex | Perfect | None (immutable log) | Replay from offset |
| **Append-Only + Dedupe View** | Medium | Good (view dedupes) | Medium | Rerun, fix view logic |

---

**Bağlantılar:**
- [[hamle6-system-001-event-sourcing]] (immutable event log alternative)
- [[hamle5-database-003-transaction-isolation]] (ACID guarantees)
- [[hamle6-testing-001-test-pyramid]] (testing idempotent pipelines)
- [[hamle5-backend-001-event-loop-optimization]] (async batch processing)
