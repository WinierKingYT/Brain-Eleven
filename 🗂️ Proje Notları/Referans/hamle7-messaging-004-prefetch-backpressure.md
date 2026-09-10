---
type: decision
title: Backpressure & Flow Control via Prefetch Limits
category: Messaging & Event Streaming
status: active
created: 2026-08-28
source: messaging-production-systems (Hamle 7)
tags: [messaging, backpressure, prefetch, qos, resource-management]
---

# Backpressure & Flow Control with Prefetch

**Pattern:** Limiting unacknowledged messages to prevent consumer overload and OOM.

## The Problem

Without prefetch limits, brokers push all queued messages to consumer immediately:
- Fast producer, slow consumer → consumer memory fills up
- OOM crash → loses in-flight messages
- Other consumers starved

## Solution: Prefetch/QoS Limits

```python
import pika

# RabbitMQ: QoS (Quality of Service) prefetch
connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()

# Prefetch = max unacknowledged messages per consumer
channel.basic_qos(prefetch_count=10)  # Each consumer max 10 unacked messages

def process_message(ch, method, properties, body):
  # Process up to 10 messages concurrently
  result = heavy_computation(body)
  ch.basic_ack(delivery_tag=method.delivery_tag)  # Release prefetch slot

channel.basic_consume(queue='tasks', on_message_callback=process_message)
channel.start_consuming()
```

**Kafka: Consumer-Side Flow Control**

```python
from kafka import KafkaConsumer

consumer = KafkaConsumer(
  'orders',
  bootstrap_servers=['kafka:9092'],
  max_poll_records=100,        # Fetch max 100 records per poll
  fetch_min_bytes=1024,        # Wait for 1KB before sending
  fetch_max_wait_ms=500,       # Or 500ms, whichever comes first
  prefetch_bytes=1024*1024*10  # Internal buffer: 10MB
)

# Processing loop
for records in consumer:  # Max 100 records per iteration
  for record in records:
    process(record)
  
  consumer.commit()  # Acknowledge processed batch
```

## Tuning Prefetch: Finding the Right Value

```python
import time
import psutil

# Monitor metrics during processing
def tune_prefetch():
  prefetch_values = [1, 10, 50, 100, 300, 500]
  
  for prefetch in prefetch_values:
    channel.basic_qos(prefetch_count=prefetch)
    
    start_time = time.time()
    start_memory = psutil.Process().memory_info().rss
    
    # Process 10,000 messages
    processed = 0
    while processed < 10000:
      # ... consume and process
      processed += 1
    
    end_time = time.time()
    end_memory = psutil.Process().memory_info().rss
    
    throughput = 10000 / (end_time - start_time)
    memory_used = (end_memory - start_memory) / (1024*1024)
    
    log.info(f"prefetch={prefetch}: {throughput:.0f} msg/s, {memory_used:.1f}MB memory")
    # Find sweet spot: high throughput, low memory, low latency
```

## Hierarchical Backpressure: Per-Consumer + Channel-Wide

```python
# RabbitMQ supports layered limits
channel.basic_qos(
  prefetch_size=0,      # Size-based (0 = disabled)
  prefetch_count=100,   # Per-consumer: 100 messages
  global=False          # False = per-consumer, True = per-channel
)

# Add channel-wide limit: 1000 total across all consumers
def set_channel_limit():
  channel.basic_qos(prefetch_count=1000, global=True)
  # Now: each consumer max 100, channel max 1000 total
  # With 10 consumers: 10 × 100 = 1000 = channel limit
```

## When to Use

✓ **All production systems** (always set prefetch explicitly)
✓ **Fast producer + slow consumer** (start high, tune down)
✓ **Memory-constrained environments** (low prefetch to avoid OOM)
✓ **Batch processing** (high prefetch for throughput; need memory)

## Production Gotchas

**1. Prefetch=0 Means Unlimited (Dangerous)**
- Consumer pulls all messages into memory
- **Fix:** Always specify explicit value (100-300 typical starting point)

**2. Prefetch Too Low Causes Underutilization**
- prefetch=1: consumer waits 50ms+ for next message (latency waste)
- **Fix:** Start with 100; increase if CPU idle during processing

**3. Prefetch Too High Hides Slow Consumers**
- Consumer accumulates 10,000 unacked messages; looks healthy but actually slow
- Failure → 10,000 messages redelivered → cascade
- **Fix:** Monitor unacked count; alert if > prefetch × 10

**4. Per-Message Acks with High Prefetch**
- Acking individually = one round-trip per message (slow)
- **Fix:** Batch acks: process 100 messages, ack once (100x faster)

## Monitoring Backpressure

```python
def monitor_backpressure():
  unacked_count = channel.connection.connection_parameters.get_unacked_count()
  memory_percent = psutil.virtual_memory().percent
  
  if unacked_count > prefetch_limit * 0.8:
    log.warning(f"Backpressure building: {unacked_count} unacked (limit={prefetch_limit})")
  
  if memory_percent > 85:
    log.warning(f"Memory high: {memory_percent}%; may need to reduce prefetch")
```

---

**Bağlantılar:**
- [[hamle7-messaging-002-consumer-group-rebalancing]] (rebalancing under backpressure)
- [[hamle6-system-004-outbox-pattern]] (transactional outbox uses prefetch)
- [[hamle6-devops-001-structured-logging-json]] (monitoring unacked message counts)
