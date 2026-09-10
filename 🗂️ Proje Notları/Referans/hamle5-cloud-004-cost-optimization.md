---
type: decision
title: Cloud Cost Optimization - Right-sizing and Reserved Instances
category: Cloud Architecture & DevOps
status: active
created: 2026-08-28
source: aws/cost-optimization (Hamle 5)
tags: [aws, cost-optimization, reserved-instances, rightsizing, billing]
---

# Cloud Cost Optimization Strategies

**Pattern:** Reducing Cloud Spend Without Sacrificing Performance

## Right-Sizing Instances

```
Typical situation:
  Instance type: m5.2xlarge (8 vCPU, 32GB)
  Utilization: 5-10% CPU, 2-3GB memory
  Cost: $0.384/hour × 730 hours = $280/month
  
Wasted capacity!
  
Right-sized:
  Instance type: t3.small (2 vCPU, 2GB)
  Utilization: 50-70% CPU, 60% memory
  Cost: $0.0208/hour × 730 hours = $15/month
  
Savings: 94% (keep same performance, pay 1/20th)
```

## Finding Over-Sized Instances

```bash
# AWS CLI: Get average CPU utilization over 30 days
aws cloudwatch get-metric-statistics \
  --namespace AWS/EC2 \
  --metric-name CPUUtilization \
  --dimensions Name=InstanceId,Value=i-1234567890abcdef0 \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-02-01T00:00:00Z \
  --period 3600 \
  --statistics Average

# AWS Cost Explorer: Right-sizing recommendations
# Console → Cost Management → Cost Explorer
#         → Trusted Advisor → Idle resources
```

## Reserved Instances (RI)

```
On-Demand Pricing:
  t3.medium: $0.0416/hour × 730 hours = $30/month

1-Year Reserved Instance:
  Upfront: $150
  Monthly: $15
  Total: $150 + ($15 × 12) = $330/year
  
Savings vs On-Demand: $30 × 12 - $330 = $330/year (55% off)
```

## Instance Selection Matrix

```
High Utilization (>50%):
  ✓ Reserved Instances (3-year is cheapest)
  ✓ Savings Plans (1-3 year commitments)
  
Variable Utilization (20-50%):
  ✓ Mix of On-Demand + Reserved (50/50)
  ✓ Compute Savings Plans (more flexible)
  
Low Utilization (<20%):
  ✓ On-Demand or Spot
  ✗ Don't buy Reserved (too risky)
  
Batch/Temporary:
  ✓ Spot Instances (70% cheaper, interruption ok)
```

## Storage Optimization

```
S3 Storage Classes:
  S3 Standard:    $0.023/GB (instant access)
  S3-IA:          $0.0125/GB (infrequent, 30 day minimum)
  S3-Glacier:     $0.004/GB (archive, retrieval delay)
  S3-Glacier Deep: $0.00099/GB (compliance, rare access)

Example:
  1TB logs (rarely accessed after 30 days)
  
  Standard: $1000/month
  → IA after 30 days: $150/month
  → Glacier after 90 days: $50/month
  
  Annual savings: $8,000+
```

## Compute Savings Plans

```
1-Year Savings Plan:
  Flexibility: Mix of instance types and regions
  Discount: 20-30% off on-demand
  
Example:
  Commitment: $1000/month baseline
  Any instances using that $1000 get 20% discount
  
  If use $1500 worth on-demand:
    - $1000 at -20% = $800
    - $500 at full price = $500
    - Total: $1300 (instead of $1500)
```

## Cost Monitoring

```bash
# AWS Cost Explorer (visualize trends)
# AWS Budgets (alert on spending)
# AWS Cost and Usage Report (detailed breakdown)

# CLI: Get daily spending
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-02-01 \
  --granularity MONTHLY \
  --metrics "UnblendedCost" \
  --group-by Type=DIMENSION,Key=SERVICE

# Expected output:
# EC2: $5000/month
# RDS: $2000/month
# S3: $800/month
# etc.
```

## Cost Optimization Checklist

```
✓ Enable detailed billing
✓ Use AWS Cost Explorer monthly
✓ Right-size instances (target: 50-70% utilization)
✓ Buy 1-3 year RIs for stable workloads
✓ Use Spot for batch/fault-tolerant work
✓ Move infrequent data to cheaper tiers
✓ Delete unattached EBS volumes and snapshots
✓ Delete old AMIs
✓ Close unused RDS instances
✓ Monitor unused security groups/load balancers
```

---

**Bağlantılar:** [[hamle5-performance-001-flame-graphs]]
