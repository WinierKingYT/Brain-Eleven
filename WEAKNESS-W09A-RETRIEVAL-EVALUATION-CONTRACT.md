# W-09A — Retrieval Evaluation Truth Foundation Contract

**Status:** CONTRACT / IMPLEMENTATION NOT AUTHORIZED  
**Program:** Engineering Weak-Point Improvement Goal  
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW  
**Predecessor:** W-09 Evaluation Evidence Integrity, independently `SHIP` at `c90a9ca`

## 1. Problem

The repository can run deterministic V1 and V2 context evaluations, but the
current retrieval evidence is not yet a reliable product gate. The measured
public results are weak and differ by provider; safety status, quality status,
source identity and promotion status must remain separate. A green safety
result is not proof that the selected context is useful.

The current evidence remains visible and frozen for this package:

- the current W-09 public run measures V1 and V2 on the same public inputs;
- V2 is still `SHADOW` and is not promoted;
- W-09 generic reports without a provider allowlist remain
  `evidence=unavailable`;
- no ranking, embedding, corpus-label or threshold change is authorized by
  this contract.

W-09A establishes the measurement truth needed before any retrieval change.
It does not make retrieval better by changing the retriever.

## 2. Objective

Create a reproducible, anti-gaming retrieval evaluation boundary that answers:

1. Which context items are required, acceptable, irrelevant or forbidden for
   a task?
2. How do V1 and V2 perform on exactly the same cases and candidate pools?
3. Are old-but-critical decisions retained while recent irrelevant items are
   excluded?
4. Are scope, lifecycle and forbidden-context safety gates still zero-leak?
5. Is a provider unavailable, unsupported, stale or tampered rather than
   silently treated as a score?

## 3. Bounded implementation surface

Implementation may add or tighten evaluation-only code and tests in:

- `evals/` retrieval corpus/schema/metrics/reporting surfaces;
- focused `tests/` for the evaluator and report boundary;
- public synthetic fixtures and versioned evaluation documentation.

The implementation must preserve the W-09 status and evidence model, including
source/corpus fingerprints, explicit `evaluation_status`, content-free errors,
and `promotion=blocked` when required evidence or quality is unavailable.

No production retrieval or memory behavior may change in W-09A.

## 4. Frozen input and split rules

### 4.1 Dataset classes

The evaluator must distinguish:

- **PUBLIC SYNTHETIC:** repository-committed, deterministic, reviewable;
- **PRIVATE REALISTIC:** local-only, never committed with raw prompts or
  memory content;
- **SANITIZED REAL FAILURES:** versioned only after secrets and private content
  are removed.

### 4.2 Public split

Public measurement uses `DEV + TEST` only. `HOLDOUT` is never read for public
metrics, threshold selection, provider tuning, or fixture repair. Every report
must carry ordered case IDs, split identity and a source/corpus fingerprint.

The holdout labels are immutable for a corpus version. Any changed case,
label, required/acceptable/forbidden set, or answerability decision requires a
new corpus version; `ig-eval-v1` and later versions are never silently edited.

### 4.3 Answerability

Each case must state whether a competent system can infer the expected result
from the query and available context. `answerability.status=NO` cases are
excluded from quality aggregates and counted in an explicit excluded-case
status. They cannot be used to lower or raise a provider score.

## 5. Retrieval case contract

Each public case contains, at minimum:

```text
case_id, family, category, language, query, project_id,
candidate_ids, required_ids, acceptable_ids, forbidden_ids,
mandatory_ids, rationale, answerability, provenance, split
```

Families must cover exact relevance, paraphrase, related meaning, old critical
decision, current state, blocker/lesson, recent irrelevant distractor,
same-keyword wrong meaning, wrong project, superseded decision, resolved
blocker, preference and historical context. Turkish, English and mixed
technical language are required.

Selection-everything and selection-none controls are mandatory. A provider
must not obtain a good result by selecting every candidate: precision, noise
and token waste are required metrics alongside recall.

## 6. Metrics and hard gates

For a fixed `K` and the same candidate pool, report at least:

- Precision@K, Recall@K and F1;
- MRR/rank quality;
- mandatory-context recall;
- noise ratio and token waste;
- selected count and context size/latency where available.

Safety gates are evaluated per case and cannot be hidden by aggregate averages:

```text
wrong_project_leakage = 0
forbidden_leakage = 0
superseded_leakage = 0
resolved_leakage = 0
```

One applicable safety failure is a hard failure. Unsupported required safety
capabilities are also non-passing. Quality being unavailable is explicit and
blocks promotion; it is never represented as zero or as a passing gate.

The contract floor remains `context precision >= 0.60` and `mandatory recall
>= 0.80`. The desired product target is precision `>= 0.75` and mandatory
recall `>= 0.90`; these targets are recorded, not silently changed during
implementation.

## 7. V1/V2 comparison boundary

V1 and V2 must run against the identical versioned cases, candidate IDs,
labels, project scope and `K`. The report must show both sides for precision,
mandatory recall, noise and context size. V2 may be declared better only when:

- V2 precision is strictly greater than V1;
- V2 mandatory recall meets the accepted V1-equivalent threshold;
- all safety gates remain zero-leak;
- evidence is `verified` and quality is `measured`.

No V2 default/canary/promotion, rollback change or SessionStart change is part
of W-09A.

## 8. Provider and anti-gaming rules

Provider IDs and roles are bounded identifiers. A missing semantic/embedding
provider must report `SEMANTIC_UNAVAILABLE` (or the existing bounded
unavailable code) with `quality=unavailable`, `measurement=incomplete` and
`promotion=blocked`. Random vectors, fabricated confidence or lexical output
must not be labelled semantic evidence.

Weight tuning, embedding-provider migration, corpus relabeling and threshold
tuning against HOLDOUT are forbidden. Any parameter selection uses DEV only;
VALIDATION is for architecture decisions, and HOLDOUT is final read-only
evidence.

## 9. Reproducible evidence

The package must provide deterministic commands for:

```text
V1 public report
V2 public report
V1/V2 same-input comparison
selection-all and selection-none controls
HOLDOUT read guard
source/corpus fingerprint reconciliation
```

The package report records exact revision, commands, public split fingerprint,
report hashes, case counts, before/after metrics, safety status, unavailable
provider status, known limitations and open failures. No raw prompts,
transcripts, memory contents or credentials may enter the report.

## 10. Exit gate

W-09A is `SHIP` only when all are true:

- evaluation contract, corpus schema and version/split policy are frozen;
- public synthetic retrieval cases include realistic distractors and
  Turkish/English/mixed-language coverage;
- answerability and excluded-case handling are tested;
- V1/V2 use identical inputs and comparison output is deterministic;
- precision/recall/F1/MRR/mandatory recall/noise/token-waste metrics are tested;
- select-all, select-none, wrong-project, forbidden, superseded and resolved
  safety controls are tested;
- unavailable-provider status is explicit and promotion-blocking;
- HOLDOUT is unread by public evaluation and its labels remain unchanged;
- source/corpus fingerprints and report hashes independently reproduce;
- focused tests, full regression, critical flake8, compile/import and diff
  checks pass;
- independent read-only review returns exactly `SHIP`.

Any open P0, safety leakage, holdout read, unbounded report input or
unexplained V1/V2 input mismatch leaves the package `FIX-FIRST` or `RETHINK`.

## 11. Explicit exclusions

W-09A does not authorize:

- retrieval ranking or task-understanding changes;
- embedding provider migration, local Qwen integration or random-vector
  fallback;
- semantic extraction, correction/lifecycle changes or memory writes;
- V2 runtime promotion, canary/default rollout or rollback changes;
- capture/worker changes, architecture consolidation, reminder delivery,
  Phase 20 or Knowledge Engine work;
- editing existing corpus labels, thresholds, HOLDOUT or historical baselines
  to make results pass.

## 12. Package report template

```text
PACKAGE: W-09A
REVISION:
OBJECTIVE:
FILES CHANGED:
ROOT CAUSES ADDRESSED:
TESTS ADDED:
TESTS EXECUTED:
QUALITY METRICS BEFORE:
QUALITY METRICS AFTER:
SAFETY METRICS:
KNOWN LIMITATIONS:
OPEN FAILURES:
INDEPENDENT REVIEW: REVIEW PENDING
SCORE BEFORE:
SCORE AFTER:
VERDICT: REVIEW PENDING
```

**Plan status: REVIEW PENDING — implementation has not started.**
