---
type: decision
title: SRE Metrics - SLI, SLO, SLA Framework
category: Security & DevOps
status: active
created: 2026-08-27
source: dastergon/awesome-sre (Hamle 4)
tags: [sre, metrics, reliability, sli, slo, sla]
---

# SLI/SLO/SLA Framework

**Pattern:** Reliability Measurement and Accountability

## Definitions

**SLI (Service Level Indicator)** = Metric
- Example: API latency (p99), error rate (%), availability (%)

**SLO (Service Level Objective)** = Target
- Example: "99.9% availability" = 43 minutes downtime/month

**SLA (Service Level Agreement)** = Contract
- Example: Miss SLO → customer gets credit

## Example: Payment API

```
SLI: 
- Latency: p50 <100ms, p99 <500ms
- Error rate: <0.1%
- Availability: uptime %

SLO:
- p99 latency < 500ms (99% of requests)
- Error rate < 0.05%
- 99.95% availability (monthly)

SLA:
- Miss latency SLO → customer gets 5% credit
- Miss availability SLO → customer gets 10% credit
- Two consecutive months → full refund
```

## Error Budget

```
SLO: 99.9% availability
= 99.9% uptime, 0.1% downtime allowed
= 43 minutes/month downtime budget

Use it strategically:
- Risky deployment: 10 minutes
- Canary rollout: 20 minutes
- DB maintenance: 10 minutes
- Reserve: 3 minutes

Total: 43 minutes ✓
```

## Incident Response Levels

| Severity | Response Time | Escalation |
|----------|---------------|-----------|
| S1 (Critical) | 15 minutes | CEO notified |
| S2 (High) | 1 hour | VP notified |
| S3 (Medium) | 4 hours | Manager notified |
| S4 (Low) | 1 day | Log only |

---

**Bağlantılar:** 
- [[hamle4-011-incident-response]] (response procedures)
- [[hamle6-devops-001-structured-logging-json]] (SLI measurement)
- [[hamle6-testing-001-test-pyramid]] (reliability testing)
- [[hamle5-system-001-event-sourcing]] (audit trail for SLA)
