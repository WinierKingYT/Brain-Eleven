---
type: decision
title: Connection Pooling - Strategic Resource Management
category: Backend Patterns & Architecture
status: active
created: 2026-08-28
source: brettwooldridge/HikariCP (Hamle 5)
tags: [connection-pooling, database, resource-management, performance]
---

# Connection Pooling Architecture

**Pattern:** Efficient Database Connection Lifecycle Management

## The Problem

```
Without pooling:
  Each request → new connection → expensive handshake → query → close
  
Cost per connection:
  - TCP handshake: 1-5ms
  - SSL/TLS negotiation: 5-20ms
  - Auth validation: 2-5ms
  Total: 8-30ms per request × 1000 req/sec = 8-30 seconds wasted

With pooling:
  Pool maintains N ready connections
  Request grabs available connection → query → returns to pool
  Cost: <1ms (just lock contention)
```

## Connection Pool Parameters

```
pool_size = (core_count × 2) + spare_disk_connections

Example: 4-core server
  Recommended: (4 × 2) + 2 = 10 connections
  
Why not unlimited?
  - Each connection = memory (200-300KB)
  - Each connection = thread state
  - Idle connections consume OS resources
```

## HikariCP Best Practices (Industry Standard)

```java
HikariConfig config = new HikariConfig();
config.setJdbcUrl("jdbc:postgresql://localhost/db");
config.setUsername("user");
config.setPassword("pass");

// Connection lifecycle
config.setMaximumPoolSize(10);           // Max connections
config.setMinimumIdle(5);                // Min idle connections
config.setIdleTimeout(600000);           // 10 min idle timeout
config.setConnectionTimeout(30000);      // 30s acquisition timeout
config.setLeakDetectionThreshold(60000); // 60s leak detection

// Query timeout
config.setConnectionTestQuery("SELECT 1");
config.setValidationTimeout(5000);

HikariDataSource ds = new HikariDataSource(config);
```

## Common Pitfalls

```
❌ Pool too small
  queue_time increases → requests timeout → cascading failures

❌ Pool too large
  Slow response time (more scheduling overhead)
  Memory pressure (each connection is 200-300KB)

❌ No connection timeout
  Waiting connections hang forever
  Resource exhaustion

❌ No idle timeout
  Dead connections stay pooled (DB restarts)
  Application can't recover

✓ Monitor: active, idle, pending, timeout count
✓ Alert: idle < min_size (connection churn)
✓ Alert: pending > 5 (pool saturation)
```

## Monitoring Connection Pool Health

```
Metrics to track:
  - Active connections (gauge)
  - Idle connections (gauge)
  - Pending requests (gauge)
  - Acquired time (histogram, p99)
  - Timeout count (counter)
  - Connection errors (counter)

Alert thresholds:
  IF active == max_size AND pending > 0:
    ALERT "Pool exhausted" → investigate slow queries
    
  IF idle < min_size:
    ALERT "Connection churn" → check for connection leaks
```

---

**Bağlantılar:** [[hamle5-backend-003-graceful-shutdown]]
