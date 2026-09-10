---
type: decision
title: Multi-Agent Systems - Coordination Patterns
category: AI & LLM
status: active
created: 2026-08-27
source: e2b-dev/awesome-ai-agents (Hamle 4)
tags: [ai, agents, coordination, communication, patterns]
---

# Multi-Agent Coordination

**Pattern:** Orchestrating Multiple AI Agents

## Communication Models

**1. Hierarchical (Orchestrator)**
```
Orchestrator (coordinator)
  ├─ Agent A (writer): Generate outline
  ├─ Agent B (researcher): Find sources
  └─ Agent C (editor): Review and refine

Flow: Sequential with feedback
```

**2. Peer (Collaborative)**
```
Agent A (analyst) ↔ Agent B (verifier) ↔ Agent C (integrator)
  └─ Shared context (memory store)

Flow: Concurrent with shared state
```

**3. Hierarchical with Voting**
```
Main agent routes to 3 specialists:
  - Correctness judge
  - Security judge  
  - Performance judge

Voting: 3/3 agree → green light
        2/3 → warning
        <2/3 → reject
```

## State Management

```
Single Source of Truth:
  Shared memory (Redis, vector DB) for all agents

Agent A writes: "User wants PDF export"
Agent B reads: "Task = PDF export" → selects PDF lib
Agent C updates: "Status = in_progress"

Alternative: Event log
  All state changes append to log
  Each agent catches up independently
```

## Failure Handling

```
Agent A fails (timeout):
  - Retry with backoff (3 attempts)
  - Escalate to human if still failing
  - Fallback to simpler approach

Example:
  Try: Complex analysis (cost $1)
  Fail: Timeout after 10s
  Retry: Simpler analysis (cost $0.10)
  Fail: Return partial result + warning
```

## Token Budget Across Agents

```
Total budget: 100k tokens/day

Agent allocation:
- Research: 40k (needs context)
- Analysis: 30k (deep thinking)
- Integration: 20k (lightweight)
- Reserve: 10k (emergencies)

Monitor: Each agent logs token usage
```

---

**Bağlantılar:** [[hamle4-005-prompt-engineering-patterns]], [[hamle4-020-token-optimization-strategies]]
