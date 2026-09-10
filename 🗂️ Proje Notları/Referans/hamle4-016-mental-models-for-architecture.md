---
type: decision
title: Mental Models - First Principles, Chesterton's Fence, Occam's Razor
category: Engineering Mindset
status: active
created: 2026-08-27
source: lucasviola/awesome-mental-models (Hamle 4)
tags: [mental-models, thinking, architecture, decision-making]
---

# Decision-Making Mental Models

**Pattern:** Thinking Tools for Architecture

## 1. First Principles Thinking

Break problem into fundamental truths:

```
Question: "Should we use microservices?"

Fundamental truths:
- We deploy independently → reduces blast radius
- Teams scale to 30 people → need clear boundaries
- Complexity grows → distributed systems harder
- Business domains: Orders, Payments, Shipping

Conclusion: Microservices if > 1 team per domain
```

## 2. Chesterton's Fence

"Don't remove it if you don't understand why it's there"

```
Old code: 100-line validation function in every controller

Before refactoring:
□ Why is it duplicated? (Oversight or intentional?)
□ What does it validate? (User input? Data integrity?)
□ Can I extract to shared lib? (Without breaking others?)

Don't just DRY because code looks wrong.
Understand purpose first.
```

## 3. Occam's Razor

"Simpler explanation is usually correct"

```
Bug: Users see stale order status

Complex: Cache invalidation issue, race condition, ...
Simple: Forgot to refresh database query

Test simple first:
1. Clear cache → fixed? → cache bug
2. Restart service → fixed? → memory leak
3. Check logs → error? → obvious bug
```

## 4. Second-Order Thinking

"What are the long-term consequences?"

```
Shortcut: Copy-paste this function (save 5 minutes)
1st order: Save time
2nd order: Team maintainers see duplication, confused by inconsistency
3rd order: New feature breaks one copy, not the other

Better: Take 15 minutes, refactor to shared function
```

## Application to Architecture

```
Decision: Use Kafka for events

1st: Fast, scalable messaging ✓
2nd: Need ops expertise, requires deployment
3rd: Can team maintain it? Do we have 6 months stability buffer?
```

---

**Bağlantılar:** 
- [[hamle4-013-technical-debt-matrix]], [[hamle4-014-design-document-template]]
- [[hamle6-system-001-event-sourcing]] (event-driven architecture patterns)
- [[hamle5-system-001-event-sourcing]] (patterns in distributed systems)
- [[hamle6-testing-001-test-pyramid]] (testing architectural decisions)
