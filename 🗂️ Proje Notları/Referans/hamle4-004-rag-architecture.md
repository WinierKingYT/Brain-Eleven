---
type: decision
title: RAG Architecture - Retrieval Augmented Generation
category: AI & LLM
status: active
created: 2026-08-27
source: anthropics/anthropic-cookbook (Hamle 4)
tags: [ai, llm, rag, prompt-engineering, retrieval, embeddings]
---

# RAG Architecture Pipeline

**Pattern:** Knowledge + LLM Generation

## Flow

```
User Query
    ↓
1. Embedding: Convert query to vector
    ↓
2. Retrieval: Find similar documents via vector DB
    ↓
3. Ranking: Score top-K by relevance
    ↓
4. Context Assembly: Build prompt with docs
    ↓
5. Generation: LLM generates response
    ↓
Answer with citations
```

## Critical Decisions

**1. Embedding Model**
- `OpenAI text-embedding-3-small`: 1536-dim, cheap
- `OpenAI text-embedding-3-large`: 3072-dim, better quality
- Semantic quality > dimensions (3-large > raw 8k-dim garbage)

**2. Retrieval Strategy**
- Dense (vector similarity): Fast, semantic
- Sparse (BM25): Exact keyword matching
- Hybrid: Both + rank

**3. Context Window Management**
- Fit docs in context: Better relevance
- Summarize long docs: Preserve meaning, save tokens
- Hierarchical: Chunk hierarchy → retrieve summary → expand if needed

## Example: Customer Support RAG

```
Query: "How do I return items?"
    ↓
Retrieve: [
  policy_doc: "30-day return window",
  faq: "Return process steps",
  terms: "Restocking fee rules"
]
    ↓
Prompt:
  System: You're helpful support agent
  Context: [Retrieved docs above]
  User: How do I return items?
    ↓
LLM: "You have 30 days... Here's the process..."
```

## Common Mistakes

- ❌ Not re-ranking results (first result not always relevant)
- ❌ Context window too small (lose important docs)
- ❌ Embedding quality not tested
- ❌ No citation tracking (can't verify sources)

---

**Bağlantılar:** [[hamle4-005-prompt-engineering]]
