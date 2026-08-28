---
type: decision
title: Exactly-Once vs At-Least-Once Delivery Semantics
category: Messaging & Event Streaming
status: active
created: 2026-08-28
source: messaging-production-systems (Hamle 7)
tags: [messaging, kafka, rabbitmq, exactly-once, deduplication, reliability]
---

# Exactly-Once vs At-Least-Once Delivery

**Pattern:** Choosing reliability semantics based on cost/complexity tradeoff.

## The Problem

Balancing reliability with performance:
- **Exactly-once** = expensive, complex, but safe for financial transactions
- **At-least-once** = simple but requires idempotent consumers (can process duplicates)

## Kafka: Transactional Exactly-Once

```python
from kafka import KafkaProducer, KafkaConsumer
import time

# Producer: Exactly-once via idempotent sends
producer = KafkaProducer(
  enable_idempotence=True,  # De-duplicate at broker
  acks='all',               # Wait for all replicas
  retries=2147483647,       # Infinite retries
  max_in_flight_requests_per_connection=5  # Maintains ordering
)

# Consumer: Transactional reading + processing
consumer = KafkaConsumer(
  'orders',
  isolation_level='read_committed',  # Only read committed transactions
  group_id='order-processor'
)

for message in consumer:
  try:
    # Process (atomically with offset commit)
    order_id = message.value['id']
    price = message.value['amount']
    
    # Write to database in transaction
    db.begin_transaction()
    db.insert('processed_orders', {'order_id': order_id, 'price': price})
    db.commit()
    
    # Commit offset (only after DB commit succeeds)
    consumer.commit()
    
  except Exception as e:
    # Redelivery on failure; offset not committed
    log.error(f"Order processing failed: {e}; will retry")
```

## RabbitMQ: At-Least-Once (Application-Level Deduplication)

```python
import pika
import sqlite3

# RabbitMQ doesn't guarantee exactly-once natively
# Solution: application-level deduplication with unique message IDs

connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()
channel.basic_qos(prefetch_count=10)

def process_order(ch, method, properties, body):
  message_id = properties.message_id
  
  try:
    # Check if already processed
    db = sqlite3.connect(':memory:')
    cursor = db.cursor()
    cursor.execute('SELECT 1 FROM processed_messages WHERE id = ?', (message_id,))
    
    if cursor.fetchone():
      # Already processed; skip
      log.info(f"Duplicate message {message_id}; skipping")
      ch.basic_ack(delivery_tag=method.delivery_tag)
      return
    
    # Process new message
    order = json.loads(body)
    process_order_logic(order)
    
    # Record as processed
    cursor.execute('INSERT INTO processed_messages VALUES (?)', (message_id,))
    db.commit()
    
    # Acknowledge
    ch.basic_ack(delivery_tag=method.delivery_tag)
    
  except Exception as e:
    # Negative acknowledge; message requeued
    log.error(f"Order processing failed: {e}")
    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

channel.basic_consume(queue='orders', on_message_callback=process_order)
channel.start_consuming()
```

## Comparison

| Aspect | At-Least-Once | Exactly-Once |
|--------|--------------|--------------|
| **Simplicity** | Simple (ack/nack) | Complex (idempotence + dedup) |
| **Latency** | Low (1x processing) | High (2x: produce + idempotence check) |
| **Storage** | Queue only | Queue + dedup state |
| **Database Cost** | Cheaper (fewer writes) | Expensive (uniqueness checks) |
| **Use Case** | Logging, metrics | Payments, inventory |

## When to Use

**Exactly-Once:**
- ✓ Financial transactions (payment processing)
- ✓ Inventory updates (stock deductions)
- ✓ Account balance changes
- ✓ Legal audit trails (financial records)

**At-Least-Once:**
- ✓ Analytics events (duplicate counts acceptable)
- ✓ Logging (retries won't hurt)
- ✓ Metrics (eventual consistency okay)
- ✓ User notifications (duplicate okay)

## Production Gotchas

**1. Exactly-Once Latency Cost**
- Kafka transactional writes are 2-3x slower than non-transactional
- Deduplication checks add latency
- **Fix:** Reserve exactly-once for critical paths only; use at-least-once for bulk operations

**2. Duplicate Detection Requires Unique Message IDs**
- If producer doesn't set message ID, duplicates undetectable
- **Fix:** Enforce message IDs in producer schema; validate in consumer

**3. Deduplication State Must Outlive Transaction Window**
- If dedup DB loses records before consumer process, duplicates occur
- **Fix:** Persist dedup state durably; use distributed cache (Redis) with TTL > max retry window

**4. Offset Commit Race Condition (Kafka)**
- Process crashes after DB commit but before offset commit → message reprocessed
- **Fix:** Commit offset BEFORE closing transaction, or accept at-least-once

---

**Bağlantılar:**
- [[hamle6-system-003-saga-pattern]] (distributed transaction coordination)
- [[hamle6-security-004-rate-limiting-distributed]] (request deduplication)
- [[hamle6-testing-001-test-pyramid]] (testing idempotent handlers)
