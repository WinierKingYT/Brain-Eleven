---
type: decision
title: Incident Response - Playbook Framework
category: Security & DevOps
status: active
created: 2026-08-27
source: dastergon/awesome-sre (Hamle 4)
tags: [sre, incident-response, reliability, playbook]
---

# Incident Response Playbook

**Pattern:** Structured Crisis Management

## Immediate Actions (First 15 Minutes)

```
1. DECLARE INCIDENT
   - Message: "#incident: Payment API errors (P1)"
   - Slack channel: incident-response
   - Page: on-call engineer + manager

2. ESTABLISH INCIDENT COMMANDER
   - Role: coordinates response, no direct fixes
   - Communications owner: updates stakeholders
   - Technical lead: investigates root cause

3. MITIGATE IMPACT
   - Rollback last deployment? 
   - Enable fallback?
   - Route traffic elsewhere?
   - Scale resources?

4. GATHER DATA
   - Application logs (last 15 min)
   - Infrastructure metrics (CPU, memory, disk)
   - Network traffic patterns
   - Recent changes (deployment, config)
```

## Investigation Phase (15 minutes - 2 hours)

```
Timeline:
- 15:30: Alert fired (error rate > 1%)
- 15:32: Declared P1
- 15:35: Identified: DB connection pool exhausted
- 15:45: Mitigation: Increased pool size from 100 → 150
- 16:00: Service recovered
```

## Post-Incident: Blameless Post-Mortem

```
Template:
1. INCIDENT SUMMARY
   - Duration: 30 minutes
   - Impact: 5M users, $50k revenue loss
   - Root cause: Untuned connection pool

2. TIMELINE
   - 15:30: Alert fired
   - 15:35: Declared (5 min delay)
   - 15:45: Recovered (10 min MTTR)

3. ROOT CAUSE ANALYSIS
   - Why did pool exhaustion happen?
   - Why wasn't this caught in testing?
   - Why did monitoring not warn earlier?

4. ACTION ITEMS
   - [ ] Add connection pool monitoring
   - [ ] Load test with 2x peak traffic
   - [ ] Document recovery steps
   - [ ] Ownership assigned + deadline

5. LESSONS LEARNED
   - What did we do well?
   - What should we improve?
   - How do we prevent recurrence?
```

---

**Bağlantılar:** [[hamle4-010-sre-sli-slo-sla]]
