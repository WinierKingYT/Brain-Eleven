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

W-09A freezes one exact corpus root and version:
`evals/ig01b/public/ig-eval-v2/`, manifest `corpus_version=ig-eval-v2`.
That root has exactly `dev.jsonl`, `validation.jsonl`, `holdout.jsonl` and
`abstention.jsonl`. `DEV` is iteration data, `VALIDATION` is the public
architecture-decision split, and `HOLDOUT` is the final read-only split. The
older `evals/corpus-v2/` directory is a different Phase-15 corpus and is not a
W-09A input. No `TEST` alias is used by this contract.

Public measurement may read `DEV + VALIDATION`; it may not read `HOLDOUT` for
metric calculation, parameter/threshold selection, provider tuning, fixture
repair or promotion. A separate final holdout audit may read HOLDOUT only
after all implementation decisions are frozen, and its report is never fed
back into code or public thresholds. Public and holdout commands, roots and
report paths must be distinct and recorded.

Every report must carry the split name, ordered case IDs and separate source
and corpus fingerprints. The holdout labels are immutable for a corpus
version. Any changed case, label, required/acceptable/forbidden set, or
answerability decision requires a new corpus version; `ig-eval-v1` and later
versions are never silently edited.

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

### 5.1 Set and ordering invariants

Set-like label arrays (`required_ids`, `acceptable_ids`, `forbidden_ids` and
`mandatory_ids`) are sorted, unique, bounded identifiers. Ranked arrays
(`candidate_ids` and a provider's `selected_ids`) preserve meaningful order;
they are unique bounded identifiers but are not sorted. Their ordered values
are fingerprinted separately. `required_ids`, `acceptable_ids`,
`forbidden_ids` and `mandatory_ids` are subsets of the candidate set;
`mandatory_ids` is a subset of `required_ids`; forbidden IDs are disjoint from
required and acceptable IDs. Candidate content metadata has one stable ID per
case. A case violating these invariants is invalid and is
excluded from quality aggregates with an explicit invalid status; it is never
silently repaired by the evaluator.

`answerability.status=NO` cases are excluded from quality aggregates because
they do not have a determinable expected selection. Their schema, privacy and
available safety checks still run. If a required safety label is unavailable,
the case records `unsupported` or `not_applicable` explicitly; it is not
converted to a passing or zero quality result.

## 6. Metrics and hard gates

For a fixed `K` and the same candidate pool, report at least. The definitions
below are frozen for this contract:

- Precision@K, Recall@K and F1;
- MRR/rank quality;
- mandatory-context recall;
- noise ratio and token waste;
- selected count and context size/latency where available.

Let `R = required_ids ∪ acceptable_ids`, `S` be the selected IDs after
normalization and first-`K` truncation, and `N = |S|`. A provider output with
more than `K` ranked IDs is rejected as invalid rather than silently allowing
select-all behavior. Precision@K is `|S ∩ R| / N`, with `0` when
`N=0` and `|R|>0`, and `1` when both are empty. Recall@K is
`|S ∩ required_ids| / |required_ids|`; if `required_ids` is empty the case is
not applicable for recall. F1 is the harmonic mean of the defined precision
and recall, and is `0` when either required component is zero. MRR is the
reciprocal rank of the first item in `R` (zero when no relevant item is
selected). Mandatory recall is `|S ∩ mandatory_ids| / |mandatory_ids|`, or
not-applicable when the mandatory set is empty. Noise ratio is
`|S - R| / max(N, 1)`. Token waste is the number of selected tokens belonging
to `S - R` divided by total selected tokens; when token counts are unavailable
it is `unavailable`, never an invented zero. Aggregates must state whether
they are macro averages over applicable cases or micro counts; W-09A uses
macro averages for per-case rates and a separately reported micro numerator /
denominator. Fewer than `K` selected items and abstention use the actual `N`
and do not receive padding items.

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
labels, project scope and `K`. “Identical” additionally requires equal
candidate content fingerprints, candidate ordering fingerprint, query/task
fingerprint, split/corpus version, deterministic seed, provider configuration
ID/version, selection normalization and tie-breaking policy. The report must show both sides for precision,
mandatory recall, noise and context size. V2 may be declared better only when:

- V2 precision is strictly greater than V1;
- V2 mandatory recall meets the accepted V1-equivalent threshold;
- all safety gates remain zero-leak;
- evidence is `verified` and quality is `measured`.

No V2 default/canary/promotion, rollback change or SessionStart change is part
of W-09A.

## 8. Provider and anti-gaming rules

Provider IDs and roles are bounded identifiers. A missing semantic/embedding
provider has one exact provider state: `available`, `unsupported`, or
`unavailable`. A missing semantic/embedding provider reports provider state
`unavailable` and reason code `SEMANTIC_UNAVAILABLE`; a provider that cannot
prove a required capability reports `unsupported` and reason code
`PROVIDER_UNSUPPORTED`. Source/corpus problems use W-09 evidence states
`stale`, `tampered`, `invalid` or `unavailable` with bounded reason codes
`SOURCE_STALE`, `SOURCE_TAMPERED`, `SOURCE_INVALID` or
`SOURCE_UNAVAILABLE`. All such states produce `quality=unavailable` or
`invalid`, `measurement=incomplete` and `promotion=blocked`. Random vectors,
fabricated confidence or lexical output must not be labelled semantic
evidence.

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

The source fingerprint allowlist is frozen for W-09A and is separate from the
corpus fingerprint. The exact source paths are:

```text
evals/w09a/contracts.py
evals/w09a/metrics.py
evals/w09a/engine.py
evals/w09a/reporting.py
tests/test_w09a_retrieval_evaluation.py
```

An implementation that needs another source path must amend this contract
before coding. Corpus input is exactly:

```text
evals/ig01b/public/ig-eval-v2/manifest.json
evals/ig01b/public/ig-eval-v2/dev.jsonl
evals/ig01b/public/ig-eval-v2/validation.jsonl
evals/ig01b/public/ig-eval-v2/abstention.jsonl
```

The final holdout audit additionally hashes `holdout.jsonl` and
`holdout.sha256`, but public runs must not read either file. Both fingerprints
use normalized LF bytes, sorted relative POSIX paths and length-framed SHA-256
input. Generated reports, model weights and arbitrary unlisted files are
excluded. A report must record both fingerprints and the provider
configuration/version, seed, `K`, normalization and tie-breaking codes.

Generated reports are content-free: case rows may contain bounded IDs,
counts, status codes and metric values only. Queries, rationale, transcript,
memory text, secrets and arbitrary candidate content stay in fixtures or
private local inputs and never appear in report JSON, package reports or
telemetry. Unknown fields, unbounded IDs and forbidden content keys are
rejected with bounded errors.

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
