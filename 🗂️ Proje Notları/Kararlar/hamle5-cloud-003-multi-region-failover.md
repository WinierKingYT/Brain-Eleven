---
type: decision
title: Multi-Region Failover - Geographic Redundancy
category: Cloud Architecture & DevOps
status: active
created: 2026-08-28
source: aws/aws-architecture (Hamle 5)
tags: [multi-region, failover, high-availability, disaster-recovery, aws]
---

# Multi-Region Failover Strategy

**Pattern:** Geographic Redundancy and Automatic Failover

## Architecture

```
┌─────────────────────────────────────────┐
│          Global DNS (Route 53)          │
│  us-east-1 (Primary) | eu-west-1 (DR)  │
└──────────┬───────────────────┬──────────┘
           │                   │
    ┌──────▼──────┐     ┌──────▼──────┐
    │ us-east-1   │     │ eu-west-1   │
    │ ├ API       │     │ ├ API       │
    │ ├ Database  │     │ ├ Database  │
    │ └ Cache     │     │ └ Cache     │
    └─────────────┘     └─────────────┘
    ↑
    PRIMARY (taking traffic)
    └─ If primary fails → DNS switches to DR
```

## DNS Failover (Route 53)

```json
{
  "HostedZoneId": "/hostedzone/Z1EXAMPLE",
  "ResourceRecordSets": [
    {
      "Name": "api.example.com",
      "Type": "A",
      "SetIdentifier": "primary",
      "Failover": "PRIMARY",
      "AliasTarget": {
        "HostedZoneId": "Z35SXDOTRQ7X7K",
        "DNSName": "elb-us-east-1.amazonaws.com",
        "EvaluateTargetHealth": true
      }
    },
    {
      "Name": "api.example.com",
      "Type": "A",
      "SetIdentifier": "secondary",
      "Failover": "SECONDARY",
      "AliasTarget": {
        "HostedZoneId": "Z32O12XQLNTSW2",
        "DNSName": "elb-eu-west-1.amazonaws.com",
        "EvaluateTargetHealth": true
      }
    }
  ]
}
```

## Database Replication

```
Active-Passive:
  Primary (us-east-1)    Replica (eu-west-1)
       ↓ sync writes
       ↓ continuous replication
       
  On primary failure: Promote replica (data loss = replication lag)
  Typical lag: <1 second

Active-Active:
  Both regions accept writes (eventual consistency)
  Conflict resolution needed (last-write-wins, custom logic)
  Higher availability, eventual consistency
```

## Backup Strategy

```
Tier 1: Primary Region Backup
  - Daily snapshots
  - 7-day retention
  - <1 hour recovery time

Tier 2: Cross-Region Backup
  - Weekly snapshots to DR region
  - 30-day retention
  - Protection against regional disaster

Tier 3: Archive
  - Monthly to Glacier
  - 1-year retention
  - Compliance/audit trail
```

## Failover Sequence

```
1. Health Check Fails
   └─ Primary region unhealthy for 30s

2. DNS Updates (30-60s propagation)
   └─ Traffic reroutes to secondary

3. Application Detection
   └─ App detects primary region down
   └─ Switches to DR database connection string

4. Manual Validation
   └─ Ops team verifies secondary is healthy
   └─ No automatic promotion to primary (prevent flapping)

5. Recovery
   └─ Once primary recovers → manual validation
   └─ DNS switches back
   └─ Resync primary from secondary
```

## Challenges

```
❌ Data Replication Lag
  Write to us-east-1 → replicate to eu-west-1 (1-5 seconds)
  Failover happens → eu-west-1 missing latest writes
  
  ✓ Accept eventual consistency
  ✓ Use transaction logs (binary logs) for recovery

❌ DNS Propagation Delay
  Update DNS → wait 30-60s for worldwide cache refresh
  
  ✓ Reduce TTL before planned failover (from 3600s to 60s)
  ✓ Use application-level failover (faster than DNS)

❌ Split-Brain Scenario
  Primary region partitioned (can't reach, but not down)
  Both regions think they're primary
  
  ✓ Use quorum voting (need majority for promotion)
  ✓ Manual failover only (don't auto-promote)
```

---

**Bağlantılar:** [[hamle5-cloud-004-cost-optimization]]
