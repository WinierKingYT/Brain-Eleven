---
type: decision
title: Schema Evolution - Medallion Governance Pattern
category: Data Engineering & Schema Design
status: active
created: 2026-08-28
source: data-engineering-production-systems (Hamle 7)
tags: [data-engineering, schema-evolution, medallion, governance, data-quality]
---

# Schema Evolution with Medallion Governance

**Pattern:** Layered data quality by pipeline layer (Bronze → Silver → Gold).

## The Problem

Incoming data changes (new columns, type shifts, nested structure changes) break downstream pipelines silently:
- Bronze layer accepts raw data → schema mutates
- Silver layer assumes fixed structure → queries fail
- Gold layer dashboards show wrong data
- No visibility into what changed or when

## Solution: Medallion Architecture with Progressive Strictness

Three-layer governance pyramid:

```
GOLD (Strict) ← validated, immutable dimensional/fact tables
  ↓ (contract enforcement)
SILVER (Moderate) ← type-frozen but columns can evolve
  ↓ (schema detection)
BRONZE (Permissive) ← raw data, full schema evolution
```

**Bronze Layer (Permissive):**
```python
# Auto-evolve schema; capture all changes
spark.readStream \
  .option("cloudFiles.format", "json") \
  .option("cloudFiles.schemaEvolutionMode", "addNewColumns") \
  .load("s3://raw-data/") \
  .writeStream.format("delta") \
    .option("mergeSchema", "true") \
    .save("s3://bronze-lake/")
```

**Silver Layer (Type-Frozen):**
```python
# Allow new columns, reject type changes
schema = StructType([
  StructField("order_id", LongType()),
  StructField("customer_id", LongType()),
  StructField("amount", DoubleType()),
  # ... more fields
])

silver_df = spark.read.schema(schema).load("s3://bronze-lake/")
# Rejects: order_id as string (type mismatch)
# Accepts: new column 'shipping_cost' (schema evolution)
```

**Gold Layer (Strict Contracts):**
```python
# Validate with Pydantic model before ingesting
from pydantic import BaseModel, validator

class OrderFact(BaseModel):
  order_id: int
  customer_id: int
  amount: float
  
  @validator('amount')
  def amount_positive(cls, v):
    if v <= 0: raise ValueError('amount must be positive')
    return v

# Ingest only if passes validation
for record in silver_df.collect():
  OrderFact(**record.asDict())  # Raises if invalid
```

## Change Notification

Instrument schema changes to alert team:

```python
# Detect new columns at Bronze → Silver ingestion
def detect_schema_changes(old_schema, new_schema):
  new_cols = set(new_schema) - set(old_schema)
  dropped_cols = set(old_schema) - set(new_schema)
  type_changes = {
    col: (old_schema[col], new_schema[col])
    for col in set(old_schema) & set(new_schema)
    if old_schema[col] != new_schema[col]
  }
  
  if new_cols or dropped_cols or type_changes:
    slack.post(f"Schema changed: +{new_cols}, -{dropped_cols}, types={type_changes}")
    
detect_schema_changes(prev_schema, current_schema)
```

## When to Use

✓ **Multi-source data lakes** (100+ upstream sources)
✓ **Evolving APIs** with backward-compatible changes
✓ **SaaS data integration** (Salesforce, HubSpot add fields)
✓ **Data platforms** handling diverse schemas

## Production Gotchas

**1. Silent Schema Evolution Creates Invisible Dashboard Changes**
- New column silently appears; dashboards don't update
- **Fix:** Instrument every schema change event; require manual Silver/Gold migration approval

**2. Type Changes Leave Orphaned Columns**
- `amount: int` → `amount: string` causes query errors
- **Fix:** Use variant columns: `amount` (original), `amount__v_text` (coerced version); keep both temporarily

**3. Removing Columns is Hard**
- Downstream depends on column; can't delete without breaking queries
- **Fix:** Mark as deprecated; use dbt `deprecated` flag; soft-deprecate for 6 months before removal

---

**Bağlantılar:**
- [[hamle6-system-002-cqrs]] (separation of read/write models)
- [[hamle5-database-003-transaction-isolation]] (schema consistency)
- [[hamle6-devops-001-structured-logging-json]] (tracking metadata changes)
