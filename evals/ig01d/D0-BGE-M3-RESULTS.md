# D0 BGE-M3 — actually measuring the candidate that was never run

**Status:** GENERATED EVIDENCE. Evaluation-only, following the task in
`D0-RECHECK-RESULTS.md` §"Longer-term, lower-priority gaps identified but
not yet actioned": *"A second embedding model (`BAAI/bge-m3`) was listed as
a D0 candidate but never actually run — `_try_tuned_provider`
(`d0_rethink.py:280-311`) stops at the first success (E5-large)."* This
document runs it. Does not modify `evals/ig01d/d0_rethink.py`,
`evals/ig01d/spike.py`, or `evals/ig01d/d0_recheck.py` — it only imports
`run_recheck` (and, transitively, `_metric_row_recheck`) from
`d0_recheck.py` unmodified. Does not touch `IG01-A-EVALUATION-CONTRACT.md`,
any other contract/authority document, production retrieval paths
(`scripts/context-compiler.py`, `scripts/hybrid-search.py`,
`context_router/`, `retrieval_decision_v2/` beyond reading `engine.py`,
`brain_eleven/runtime/`), or canonical memory/vault content. Does not
reopen the D1 decision or state a verdict on Branch A — that remains the
project owner's call. All numbers below were produced in this session and
can be reproduced with the exact commands shown.

**New files:** `evals/ig01d/d0_bge_m3.py` (script, imports `run_recheck`
from `d0_recheck.py`, does not edit it), `evals/ig01d/d0-recheck-bge-m3.json`
(raw per-variant/per-language aggregate output, schema-identical to
`d0-recheck-mpnet.json`/`d0-recheck-e5large.json` since it is produced by
the same `run_recheck` function).

## 0. Environment note and scope of what was measured

`torch==2.8.0+cpu` and `sentence-transformers==6.0.1` were already installed
in this container from the prior D0 recheck session (`D0-RECHECK-RESULTS.md`
§0); this session reused them rather than reinstalling. Outbound HTTPS to
`huggingface.co` was reachable through the environment's configured proxy
(verified with a direct `curl` to a model file before doing anything else,
HTTP 307 redirect — normal HF CDN behavior, not a failure).

Two models were downloaded fresh into this container's Hugging Face cache
and verified to load and run correctly **before** writing any eval code:

- `BAAI/bge-m3` (embedding) — loaded via
  `sentence_transformers.SentenceTransformer`, the exact class
  `LocalSentenceTransformerProvider` (`brain_eleven/retrieval/embedding_provider.py:212-228`)
  wraps. `.encode(["hello world", "merhaba dunya"])` returned a `(2, 1024)`
  array — ordinary dense sentence embeddings, load+first-encode ≈27s.
- `BAAI/bge-reranker-v2-m3` (reranker) — loaded via
  `sentence_transformers.CrossEncoder`, the exact class
  `LocalCrossEncoderReranker` (`brain_eleven/retrieval/embedding_provider.py:275-291`)
  wraps. `.predict()` on a relevant/irrelevant pair returned sane scores
  (`0.9997` vs `0.000017`), load+first-predict ≈20s.

Both are exactly the pair `d0_rethink.py`'s `_try_tuned_provider`
(`d0_rethink.py:279-328`) already lists as its second candidate —
`("BAAI/bge-m3", "BAAI/bge-reranker-v2-m3", False)` — but that function
returns as soon as its first candidate (`intfloat/multilingual-e5-large`)
succeeds, so this pair was never actually exercised until this session.

**Scope limitation, as flagged by the task before starting:** BGE-M3 is
architecturally a dense+sparse+ColBERT multi-vector retrieval model. Only
its **dense** embedding output is measured here — the mode
`sentence_transformers.SentenceTransformer.encode()` returns, and the same
mode `LocalSentenceTransformerProvider` already uses for MPNet and
E5-large, making it the directly comparable one. The sparse (lexical
weight) and ColBERT (multi-vector, token-level MaxSim) modes require the
separate `FlagEmbedding` package (`import FlagEmbedding` fails in this
environment — not installed, and installing it plus a MaxSim/sparse scoring
path would mean writing new retrieval-scoring code, since `_rank_semantic`
(`spike.py:173-198`) only implements single-vector cosine similarity
followed by cross-encoder reranking). Per the task's own instruction —
*"don't attempt the sparse/multi-vector modes unless they're trivial ...
stick to dense embeddings and note the limitation"* — this was judged to be
real engineering effort, not a cheap swap-in, so only the dense mode was
run. This is a genuine limitation of what follows: it does not say anything
about BGE-M3's sparse or ColBERT retrieval quality, only its dense output.

## 1. Pipeline correctness: inherited, not re-derived

`D0-RECHECK-RESULTS.md` §1 and §4.1 already fidelity-checked
`d0_recheck.py`'s `run_recheck` pipeline twice — once against the original
saved `mpnet_scope_filtered`/`mpnet_hybrid` aggregates, once against
`tuned_scope_filtered`/`tuned_hybrid` (E5-large) — and both matched the
original D0 evidence to floating-point noise. `evals/ig01d/d0_bge_m3.py`
calls `run_recheck` directly, unmodified, with a different
`embedding_provider`/`reranker` pair; it does not touch
`_rank_semantic`, `_rrf`, `_metric_row_recheck`, `_lexical_rank`, or the
vault/corpus construction. There is no prior BGE-M3 aggregate to check
against (that is the entire reason this experiment exists), so no new
fidelity table is possible here — but the harness producing these numbers
is the same one already independently verified twice, run through an
unmodified entry point.

## 2. Command

```
python3 -m evals.ig01d.d0_bge_m3 --output evals/ig01d/d0-recheck-bge-m3.json --local-files-only
```

(`--local-files-only` was safe to pass because both models had already been
downloaded and cached in the loading check in §0; a first, uncached run
would omit that flag exactly as `d0_recheck.py`'s README-equivalent command
for E5-large did.) Ran against `evals/ig01d/public/ig-r3-d0-v1/` (120 cases,
`SEED=17`, `NOISE_COUNT=24` — same corpus/vault/seed as the MPNet and
E5-large recheck runs), at git SHA `3127833c4f804d6d7dca6cac83b9046892e4cede`
(recorded in `d0-recheck-bge-m3.json`'s `source.git_sha`, matching the
`master` HEAD this task started from). Wall time ≈5 minutes (model loading
dominates; 120 cases × 3 RRF variants sharing one semantic ranking per case,
CPU-only, 4 cores).

## 3. All four metrics, three variants, n=120

| Variant | precision@5 | precision@min(5,\|rel\|) | recall@5 | MRR |
|---|---:|---:|---:|---:|
| semantic_only | 0.186667 | 0.251389 | 0.637500 | 0.458056 |
| hybrid_baseline_blind (query-blind control) | 0.200000 | 0.233333 | 0.800000 | 0.492361 |
| hybrid_lexical_query_aware | 0.195000 | 0.234722 | 0.758333 | 0.469861 |

Safety counters (`wrong_project_leakage`, `forbidden_leakage`,
`superseded_leakage`, `resolved_leakage`) are 0 for all three variants —
consistent with both MPNet and E5-large.

Per-language breakdown (from `d0-recheck-bge-m3.json`):

| Variant | Language | n | precision@5 | precision@min(5,\|rel\|) | recall@5 | MRR |
|---|---|---:|---:|---:|---:|---:|
| semantic_only | en | 40 | 0.2050 | 0.2500 | 0.6875 | 0.4567 |
| semantic_only | tr | 40 | 0.1850 | 0.2042 | 0.7125 | 0.4304 |
| semantic_only | tr-en | 40 | 0.1700 | 0.3000 | 0.5125 | 0.4871 |
| hybrid_baseline_blind | en | 40 | 0.1950 | 0.2042 | 0.7875 | 0.4921 |
| hybrid_baseline_blind | tr | 40 | 0.1900 | 0.2417 | 0.8250 | 0.4800 |
| hybrid_baseline_blind | tr-en | 40 | 0.2150 | 0.2542 | 0.7875 | 0.5050 |
| hybrid_lexical_query_aware | en | 40 | 0.2000 | 0.2500 | 0.8000 | 0.4721 |
| hybrid_lexical_query_aware | tr | 40 | 0.1900 | 0.2542 | 0.7500 | 0.4829 |
| hybrid_lexical_query_aware | tr-en | 40 | 0.1950 | 0.2000 | 0.7250 | 0.4546 |

Oracle precision@5 ceiling on this corpus (unchanged, model-independent,
reproduced again as part of this run): **0.424999999999999**, matching
`D0-RECHECK-FINDINGS.md` and `D0-RECHECK-RESULTS.md`.

## 4. Direct comparison: MPNet vs. E5-large vs. BGE-M3 (dense)

All three rows below come from the same `run_recheck` function, same
corpus/vault/seed, same `_metric_row_recheck` scoring — only the embedding
model (and, for BGE-M3/E5-large, the reranker) differs.

### 4.1 `semantic_only` (no RRF fusion)

| Model | precision@5 | precision@min(5,\|rel\|) | recall@5 | MRR |
|---|---:|---:|---:|---:|
| MPNet (`paraphrase-multilingual-mpnet-base-v2`) | **0.205000** | **0.259722** | **0.704167** | **0.484583** |
| E5-large (`multilingual-e5-large`) | 0.190000 | 0.251389 | 0.641667 | 0.460972 |
| BGE-M3 (`bge-m3`, dense) | 0.186667 | 0.251389 | 0.637500 | 0.458056 |

MPNet leads on all four metrics for the unfused semantic ranking. BGE-M3 is
the lowest of the three on raw precision@5, recall@5, and MRR — but only by
a small margin from E5-large (≤0.003 on precision@min5rel, MRR, and
recall@5 is within 0.6 points). On precision@min(5,\|relevant\|), BGE-M3 and
E5-large are effectively tied (0.2513888888888889 vs. 0.25138888888888883 —
equal to 13 significant figures; this is very likely a real coincidence
from two different rankings producing the same aggregate mean over 120
cases with only two possible per-case denominators (2 or 3), not a
methodology artifact — both were computed via the same unmodified
`_metric_row_recheck`, and their raw precision@5 values, which use the
same aggregation over different per-case rankings, differ (0.190 vs.
0.186667)).

### 4.2 `hybrid_baseline_blind` (query-blind RRF control)

| Model | precision@5 | precision@min(5,\|rel\|) | recall@5 | MRR |
|---|---:|---:|---:|---:|
| MPNet | 0.185000 | 0.230556 | 0.804167 | 0.480833 |
| E5-large | **0.201667** | 0.222222 | **0.812500** | 0.473194 |
| BGE-M3 | 0.200000 | **0.233333** | 0.800000 | **0.492361** |

Here BGE-M3 has the **best MRR of the three** (0.492361) and the best
precision@min5rel (0.233333), despite having the weakest `semantic_only`
MRR of the three in §4.1 — fusing with the query-blind baseline lexical
ranker changes the ordering. No model is best on all four metrics in this
variant either.

### 4.3 `hybrid_lexical_query_aware` (real lexical+semantic hybrid)

| Model | precision@5 | precision@min(5,\|rel\|) | recall@5 | MRR |
|---|---:|---:|---:|---:|
| MPNet | **0.215000** | 0.233333 | 0.754167 | 0.466111 |
| E5-large | 0.185000 | 0.233333 | 0.679167 | 0.446250 |
| BGE-M3 | 0.195000 | **0.234722** | **0.758333** | **0.469861** |

MPNet has the best raw precision@5 here (as it did in `D0-RECHECK-RESULTS.md`
§3.2); BGE-M3 has the best of the other three metrics in this variant, and
recovers from being the worst `semantic_only` performer to the best
`hybrid_lexical_query_aware` performer on recall@5 and MRR. E5-large is the
weakest of the three on every metric in this variant.

## 5. Is BGE-M3 better, worse, or the same?

**Roughly the same as the other two, model-dependent per metric and per
variant — not a clear win or loss for BGE-M3 (dense-only mode) on this
corpus.**

- On the cleanest single comparison — `semantic_only`, no fusion, so no
  RRF interaction to explain away — MPNet is ahead of both tuned models,
  and BGE-M3 is marginally behind E5-large (by ≤0.003 on three of four
  metrics; recall@5 differs by 0.6 percentage points). This is the same
  relationship the original D0 evidence already showed for E5-large vs.
  MPNet (`tuned_scope_filtered` under-performing `mpnet_scope_filtered`,
  `D0-RECHECK-RESULTS.md` §4), extended to a third model in the same
  direction.
- Once RRF fusion enters (either hybrid variant), the ordering does not
  hold: BGE-M3 has the best MRR of the three models in
  `hybrid_baseline_blind`, and the best recall@5 and MRR (though not
  precision@5) in `hybrid_lexical_query_aware`. As `D0-RECHECK-RESULTS.md`
  §4.3 already found for the MPNet/E5-large comparison, the effect of a
  given fusion partner is **not consistent across embedding models** on
  this corpus — this recheck's addition of a third model reinforces that
  finding rather than settling it in either direction.
- No embedding model is best on all four metrics in any of the three
  variants. This matches the pattern already noted for MPNet vs. E5-large
  in `D0-RECHECK-RESULTS.md` §3.3 and §4.2 — it is not specific to adding
  BGE-M3.
- The spread between the three models on any given metric/variant cell is
  small relative to the oracle ceiling (0.425) and to the gap already
  identified between any of these models and that ceiling — e.g. the
  widest `semantic_only` precision@5 spread across all three models is
  0.205 − 0.186667 ≈ 0.018, versus a ≈0.22 gap from any of them up to the
  oracle ceiling. On this corpus, at this sample size (120 cases), the
  choice among these three specific embedding models looks like a
  second-order effect next to the corpus-ceiling and fusion-partner
  questions `D0-RECHECK-FINDINGS.md` and `D0-RECHECK-RESULTS.md` already
  raised.

## 6. What this document does and does not claim

- Confirms `BAAI/bge-m3` (dense mode) loads and runs correctly against this
  corpus via the exact tooling `d0_rethink.py`'s own `_try_tuned_provider`
  already names for it, closing the "never actually run" gap
  `D0-RECHECK-RESULTS.md` flagged.
- Does not measure BGE-M3's sparse or ColBERT (multi-vector) retrieval
  modes — see §0's scope limitation. A claim that "BGE-M3 is roughly on par
  with MPNet/E5-large" in this document refers only to its dense output.
- Does not identify a clear best embedding model among the three measured.
  Which one "wins" depends on which metric and which fusion variant is
  read, exactly as `D0-RECHECK-RESULTS.md` §4.3 already found comparing
  just MPNet and E5-large.
- Does not reopen or settle the D1 (`BRANCH_B`) decision, and does not
  claim any of these numbers clears any `IG01-A-EVALUATION-CONTRACT.md`
  threshold. That remains the project owner's call.
- Every embedding/reranker number in this document came from a real local
  model forward pass in this container; none is fabricated, hash-seeded,
  or estimated. Both models (`BAAI/bge-m3`, `BAAI/bge-reranker-v2-m3`) were
  verified to load and produce sane output (§0) before being wired into
  the eval.

## 7. Reproduction

```
# BGE-M3 (dense embedding mode) + BGE-reranker-v2-m3, same corpus/vault/seed
python3 -m evals.ig01d.d0_bge_m3 --output evals/ig01d/d0-recheck-bge-m3.json --local-files-only

# for comparison, already-measured models (unchanged from D0-RECHECK-RESULTS.md)
python3 -m evals.ig01d.d0_recheck --output evals/ig01d/d0-recheck-mpnet.json \
  --embedding-model sentence-transformers/paraphrase-multilingual-mpnet-base-v2 \
  --reranker-model cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 --local-files-only

python3 -m evals.ig01d.d0_recheck --output evals/ig01d/d0-recheck-e5large.json \
  --embedding-model intfloat/multilingual-e5-large \
  --reranker-model cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 --e5-prefix --local-files-only
```

**Key files:** `evals/ig01d/d0_bge_m3.py`, `evals/ig01d/d0-recheck-bge-m3.json`,
`evals/ig01d/d0_recheck.py` (read + imported, not modified),
`evals/ig01d/d0_rethink.py:279-328` (`_try_tuned_provider`, read, not
modified — the source of the BGE-M3 candidate this document actually runs),
`evals/ig01d/spike.py` (read, not modified),
`brain_eleven/retrieval/embedding_provider.py:212-291`
(`LocalSentenceTransformerProvider`, `LocalCrossEncoderReranker`, read, not
modified), `evals/ig01d/d0-recheck-mpnet.json`,
`evals/ig01d/d0-recheck-e5large.json` (read for comparison, not modified),
`evals/ig01d/D0-RECHECK-RESULTS.md`, `D0-RECHECK-FINDINGS.md`.
