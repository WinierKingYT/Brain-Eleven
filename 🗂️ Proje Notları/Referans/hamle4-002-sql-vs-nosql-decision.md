---
type: decision
title: SQL vs NoSQL - Decision Tree
category: Architecture & API Design
status: active
created: 2026-08-27
source: microsoft/api-guidelines (Hamle 4)
tags: [architecture, database, sql, nosql, data-modeling]
---

# SQL vs NoSQL Decision

**Pattern:** Database Selection Framework

## Karar Ağacı

```
Start: Veri modellemen nedir?

1. Relationships önemli mi? (Foreign keys, JOINs)
   ✓ YES → SQL (PostgreSQL, MySQL)
   ✗ NO → Continue

2. Schema fixed (tüm records aynı structure)?
   ✓ YES → SQL
   ✗ NO → Document DB (MongoDB)

3. Yazma throughput çok mu yüksek? (100k+ writes/sec)
   ✓ YES → NoSQL (Cassandra, DynamoDB)
   ✗ NO → SQL OK

4. Time-series data mı? (metrics, logs, events)
   ✓ YES → Time-series DB (InfluxDB, TimescaleDB)
   ✗ NO → Above tree follow

5. Full-text search gerekli?
   ✓ YES → Elasticsearch
   ✗ NO → Continue
```

## Hybrid Approach (Polyglot)

```
Microservice Architecture:
- User Service → PostgreSQL (relational)
- Product Catalog → MongoDB (flexible schema)
- Analytics → Elasticsearch (full-text)
- Metrics → InfluxDB (time-series)
- Cache → Redis (speed)
- Queueing → Kafka (messaging)
```

## SQL Seç Eğer

- ✓ Complex transactions (banking, orders)
- ✓ Data integrity critical (ACID)
- ✓ Multiple tables JOIN
- ✓ Changing requirements (flexible schema evolution)

## NoSQL Seç Eğer

- ✓ Massive scale (100M+ documents)
- ✓ Unstructured data (logs, JSON)
- ✓ Horizontal partitioning critical
- ✓ Schema evolution rapid

---

**Bağlantılar:** [[hamle4-001-caching-strategy]]
