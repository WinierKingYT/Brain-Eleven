---
type: decision
title: Consumer Group Coordination & Rebalancing Strategy
category: Messaging & Event Streaming
status: active
created: 2026-08-28
source: messaging-production-systems (Hamle 7)
tags: [kafka, consumer-groups, rebalancing, coordination, scale]
---

# Consumer Group Coordination & Rebalancing

**Pattern:** Scaling consumers dynamically with minimal processing pause via rebalancing strategies.

## The Problem

When consumers join/leave a consumer group, partitions must be reassigned fairly:
- Adding consumer during peak = 30-90 second rebalancing pause
- Stop-the-world during rebalance = queries queue up
- False-failure rebalances due to timeout = thrashing

## Solution: Group Coordination + Rebalancing Strategies

```python
from kafka import KafkaConsumer
from kafka.structs import TopicPartition

# 1. Group Coordination (automatic)
consumer = KafkaConsumer(
  'orders',
  group_id='order-processors',
  bootstrap_servers=['kafka:9092'],
  
  # Rebalance strategy
  partition_assignment_strategy=['sticky'],  # Minimize partition movement
  
  # Heartbeat tuning (prevent false failures)
  session_timeout_ms=30000,      # Max 30s before member marked dead
  heartbeat_interval_ms=3000,    # Send heartbeat every 3s
  max_poll_interval_ms=300000,   # Max 5 min between polls
)

# 2. Graceful shutdown before rebalance
def shutdown_gracefully():
  # Drain in-flight messages
  consumer.pause()  # Stop fetching
  
  # Wait for current batch to finish
  for record in current_batch:
    process(record)
    consumer.commit()
  
  consumer.close()  # Trigger rebalance
  log.info("Gracefully shut down; partition reassigned to other consumers")

# 3. Rebalance listener for cleanup
def on_rebalance(partitions):
  if partitions.is_assigned():
    log.info(f"Rebalance assigned: {partitions}")
  else:
    log.info(f"Rebalance revoked: {partitions}; stopping processing")

consumer.subscribe(['orders'], on_partitions_revoked=on_rebalance)
```

## Rebalancing Strategies Comparison

| Strategy | Behavior | When to Use |
|----------|----------|------------|
| **Range** | Consumer 0 gets partitions [0-2], C1 gets [3-4] | Simple scenarios, predictable partition assignment |
| **Round-Robin** | Partitions distributed round-robin across consumers | Balanced load, better than range |
| **Sticky** | Minimizes partition movement on rebalance (keep C0→partitions if possible) | **Production: Recommended**; hot partition awareness |
| **Cooperative Sticky** | Incremental rebalancing (add C1 without revoking C0's partitions) | Zero stop-the-world; newer Kafka versions |

## Production: Sticky Strategy Example

```
Initial state (3 partitions, 2 consumers):
  C0: [P0, P1]
  C1: [P2]

Add C2:
  Range: C0: [P0], C1: [P1], C2: [P2]  (all reassigned = 100% movement)
  Sticky: C0: [P0], C1: [P1, P2], C2: []  (only P1 moved to C2 = 33% movement)
  Cooperative: C0: [P0, P2], C1: [P1], C2: []  (P2 stays with C0 during transition)
```

## Preventing False-Failure Rebalances

```python
# Problem: Long processing time triggers false rebalance
# Solution: Tune heartbeat + session timeout + poll interval

# Slow consumer (takes 10s to process)
for record in consumer:
  time.sleep(10)  # Process
  consumer.commit()

# Without tuning: heartbeat_interval=3s, session_timeout=30s
# After 10s processing, heartbeat not sent → broker marks consumer dead after 30s
# Rebalance triggered unnecessarily

# Fix: Increase timeouts
consumer = KafkaConsumer(
  session_timeout_ms=60000,      # Allow 60s of no heartbeat
  heartbeat_interval_ms=3000,    # Send heartbeat every 3s
  max_poll_interval_ms=120000,   # Allow 2 min between polls
)
```

## When to Use

✓ **Production Kafka clusters** (always use sticky)
✓ **Dynamic scaling** (add/remove consumers during traffic spikes)
✓ **Hot partitions** (sticky preserves local state across rebalance)

## Production Gotchas

**1. Rebalance Pause Causes Cascading Failures**
- 60-90 second pause → queries queue → timeout → downstream failures
- **Fix:** Implement circuit breaker on consumer lag; gracefully degrade if lag > threshold

**2. Session Timeout Too High**
- Failed consumer not detected for 30+ minutes
- **Fix:** Balance: session_timeout = 2-3x max processing time; too low causes thrashing

**3. Incremental Rebalancing Not Enabled by Default**
- Need Kafka 2.4+ and specific config
- **Fix:** `partition.assignment.strategy=cooperative-sticky` in broker config

**4. Heartbeat Loss = False Rebalance**
- Network hiccup → no heartbeat → rebalance (false alarm)
- **Fix:** Tune session_timeout based on network reliability; monitor rebalance metrics

---

**Bağlantılar:**
- [[hamle7-messaging-001-exactly-once-semantics]] (deduplication during rebalance)
- [[hamle6-system-003-saga-pattern]] (coordinating distributed consumers)
- [[hamle6-devops-001-structured-logging-json]] (tracking rebalance events)
