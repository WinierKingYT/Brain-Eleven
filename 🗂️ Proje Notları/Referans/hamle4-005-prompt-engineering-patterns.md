---
type: decision
title: Prompt Engineering Patterns - Few-Shot, CoT, ReAct
category: AI & LLM
status: active
created: 2026-08-27
source: dair-ai/Prompt-Engineering-Guide (Hamle 4)
tags: [ai, prompts, few-shot, chain-of-thought, react, reasoning]
---

# Prompt Engineering Patterns

**Pattern:** Multi-Technique Prompting

## 1. Few-Shot Learning (In-Context Examples)

```
System: You classify movie reviews as positive or negative

Examples:
- "Great movie!" → positive
- "Terrible waste of time" → negative

User: "Amazing storyline but slow pacing"
Response: mixed (but needs clarification)
```

## 2. Chain-of-Thought (CoT)

Forces step-by-step reasoning:

```
User: "If there are 3 trees with 2 birds each, how many birds?"

Without CoT:
Q: Birds total?
A: 6 (sometimes wrong even on simple math)

With CoT:
Q: Think step by step. 3 trees, 2 birds each, total birds?
A: Step 1: Each tree has 2 birds
   Step 2: 3 trees × 2 = 6 birds
   Total: 6 birds ✓
```

## 3. ReAct (Reasoning + Acting)

```
Thought: I need current price of Apple stock
Action: QUERY_API("AAPL price")
Observation: $195.50
Thought: Now I can answer the question
Response: Apple stock is $195.50
```

## 4. System Prompts

Set role and constraints:

```
System: You are a Python expert. 
- Explain code clearly
- Suggest performance optimizations
- Never provide security-sensitive code

User: How do I hash passwords?
Response: Use bcrypt library...
```

## Anti-Patterns

- ❌ Vague prompts ("Help me")
- ❌ No examples (CoT improves by 30-50%)
- ❌ Ignoring temperature setting (0 = deterministic, 1 = creative)
- ❌ Not using system prompts

---

**Bağlantılar:** [[hamle4-004-rag-architecture]]
