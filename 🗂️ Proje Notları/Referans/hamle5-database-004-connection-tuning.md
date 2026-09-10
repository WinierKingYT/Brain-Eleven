---
type: decision
title: PostgreSQL Connection Tuning - max_connections and Shared Buffers
category: Database Architecture & Optimization
status: active
created: 2026-08-28
source: postgres/postgres (Hamle 5)
tags: [postgresql, tuning, connections, performance, configuration]
---

# PostgreSQL Configuration Tuning

**Pattern:** Optimizing for Concurrent Connections

## Key Parameters

```ini
# postgresql.conf

# 1. Connections
max_connections = 200              # Total simultaneous connections
superuser_reserved_connections = 5 # Reserved for admin

# 2. Memory
shared_buffers = 25% of RAM        # Database cache
  Calculation: If 16GB RAM → shared_buffers = 4GB
  Note: Exceeding 25% has diminishing returns

work_mem = RAM / (max_connections × 2)
  Calculation: 16GB RAM, 200 connections
  work_mem = 16000MB / (200 × 2) = 40MB

maintenance_work_mem = RAM / 4
  For VACUUM, CREATE INDEX
```

## Connection Settings

```ini
# max_connections (most important)
# Each connection = ~5-10MB memory

Rule:
  max_connections = (app_connections) + (monitoring) + (backups)
  
Example:
  - App pool: 50 connections
  - Monitoring/dashboards: 20
  - Backup/maintenance: 10
  - Reserved: 5
  Total: 85 (set to 100-120)

Don't go too high!
  Excessive connections = OS thrashing
  CPU context switching overhead
```

## Shared Buffers

```ini
# Database page cache (like OS page cache but inside DB)

# Large shared_buffers:
  ✓ Frequently accessed pages cached
  ✓ Fewer disk reads
  ✗ Takes memory from OS
  ✗ Duplicate caching (OS + DB)

Recommendation: 25% of system RAM
  - 8GB system → 2GB shared_buffers
  - 64GB system → 16GB shared_buffers
  
Don't set too high (>40% has diminishing returns)
```

## Work Memory

```ini
# Per-operation memory (sorts, joins, hash tables)

Too low:
  ❌ Sorts spill to disk (10-100x slower)
  ❌ Hash tables degrade

Too high:
  ❌ Memory exhaustion with many concurrent queries
  
Calculation: Total RAM / (max_connections × 2)
  - 16GB RAM, 200 connections → 40MB per connection
  - 64GB RAM, 100 connections → 320MB per connection

Test: Increase until sorts no longer spill to disk
```

## Monitoring Connections

```sql
-- Current connections
SELECT datname, usename, count(*) 
FROM pg_stat_activity 
GROUP BY datname, usename;

-- Unused idle connections (close these)
SELECT pid, usename, state, query_start
FROM pg_stat_activity 
WHERE state = 'idle' AND query_start < NOW() - INTERVAL '1 hour';

-- Long-running queries
SELECT pid, usename, query, query_start,
       EXTRACT(EPOCH FROM (NOW() - query_start)) as duration_sec
FROM pg_stat_activity 
WHERE query NOT LIKE 'autovacuum%' 
ORDER BY duration_sec DESC;

-- Kill idle connection
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity 
WHERE usename = 'app' AND state = 'idle' 
  AND query_start < NOW() - INTERVAL '30 minutes';
```

## Reload Configuration

```bash
# Reload without restart (some parameters only)
sudo systemctl reload postgresql

# Or in psql
SELECT pg_reload_conf();

# Note: max_connections requires restart
sudo systemctl restart postgresql
```

---

**Bağlantılar:** [[hamle5-cloud-001-infrastructure-as-code]]
