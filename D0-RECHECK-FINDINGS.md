# D0 Recheck — the metric, not just the model, was the problem

**Status:** GENERATED EVIDENCE — research findings, re-derived independently.
Does not itself reopen IG-04's Branch A/D1 decision; that remains a human
checkpoint. Written after `IG04-B2` and `IG-07 Slice 2C/C1` closed, prompted
by a request to actually investigate the retrieval-quality gap instead of
accepting the closed decision at face value.

**Method:** a research subagent investigated `evals/ig01d/` end to end
(methodology, corpus, scoring code, production retrieval paths) with
file/line citations. The three most load-bearing claims below were then
independently re-derived by this session directly against the repo — not
taken on the subagent's word — before being written here.

## 1. The 0.45/0.60 thresholds are not reachable by any retriever on this corpus

`evals/ig01d/spike.py:40` fixes `_K = 5`. `_metric_row` (`spike.py:213-233`)
computes `precision = relevant_count / len(top)`, where `top` is always the
first 5 retrieved ids — **not** normalized by how many gold-relevant items
the case actually has.

Independently counted directly from `evals/ig01d/public/ig-r3-d0-v1/retrieval.jsonl`
(`expected_context.required ∪ expected_context.useful` per case, 120 cases):

```
105 cases have exactly 2 gold-relevant items
 15 cases have exactly 3 gold-relevant items

oracle precision@5 (a perfect retriever, gold items ranked first) = 0.425 mean
```

Reproduced independently with:
```python
oracle_scores = [min(len(required | useful), 5) / 5 for each case]
# -> mean 0.42499999999999905
```

The program's own **RETHINK threshold is 0.45** — *above* the perfect-oracle
ceiling on this corpus. The **program floor of 0.60** is only reachable at
all on the 12.5% of cases with 3 relevant items, and is mathematically
unreachable in aggregate regardless of retrieval quality. `IG01-A-EVALUATION-CONTRACT.md:243`'s
worked example (`"3 relevant in top 5 → 3/5 = 0.60"`) implicitly assumed 3
relevant items per case; the corpus that was later built to measure against
it mostly has 2. Nobody appears to have checked that feasibility before
freezing the thresholds.

## 2. Measured against the real ceiling, the gap is real but much smaller than it looked

Measured MPNet precision: 0.205. Against the true ceiling of 0.425, that's
**~48% of the achievable score captured**, not "0.205 out of a 0.60
possible." Consistent with this: mandatory recall was already 0.70–0.81
across variants (`CODEX-RESULTS-D0.md`'s own table) — the required item is
usually *found* somewhere in the top 5; the low precision number is
substantially a mechanical consequence of 3-4 forced-noise slots per case
(nothing else was allowed to fill them), not the model failing to find the
right memory.

## 3. The "hybrid" arm that supposedly didn't help was fused with a query-blind ranker

`evals/ig01d/d0_rethink.py:208` uses `BaselineContextProvider` (`evals/baseline.py:142-169`)
as the "lexical" side of the RRF hybrid. That adapter's own docstring says
it plainly: *"`task.prompt` is deliberately not supplied to the compiler."*
It wraps the production `scripts/context-compiler.py` V1 ranker, which —
independently confirmed by reading `_rank_memories` (`context-compiler.py:314-367`)
— scores purely as `type_priority*0.4 + confidence*0.4 + freshness*0.2`
with **no query text used anywhere in the function**. Fusing a real semantic
ranking with a ranker that cannot see the query dilutes the semantic signal
with noise; that the resulting "hybrid" (0.185-0.2017) scored *below*
semantic-only (0.205) is the expected result of that setup, not evidence
that a genuine lexical+semantic hybrid would fail. A real query-aware
lexical hybrid was never actually tested — the repo already has two
query-aware scorers that were never used for this (`retrieval_decision_v2/engine.py`'s
IDF term-overlap, `scripts/memory-retriever.py`'s Jaccard overlap).

## 4. What D0 measured was never live in production anyway

Traced separately, independently confirmed by reading the code: the V1 path
that actually fires on every SessionStart (`scripts/context-compiler.py`,
per `IG04-B1-CONTRACT.md:30-40`'s own diagram) never reads the query at all
(§3 above). `scripts/hybrid-search.py`'s semantic channel only runs from the
on-demand chat/search surface (`brain_eleven/runtime/chat_interface.py`,
`scripts/search-api.py`), and is gated off by default (`IG_EMBEDDING_PROVIDER`
unset → `semantic_available = False`, `scripts/semantic-search.py:41-49`).
V2/SHADOW (`context_router/`, `retrieval_decision_v2/`, `context_compiler_v2/`)
uses substring/keyword matching and IDF term-overlap, not embeddings at all
— `grep -r "embed|cosine|vector"` across all three returns zero hits.
**Abandoning "Branch A" changed nothing about what users experience today,
because embedding retrieval was never wired into the live path in the first
place.**

## What this doc does and doesn't claim

- Does not claim embedding retrieval is secretly great — 48% of a 0.425
  ceiling is a real, moderate gap worth closing, not a solved problem.
- Does not reopen the D1 decision by itself — that pivot (Branch A → Branch
  B, human-approved retrieval) was a reasonable response to the number as
  measured, and B1/B2 remain closed, accepted, and valuable regardless of
  this finding.
- Does claim the specific evidence D1 was based on (0.205 vs a 0.60 floor,
  "hybrid doesn't help") mixes a real model-quality gap with a metric-design
  artifact and a mislabeled control arm, and that both are cheap to correct
  without new infrastructure.

## Recommended next experiments (both reuse existing code/data, no new infra)

1. **Re-score the existing D0 rankings with a fair metric** — precision
   normalized by `min(k, |relevant|)`, recall@5, and MRR as co-primary,
   against `evals/ig01d/d0-probe-real-exact.json`'s saved output. No new
   retrieval run needed.
2. **Re-run the hybrid variant with a real lexical arm** — swap
   `BaselineContextProvider` out of `d0_rethink.py`'s RRF fusion (`d0_rethink.py:156-165`,
   `_rrf`) for `retrieval_decision_v2.engine`'s IDF scorer or
   `scripts/memory-retriever.py`'s Jaccard scorer.

## Longer-term, lower-priority gaps identified but not yet actioned

- A second embedding model (`BAAI/bge-m3`) was listed as a D0 candidate but
  never actually run — `_try_tuned_provider` (`d0_rethink.py:280-311`) stops
  at the first success (E5-large).
- Query expansion/rewriting before embedding: not present anywhere in
  `evals/ig01d/`.
- The eval corpus itself is 40 underlying tasks × 3 mechanical
  EN/TR/TR-EN template translations (`evals/ig01d/build_d0_corpus.py:30-113`)
  — generic, repetitive, and not representative of the real vault's
  eclectic content. Any future precision number should be treated
  cautiously until measured against a more representative corpus.

**Key files:** `evals/ig01d/d0_rethink.py`, `evals/ig01d/spike.py`,
`evals/ig01d/build_d0_corpus.py`, `evals/baseline.py`,
`IG01-A-EVALUATION-CONTRACT.md:243`, `scripts/context-compiler.py:314-367`,
`retrieval_decision_v2/engine.py`, `scripts/memory-retriever.py:73-84`,
`scripts/hybrid-search.py`, `scripts/semantic-search.py:41-49`,
`brain_eleven/retrieval/embedding_provider.py:359-410`.
