---
type: decision
title: Technical Debt - Assessment and Paydown Matrix
category: Engineering Mindset
status: active
created: 2026-08-27
source: charlax/professional-programming (Hamle 4)
tags: [technical-debt, refactoring, architecture, decision-making]
---

# Technical Debt Assessment

**Pattern:** Intentional vs Accidental Debt

## Intentional Debt (Acceptable)

```
MVP Launch:
- Skip comprehensive testing (accept P1 bugs later)
- Monolith first (split microservices later)
- Manual deployment (automate after stable)

Trade-off: Speed now, refactor later
Timeline: Pay within 3 months or cost multiplies
```

## Accidental Debt (Prevent)

```
Copy-paste code (should be DRY function)
Inconsistent naming (confuses team)
No error handling (crashes in production)
Hardcoded values (brittle to change)

Cost: Compounds daily (more expensive to fix later)
Timeline: Pay immediately (day 1)
```

## Paydown Prioritization

| Debt Type | Cost | Priority | Action |
|-----------|------|----------|--------|
| Security hole | Very High | P0 | Fix now |
| Performance regression | High | P1 | Fix this sprint |
| Code duplication | Medium | P2 | Refactor next sprint |
| Style inconsistency | Low | P3 | During review |

## "Debt Crisis" Detection

```
Red flags (time to refactor):
- Adding features takes 50% longer (cognitive load)
- Code review feedback is "split this file"
- Test failures are hard to diagnose
- onboarding new dev takes weeks
- Deployments happen less frequently

Action: Allocate 20% sprint time to debt paydown
```

## Design Debt Decision Tree

```
"Should we refactor this module?"

1. Does it block other work?
   → YES: Refactor (unblocks progress)
   → NO: Continue to 2

2. Is it used in critical path?
   → YES: Refactor (impacts users)
   → NO: Continue to 3

3. Does team complain about it?
   → YES: Refactor (morale matters)
   → NO: Leave it (no ROI)
```

---

**Bağlantılar:** [[hamle4-014-design-doc-template]]
