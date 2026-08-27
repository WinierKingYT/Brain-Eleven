---
type: decision
title: Hallucination Prevention in LLMs
category: AI & LLM
status: active
created: 2026-08-27
source: dair-ai/Prompt-Engineering-Guide (Hamle 4)
tags: [ai, hallucinations, factuality, verification, safety]
---

# Preventing LLM Hallucinations

**Pattern:** Confidence-Based Verification

## What is Hallucination?

```
Query: "What year did Einstein discover relativity?"

Hallucination (plausible-sounding lie):
  "Einstein discovered relativity in 1907"
  (Actually 1905 for special relativity)

Why: Model completes probabilistically without fact-checking
```

## Prevention Techniques

**1. Citation Requirements**
```
Prompt: "Answer and cite sources."

Model:
  "Relativity was published in 1905 (Einstein, 1905)."
  [Citable source required forces accuracy]
```

**2. Confidence Thresholds**
```
Model response metadata:
  {
    "answer": "Einstein discovered...",
    "confidence": 0.95,  # High confidence
    "source": "Known fact"
  }

If confidence < 0.7: Mark as [uncertain]
```

**3. Verification Chain**
```
Step 1: Generate answer (might hallucinate)
Step 2: Verify facts (agent checks sources)
Step 3: Return with citations or error

Example:
  Step 1: "Einstein, 1907"
  Step 2: Check → Wrong! Actually 1905
  Step 3: Return corrected answer
```

**4. Grounding in Context**
```
❌ Without context:
   "Tell me about quantum entanglement"
   → Model might invent concepts

✓ With context:
   "Here's Wikipedia on entanglement: [text]
    Based ONLY on this, explain entanglement"
   → Model can't hallucinate beyond text
```

**5. Uncertainty Statements**
```
✓ Confidence-aware output:

High: "Python lists are ordered in 3.7+"
Medium: "I'm not certain, but..."
Low: "I don't know enough to answer"

❌ Confident guessing
```

---

**Bağlantılar:** [[hamle4-004-rag-architecture]]
