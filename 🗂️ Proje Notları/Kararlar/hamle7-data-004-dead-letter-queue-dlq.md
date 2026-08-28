---
type: decision
title: Dead Letter Queue (DLQ) Pattern for Pipeline Error Handling
category: Data Engineering & Error Handling
status: active
created: 2026-08-28
source: data-engineering-production-systems (Hamle 7)
tags: [error-handling, pipeline-resilience, dlq, poison-messages, observability]
---

# Dead Letter Queue Pattern

**Pattern:** Route failed records to separate queue with full context for analysis and replay.

## The Problem

A single corrupted record stops entire pipeline:
- CSV has malformed JSON in one field → entire batch fails
- Downstream dependent on 10k records gets 0
- No visibility into what failed or why
- Retry logic doesn't distinguish transient vs permanent failures

## Solution: Separate DLQ with Context Preservation

Route failures to dead letter queue with full metadata:

```python
# Spark job with DLQ handling
from pyspark.sql import functions as F

def process_batch(df):
  try:
    # Main processing
    result = df.filter(col('amount') > 0) \
      .withColumn('status', lit('processed'))
    result.write.format('delta').mode('append').save('s3://processed/')
    
  except Exception as e:
    # Route to DLQ
    error_df = df.withColumn('error_message', lit(str(e))) \
      .withColumn('error_timestamp', current_timestamp()) \
      .withColumn('retry_count', lit(0)) \
      .withColumn('original_payload', to_json(struct('*')))
    
    error_df.write.format('delta').mode('append').save('s3://dlq/')
    
    log.error(f"Routed {error_df.count()} records to DLQ: {e}")
```

**Kafka Example with Retry Logic:**

```python
from kafka import KafkaProducer, KafkaConsumer

def consume_with_dlq(topic, dlq_topic):
  consumer = KafkaConsumer(topic)
  producer = KafkaProducer()
  
  for message in consumer:
    try:
      # Process
      process_event(message.value)
      producer.send(topic + '-success', message)
      
    except TransientError as e:
      # Retry transient errors
      retry_count = int(message.headers.get('x-retry-count', 0))
      if retry_count < 3:
        producer.send(
          topic,
          message.value,
          headers={**message.headers, 'x-retry-count': str(retry_count + 1)}
        )
      else:
        # Max retries exceeded → DLQ
        producer.send(dlq_topic, {
          'payload': message.value,
          'error': str(e),
          'retries': retry_count,
          'timestamp': datetime.now().isoformat(),
          'last_error_time': message.headers.get('x-last-error-time')
        })
        
    except PermanentError as e:
      # Send to DLQ immediately
      producer.send(dlq_topic, {
        'payload': message.value,
        'error': str(e),
        'error_type': 'PERMANENT',
        'timestamp': datetime.now().isoformat()
      })
```

## Monitoring & Alerting

```python
# Alert on DLQ growth
def monitor_dlq(dlq_table):
  dlq_count = spark.sql("SELECT COUNT(*) FROM dlq").collect()[0][0]
  dlq_age_hours = spark.sql("""
    SELECT 
      (current_timestamp - MAX(error_timestamp)) / 3600 as max_age_hours
    FROM dlq
  """).collect()[0][0]
  
  if dlq_count > 1000:
    alert_slack(f"⚠️ DLQ size: {dlq_count} records")
  
  if dlq_age_hours > 24:
    alert_slack(f"⚠️ DLQ oldest record: {dlq_age_hours:.1f}h old - may need manual replay")
```

## Reprocessing DLQ Records

```python
# Manual replay: fix root cause, reprocess
def replay_dlq(dlq_id_list):
  dlq_records = spark.sql(f"SELECT * FROM dlq WHERE id IN ({dlq_id_list})")
  
  # Extract original payload
  replayed = dlq_records.select(
    from_json(col('original_payload'), schema).alias('data')
  ).select('data.*')
  
  # Reprocess with fixed logic
  processed = process_batch(replayed)
  processed.write.mode('append').save('s3://processed/')
  
  # Mark as replayed in DLQ
  spark.sql(f"UPDATE dlq SET replayed_at = current_timestamp WHERE id IN ({dlq_id_list})")
```

## When to Use

✓ **High-volume streaming pipelines** (Kafka, Kinesis with 1000+ msg/sec)
✓ **Mission-critical ETL** where graceful degradation required
✓ **CDC replication** with mixed data quality upstream
✓ **Multi-source lakes** where upstream schemas unreliable

## Production Gotchas

**1. DLQ Becomes Silent Graveyard**
- Records pile up; no one checks
- **Fix:** Set alerts: DLQ rate > 5% OR age > 24h → Slack notification with dashboard link

**2. Transient vs Permanent Errors Not Differentiated**
- DB timeout (transient, should retry) vs malformed JSON (permanent, won't retry successfully)
- **Fix:** Catch exceptions by type; categorize; retry transient only

**3. DLQ Retention Policies Outlive Investigation Windows**
- Delete DLQ after 7 days; root cause found on day 8
- **Fix:** Retain for 90+ days; archive older records to S3 cold storage

**4. Reprocessing DLQ Republishes to Same Topic**
- If DLQ messages re-sent to main topic and still fail → infinite loop
- **Fix:** Add `x-dlq-attempt` header; reject if attempt > 1 after republish

---

**Bağlantılar:**
- [[hamle6-system-003-saga-pattern]] (distributed transaction recovery)
- [[hamle6-devops-001-structured-logging-json]] (error tracking and monitoring)
- [[hamle6-testing-001-test-pyramid]] (chaos testing error paths)
