# D0 Recheck — fair-metric rescoring and a real lexical+semantic hybrid

**Status:** GENERATED EVIDENCE. Evaluation-only, following the request in
`D0-RECHECK-FINDINGS.md`. Does not modify `evals/ig01d/d0_rethink.py`,
`evals/ig01d/spike.py`, `IG01-A-EVALUATION-CONTRACT.md`, or any production
retrieval path (`scripts/context-compiler.py`, `scripts/hybrid-search.py`,
`context_router/`, `retrieval_decision_v2/` beyond reading `engine.py`,
`brain_eleven/runtime/`). Does not touch canonical memory or vault content.
Does not reopen the D1 decision — that remains the project owner's call.
All numbers below were produced in this session and can be reproduced with
the exact commands shown.

**New files:** `evals/ig01d/d0_recheck.py` (script, imports from
`d0_rethink.py`/`spike.py`, does not edit them), `evals/ig01d/d0-recheck-mpnet.json`
and `evals/ig01d/d0-recheck-e5large.json` (raw per-variant/per-language
aggregate output — schema-identical in spirit to `d0-probe-real*.json` but
covering three variants each, produced by this recheck).

## 0. Environment note (read this before the numbers)

The evaluation container had **no** `torch`, **no** `sentence-transformers`,
and no cached Hugging Face models — none of `d0_rethink.py`'s
`local_files_only=True` provider constructions could have succeeded as-is.
This was verified directly (`python3 -c "import torch"` → `ModuleNotFoundError`,
`ls ~/.cache/huggingface` → does not exist) before any other work.

Outbound HTTPS to `pypi.org`, `download.pytorch.org`, and `huggingface.co`
was reachable through the environment's proxy, so real local models were
installed and downloaded for this recheck rather than substituting a
fabricated or hash-based score:

```
pip install torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu   # later upgraded, see below
pip install sentence-transformers                                            # pulled transformers 5.17.0, which requires torch>=2.5
pip install "torch>=2.5,<2.9" --index-url https://download.pytorch.org/whl/cpu   # resolved to torch 2.8.0+cpu
```

Installed versions actually used: `torch==2.8.0+cpu`, `sentence-transformers==6.0.1`.
This changes only the Python environment the eval runs in, not the repository.

Both models measured are the same two the original D0 run measured
(`CODEX-RESULTS-D0.md`'s "best measured" MPNet arm, and the
`intfloat/multilingual-e5-large` tuned arm), downloaded fresh from Hugging
Face into this container's cache:

- `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` (embedding)
- `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (reranker)
- `intfloat/multilingual-e5-large` (embedding, `query:`/`passage:` prefixed via `d0_rethink._E5PrefixedProvider`, reused unmodified)

No embedding or reranker score in this document is fabricated, hash-seeded,
or estimated — every number below comes from a real forward pass of one of
these two local models against the same corpus and vault construction
`d0_rethink.py` uses (same `SEED=17`, `NOISE_COUNT=24`, same
`ig-r3-d0-v1` corpus).

## 1. Pipeline fidelity check

Before trusting any new number, the recheck script's semantic-only and
query-blind-hybrid variants were checked against the original saved
`mpnet_scope_filtered` / `mpnet_hybrid` aggregates from
`d0-probe-real-exact.json`, since they exercise the same code path
(`d0_rethink._rank_semantic`, same vault seed/noise) with only script
identity different (aggregation function rewritten independently, not
reused, precisely so this comparison is a real check and not a tautology).

| | original `mpnet_scope_filtered` | recheck `semantic_only` |
|---|---:|---:|
| precision@5 | 0.205000 | 0.204999999999999**57** |
| mandatory_recall (=recall@5) | 0.704167 | 0.704166666666666**7** |
| MRR | 0.484583 | 0.484583333333333**5** |

| | original `mpnet_hybrid` (query-blind) | recheck `hybrid_baseline_blind` |
|---|---:|---:|
| precision@5 | 0.185000 | 0.184999999999999**6** |
| mandatory_recall | 0.804167 | 0.804166666666666**7** |
| MRR | 0.480833 | 0.480833333333333**56** |

Per-language breakdowns match the same way (e.g. `en` precision 0.230/0.230,
`en` recall 0.75/0.75 for `semantic_only`; full breakdown in
`d0-recheck-mpnet.json`). The differences are floating-point summation-order
noise at the 14th–15th decimal digit, not a methodology difference. This
gives confidence that the corrected-precision and lexical-hybrid numbers
below, produced by the same regenerated per-case rankings, are measuring
the same thing the original evidence measured.

## 2. Experiment 1 — fair-metric rescoring

### 2.1 Per-case rankings: not present in either saved evidence file

```
python3 -c "
import json
for f in ['evals/ig01d/d0-probe-real-exact.json','evals/ig01d/d0-probe-real.json']:
    d = json.load(open(f))
    print(f, sorted(d.keys()))
"
```
Both files expose only `variants.<name>.metrics` and
`variants.<name>.per_language.<lang>.metrics` — aggregate scalars, no
per-case retrieved-id lists. Per-case rankings were therefore regenerated
by re-running `d0_rethink._rank_semantic` (unmodified) against the same
corpus/vault/seed, via the new `evals/ig01d/d0_recheck.py`.

### 2.2 Oracle ceiling, independently verified

```
python3 -c "
import json
rows = [json.loads(l) for l in open('evals/ig01d/public/ig-r3-d0-v1/retrieval.jsonl') if l.strip()]
print(len(rows))
counts = {}
scores = []
for r in rows:
    rel = set(r['expected_context']['required']) | set(r['expected_context']['useful'])
    counts[len(rel)] = counts.get(len(rel), 0) + 1
    scores.append(min(len(rel), 5) / 5)
print(counts)
print(sum(scores)/len(scores))
"
```
Output: `120` cases, `{2: 105, 3: 15}`, oracle precision@5 mean =
**0.42499999999999905**. This matches `D0-RECHECK-FINDINGS.md`'s cited
0.425 and `IG01-A-EVALUATION-CONTRACT.md:243`'s worked example
(`3 relevant in top 5 → 0.60`) implicitly assumed 3-relevant cases, which
are only 15/120 (12.5%) of this corpus; the other 105/120 (87.5%) have only
2 relevant items and can never reach precision@5 above 0.40 regardless of
retrieval quality.

### 2.3 Corrected metrics, MPNet (the original "best measured" model)

Command:
```
python3 -m evals.ig01d.d0_recheck --output evals/ig01d/d0-recheck-mpnet.json \
  --embedding-model sentence-transformers/paraphrase-multilingual-mpnet-base-v2 \
  --reranker-model cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 --local-files-only
```

`semantic_only` variant, n=120:

| Metric | Value |
|---|---:|
| precision@5 (original flawed metric) | 0.205000 |
| precision@min(5,\|relevant\|) (corrected) | 0.259722 |
| recall@5 (mandatory_recall) | 0.704167 |
| MRR | 0.484583 |

- precision@5 measured (0.205) against the verified oracle ceiling (0.425):
  **48.2%** of the achievable score on that metric — matches
  `D0-RECHECK-FINDINGS.md`'s "~48%" figure, independently reproduced here
  from freshly regenerated rankings rather than cited from the prior
  aggregate-only evidence.
- precision@min(5,\|relevant\|) is **0.259722**, about 27% higher than the
  flawed precision@5 (0.205) for the same rankings — the gap is exactly the
  effect the flawed metric's fixed `k=5` denominator has on a corpus where
  87.5% of cases have only 2 gold-relevant items. This metric's own oracle
  ceiling is 1.0 by construction (a perfect retriever always fills its
  top-`min(5,|relevant|)` slots with relevant items), so 0.259722 should be
  read as "26.0% of a perfect top-k precision on this corpus," a
  meaningfully different (worse-looking) picture than the 48.2%-of-ceiling
  reading of precision@5 — the two corrected views do not agree on how far
  above/below halfway this model is, which is itself worth noting rather
  than picking whichever reads better.

Per-language and safety counters: see `evals/ig01d/d0-recheck-mpnet.json`,
`variants.semantic_only`. `wrong_project_leakage`, `forbidden_leakage`,
`superseded_leakage`, `resolved_leakage` are all 0, consistent with D0-1.

## 3. Experiment 2 — real query-aware lexical+semantic hybrid

### 3.1 Lexical scorer selection

Two candidates were read in full:

- `retrieval_decision_v2/engine.py:24-30`, `_text_scores(query, texts)` — a
  module-level function taking a query string and a `{id: text}` mapping
  directly, returning `({id: idf_overlap_score}, has_query_terms)`. IDF term
  weights are computed over the candidate set itself; terms are extracted
  with `_terms()` (`engine.py:20-21`, regex word split, length>2, digits and
  a bilingual EN/TR stopword list filtered via `_QUERY_STOP`). No class
  instantiation, no router/authority state required.
- `scripts/memory-retriever.py:73-84`, `MemoryRetriever._similarity_score` —
  plain Jaccard word overlap, but it is a bound method on `MemoryRetriever`,
  which loads memories from a vault path in `__init__` and is otherwise
  wired for the full retrieval CLI, not just scoring one query against an
  arbitrary candidate dict.

`_text_scores` was used: it is standalone and needs only `(query, {id: text})`,
matching the task's "easier to invoke standalone against the D0 corpus's
candidate pool" criterion, and it already has bilingual (EN/TR) stopword
handling appropriate for this corpus's three language buckets.

`evals/ig01d/d0_recheck.py:_lexical_rank` calls it against the same
scope-filtered candidate pool `d0_rethink._rank_semantic` uses
(`spike._allowed_records(records, task.project_id)`), ranks by descending
score with a deterministic `memory_id` tie-break (ties are common: many
candidates share a 0.0 score for a given task prompt once template
scaffolding words are stopword-filtered — see §3.3), and RRF-fuses
(`d0_rethink._rrf`, reused unmodified) with the same semantic ranking used
in Experiment 1.

### 3.2 Three variants, one shared semantic ranking

All three share the identical per-case semantic ranking (computed once and
reused, not re-run per variant), so any difference between variants is
attributable only to what it was fused with:

- `semantic_only` — no fusion (Experiment 1's ranking).
- `hybrid_baseline_blind` — RRF-fused with `BaselineContextProvider`
  (`evals/baseline.py`), which does not receive `task.prompt`
  (`baseline.py:150-152`). Reproduces `d0_rethink.py`'s `mpnet_hybrid`.
- `hybrid_lexical_query_aware` — RRF-fused with `_text_scores` ranked
  against `task.prompt`.

MPNet results, n=120 each:

| Variant | precision@5 | precision@min(5,\|rel\|) | recall@5 | MRR |
|---|---:|---:|---:|---:|
| semantic_only | 0.205000 | 0.259722 | 0.704167 | 0.484583 |
| hybrid_baseline_blind (query-blind control) | 0.185000 | 0.230556 | 0.804167 | 0.480833 |
| hybrid_lexical_query_aware (this recheck) | 0.215000 | 0.233333 | 0.754167 | 0.466111 |

Safety counters (`wrong_project_leakage`, `forbidden_leakage`,
`superseded_leakage`, `resolved_leakage`) are 0 for all three variants.

### 3.3 Reading these numbers

- On raw precision@5, the real lexical hybrid (0.215) beats both
  semantic-only (0.205) and the query-blind control (0.185) — the ordering
  `D0-RECHECK-FINDINGS.md` predicted (a genuinely query-aware lexical
  partner should do less harm than a query-blind one) holds here.
- On the corrected precision@min(5,\|relevant\|), semantic-only is highest
  (0.259722); both hybrids are close to each other and below it
  (0.233333 lexical vs 0.230556 blind) — the real lexical partner is only
  marginally better than the broken one on this metric, and neither hybrid
  variant beats semantic-only alone.
- On recall@5, the query-blind hybrid is *higher* (0.804167) than the
  lexical hybrid (0.754167), which is itself higher than semantic-only
  (0.704167) — both hybrids trade some precision-side gain for recall, but
  the blind one trades more.
- On MRR, semantic-only (0.484583) and the blind hybrid (0.480833) are
  close; the lexical hybrid is lowest (0.466111).
- No single ranking is best on all four metrics simultaneously. The two
  hybrid variants are close to each other on 3 of 4 metrics
  (precision@min5rel, recall@5, MRR), and clearly separated only on raw
  precision@5 — where the *query-aware* fusion partner does help
  (0.215 vs 0.185), consistent with the theory in
  `D0-RECHECK-FINDINGS.md` §3, but the effect is modest and does not carry
  through to the corrected metric or to MRR.
- Inspecting individual cases (e.g. `ig-r3-d0-en-p15_authority_future_001`,
  see reproduction command below) shows many candidates receive an
  identical `_text_scores` score of `0.0` for a given prompt: this corpus's
  task prompts are templated (`build_d0_corpus.py`) and much of their
  wording — including the literal Turkish/English word "decision"/`karar`
  — is in `_QUERY_STOP` (`engine.py:17`), leaving only a handful of
  distinguishing content words per prompt. `_text_scores` was built for
  PRE-08's live retrieval-decision flow, not tuned against this eval
  corpus's template wording, and that mismatch is visible in the large
  number of tied 0.0 lexical scores per case (deterministic
  `memory_id`-order tie-break in `d0_recheck._lexical_rank`).

Command:
```
python3 -m evals.ig01d.d0_recheck --output evals/ig01d/d0-recheck-mpnet.json \
  --embedding-model sentence-transformers/paraphrase-multilingual-mpnet-base-v2 \
  --reranker-model cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 --local-files-only
```

## 4. E5-large: available and measured

Unlike the fair-metric-rescoring-only fallback the task anticipated for an
unavailable model, `intfloat/multilingual-e5-large` (the exact model the
original D0 run used, per `CODEX-RESULTS-D0.md`'s `tuned_scope_filtered` /
`tuned_hybrid` rows) downloaded successfully from Hugging Face
(`huggingface.co` was reachable through this container's proxy) and was
measured in full, using `d0_rethink._E5PrefixedProvider` unmodified for the
required `query:`/`passage:` prefix contract.

Command:
```
python3 -m evals.ig01d.d0_recheck --output evals/ig01d/d0-recheck-e5large.json \
  --embedding-model intfloat/multilingual-e5-large \
  --reranker-model cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 --e5-prefix
```
(`--local-files-only` omitted on this call since the model was not yet
cached; the download itself, ~2.1GB, happened as part of this command.)

### 4.1 Second pipeline-fidelity check

| | original `tuned_scope_filtered` | recheck `semantic_only` (E5) |
|---|---:|---:|
| precision@5 | 0.190000 | 0.18999999999999964 |
| mandatory_recall | 0.641667 | 0.6416666666666667 |
| MRR | 0.460972 | 0.4609722222222224 |

| | original `tuned_hybrid` (E5 + query-blind RRF) | recheck `hybrid_baseline_blind` (E5) |
|---|---:|---:|
| precision@5 | 0.201667 | 0.20166666666666627 |
| mandatory_recall | 0.812500 | 0.8125 |
| MRR | 0.473194 | 0.47319444444444475 |

Exact match (to floating-point summation noise) again, on a second,
independently-downloaded model — this is the second, independent
confirmation that the recheck pipeline reproduces the original evidence
faithfully, not just for MPNet.

### 4.2 All four metrics, E5-large, n=120

| Variant | precision@5 | precision@min(5,\|rel\|) | recall@5 | MRR |
|---|---:|---:|---:|---:|
| semantic_only | 0.190000 | 0.251389 | 0.641667 | 0.460972 |
| hybrid_baseline_blind (query-blind control) | 0.201667 | 0.222222 | 0.812500 | 0.473194 |
| hybrid_lexical_query_aware (this recheck) | 0.185000 | 0.233333 | 0.679167 | 0.446250 |

Safety counters are 0 for all three variants (`wrong_project_leakage`,
`forbidden_leakage`, `superseded_leakage`, `resolved_leakage`).

### 4.3 The lexical-hybrid effect is not consistent across the two models

This is the headline finding of Experiment 2: the same real, query-aware
lexical scorer (`_text_scores`), fused the same way (RRF), against the same
corpus and candidate pool, has **opposite** signs depending on which
embedding model it is fused with:

| | MPNet | E5-large |
|---|---:|---:|
| semantic_only precision@5 | 0.205000 | 0.190000 |
| hybrid_baseline_blind precision@5 (query-blind) | 0.185000 | 0.201667 |
| hybrid_lexical_query_aware precision@5 (this recheck) | **0.215000** (best of the three) | **0.185000** (worst of the three) |

For MPNet, the real lexical hybrid is the best of the three variants on
precision@5. For E5-large, it is the *worst* — worse than both
semantic-only and the query-blind control on precision@5, and it has the
lowest MRR (0.446250) and lowest recall@5 relative to the query-blind
hybrid (0.679167 vs 0.812500) of the three E5 variants.

This means the specific claim "a real query-aware lexical hybrid helps" is
not supported unconditionally — it held for one embedding model on this
corpus and did not hold for the other. `D0-RECHECK-FINDINGS.md` §3's
argument (a query-blind fusion partner dilutes the semantic signal with
noise, so its poor showing does not prove a genuine hybrid would fail) is
still correct as a critique of the *original* control's construction — but
this recheck shows the corrected experiment does not settle into a single
"hybrids help" or "hybrids don't help" verdict either; it is
model-dependent on this corpus.

## 5. What this recheck does and does not claim

- Confirms, on freshly regenerated per-case rankings (not just cited
  aggregates), that `D0-RECHECK-FINDINGS.md`'s three load-bearing numbers
  hold: oracle ceiling 0.425, MPNet precision@5 0.205 (~48% of ceiling),
  and the original "hybrid doesn't help" evidence used a query-blind
  fusion partner.
- Shows the corrected precision@min(5,\|relevant\|) metric (0.259722 for
  MPNet semantic-only) tells a *different* story from "48% of ceiling":
  read on its own 0-to-1 scale it is closer to a quarter than a half.
  Neither framing is more "correct" than the other; they answer different
  questions (share of the theoretical best top-5 vs. standard
  precision-at-k with a case-appropriate k), and this document reports
  both rather than picking one.
- Shows a real query-aware lexical partner (`_text_scores`) produces a
  modestly better hybrid than the query-blind control on raw precision@5
  for MPNet (0.215 vs 0.185) but a *worse* one for E5-large (0.185 vs
  0.201667) — see §4.3. So "a genuine lexical hybrid was never tested"
  (true, per `D0-RECHECK-FINDINGS.md` §3) does not by itself imply a
  genuine hybrid would have changed D0's headline conclusion in one
  direction; on this corpus, with this lexical scorer, the effect is
  model-dependent and does not clearly beat semantic-only on most metrics
  for either model.
- Does not claim embedding retrieval, corrected-metric or hybrid, closes
  the gap to any threshold in `IG01-A-EVALUATION-CONTRACT.md`. Does not
  claim D1 (`BRANCH_B`) should be reversed. That remains the project
  owner's decision; this document only supplies more complete, honestly
  labeled evidence for it.
- Every embedding/reranker number in this document came from a real local
  model forward pass in this container (§0); none is fabricated,
  hash-seeded, or estimated. Both models the original D0 run measured
  (MPNet, and the tuned `intfloat/multilingual-e5-large`) were available
  and measured here — this environment had outbound access to download
  them, unlike whatever produced `d0-probe-real*.json`'s aggregate-only
  evidence (which shows no per-case data was retained either way).

## 6. Reproduction

```
# per-case rescoring + real lexical hybrid, MPNet (matches original headline model)
python3 -m evals.ig01d.d0_recheck --output evals/ig01d/d0-recheck-mpnet.json \
  --embedding-model sentence-transformers/paraphrase-multilingual-mpnet-base-v2 \
  --reranker-model cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 --local-files-only

# same, E5-large with the query:/passage: prefix contract (matches original tuned model)
python3 -m evals.ig01d.d0_recheck --output evals/ig01d/d0-recheck-e5large.json \
  --embedding-model intfloat/multilingual-e5-large \
  --reranker-model cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 --e5-prefix --local-files-only

# oracle ceiling
python3 -c "
import json
rows = [json.loads(l) for l in open('evals/ig01d/public/ig-r3-d0-v1/retrieval.jsonl') if l.strip()]
scores = [min(len(set(r['expected_context']['required'])|set(r['expected_context']['useful'])), 5)/5 for r in rows]
print(len(rows), sum(scores)/len(scores))
"
```

**Key files:** `evals/ig01d/d0_recheck.py`, `evals/ig01d/d0-recheck-mpnet.json`,
`evals/ig01d/d0-recheck-e5large.json`, `evals/ig01d/d0_rethink.py` (read,
not modified), `evals/ig01d/spike.py` (read, not modified),
`retrieval_decision_v2/engine.py:_text_scores` (read, not modified),
`scripts/memory-retriever.py:73-84` (read, not used — see §3.1),
`evals/ig01d/public/ig-r3-d0-v1/retrieval.jsonl`.
