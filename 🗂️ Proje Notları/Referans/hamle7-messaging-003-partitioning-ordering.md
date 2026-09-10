---
type: decision
title: Partitioning Strategy for Ordering & Parallelism
category: Messaging & Event Streaming
status: active
created: 2026-08-28
source: messaging-production-systems (Hamle 7)
tags: [kafka, partitioning, ordering, throughput, scale]
---

# Partitioning Strategy for Ordering & Parallelism

**Pattern:** Choosing partition keys to balance message ordering with throughput.

## The Problem

Partition key determines:
- **Ordering**: messages with same key stay in order
- **Throughput**: messages spread across partitions for parallel processing
- **Hotspots**: unbalanced keys cause one partition to receive all traffic

## Solution: Partition by Entity ID

```python
from kafka import KafkaProducer
import json

producer = KafkaProducer(bootstrap_servers=['kafka:9092'])

# E-commerce: partition by order_id (all updates for one order stay ordered)
for event in event_stream:
  message = json.dumps({
    'order_id': event['order_id'],
    'action': event['action'],  # 'created', 'paid', 'shipped'
    'timestamp': event['timestamp']
  })
  
  # Key determines partition: hash(order_id) % num_partitions
  producer.send('orders', key=event['order_id'].encode(), value=message)
```

**Result: Ordering Guarantee**
```
Order 1 events → Partition 0: created → paid → shipped (ordered)
Order 2 events → Partition 1: created → paid (ordered)
Order 3 events → Partition 2: paid → shipped (ordered)

All orders process in parallel; within-order ordering preserved.
```

## Detecting Hotspot Partitions

```python
from kafka.admin import KafkaAdminClient, ConfigResource, ConfigResourceType

admin = KafkaAdminClient(bootstrap_servers=['kafka:9092'])

# Check partition sizes
def check_partition_balance():
  for partition in admin.describe_topics()['orders']:
    size_bytes = get_partition_size(partition)
    if size_bytes > average_size * 2:  # >2x average
      log.warning(f"Hotspot detected: partition {partition.number} = {size_bytes} bytes")
```

## Preventing Hotspots: Multi-Level Partitioning

```python
# Problem: All sales go to partition 0 (hotspot)
# Solution: Composite key (region + order_id)

message = json.dumps({
  'region': 'US-WEST',
  'order_id': event['order_id'],
  'sales': event['sales']
})

# Key now uses both: hash(f"{region}:{order_id}") → better distribution
producer.send('orders', key=f"{region}:{order_id}".encode(), value=message)
```

## Trade-offs: Keyless (Round-Robin) vs Keyed

| Aspect | Keyed (by order_id) | Keyless (round-robin) |
|--------|-------------------|-----------------------|
| **Ordering** | Per-key ordered | No ordering |
| **Parallelism** | Across keys | Within key |
| **Hotspots** | Possible | Balanced |
| **Use Case** | Orders, state changes | Metrics, logs |

## Rebalancing Partitions (Advanced)

```bash
# Problem: Started with 5 partitions; now need 20
# Warning: Can only ADD partitions, not remove; causes rebalancing

# Add partitions
kafka-topics.sh --bootstrap-server kafka:9092 \
  --alter --topic orders --partitions 20

# Old consumers re-partition:
# Consumer 0 had [0-3] → now has [0, 10]  (distributed across larger space)
```

## When to Use

✓ **Distributed systems** needing per-entity ordering (orders, payments, user actions)
✓ **Event sourcing** (all events for one aggregate in order)
✓ **Stateful stream processing** (join events by entity ID)

✗ **High-cardinality keys** (user_id with billions of unique IDs → hotspots)
✗ **Broadcast events** (metrics, logs; no specific order requirement)

## Production Gotchas

**1. Unbalanced Partition Key Distribution**
- 80% of orders from top 5 customers → 1 partition gets 80% traffic
- **Fix:** Ensure key has uniform distribution; add composite key (customer_id + timestamp) for better spread

**2. Partition Count Cannot Decrease**
- Scaled up to 50 partitions; now need only 5; can't reduce
- **Fix:** Migrate to new topic with fewer partitions (expensive)

**3. Key-based Ordering Requires Single Consumer Per Partition**
- Multiple consumers on same partition = ordering violated
- **Fix:** Ensure consumer_count ≤ partition_count; use share groups (new feature)

**4. Rebalancing After Partition Addition**
- Adding partitions triggers full rebalance; brief lag spike
- **Fix:** Plan scaling off-peak; use sticky assignment to minimize disruption

---

**Bağlantılar:**
- [[hamle7-messaging-002-consumer-group-rebalancing]] (partition assignment strategies)
- [[hamle6-system-003-saga-pattern]] (ordering in distributed transactions)
- [[hamle6-devops-001-structured-logging-json]] (partition metrics monitoring)
