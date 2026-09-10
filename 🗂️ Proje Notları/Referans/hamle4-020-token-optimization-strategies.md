---
type: decision
title: Token Optimization - Context Window Management
category: AI & LLM
status: active
created: 2026-08-27
source: openai/openai-cookbook (Hamle 4)
tags: [ai, tokens, optimization, context, cost]
---

# Token Optimization Strategies

**Pattern:** Maximum Efficiency in Context Windows

## Token Costs

```
Model: GPT-4 (8K context)
- Input: $0.03 / 1K tokens
- Output: $0.06 / 1K tokens

Example:
- Prompt: 2000 tokens ($0.06)
- Response: 500 tokens ($0.03)
- Total: $0.09 per request

At scale (1M requests/month):
- Without optimization: $90k/month
- With 50% reduction: $45k/month
```

## Compression Techniques

**1. Summarization**
```
Before:
  System: Long company handbook (8000 tokens)
  User: How to file expense?

After:
  System: Summarized handbook (500 tokens) + "Full doc in context if needed"
  User: How to file expense?

Savings: 93% token reduction
```

**2. Retrieval-Augmented Generation (RAG)**
```
Before:
  Embed entire manual in prompt

After:
  Only include relevant sections (vector similarity search)
  
Example: 500-page manual → 2 relevant sections (200 tokens)
```

**3. Instruction Optimization**
```
Before:
  "You are a helpful assistant. Your goal is to help users..."
  (verbose, 100+ tokens)

After:
  "Assistant. Help users."
  (5 tokens, same effect)
```

**4. Output Control**
```
Without: Let model ramble (4000 tokens)
With: "Respond in 100 words max"

Force JSON: "Output JSON only, no explanation"
```

## Budget Calculator

```
Budget: $100/month
Model: GPT-4 (avg 3000 tokens per request)
Cost per request: $0.18

Capacity: 100000 / 0.18 = 555 requests/month
= 18 requests/day

With 50% optimization:
= 36 requests/day
```

---

**Bağlantılar:** [[hamle4-004-rag-architecture]], [[hamle4-005-prompt-engineering-patterns]]
