# IG01-C — Evaluation Engine Contract

**Package:** IG01-C — Evaluation Engine  
**Status:** ACTIVE / BOUNDED  
**Authority:** CONTRACT  
**Prerequisite:** IG01-B `SHIP` at `ig01b-ship`  
**Phase 20:** `FROZEN / LOCKED`  
**V2:** `SHADOW`

## Objective

IG01-C implements the deterministic evaluator that consumes the frozen IG01-B
labels and normalized system outputs. It measures behavior without importing or
changing a retriever, extractor, resolver, compiler, model provider or
canonical persistence authority.

The evaluator is a measurement instrument. It cannot write `MemoryStore`,
`StateStore` or `ProjectRegistry`, and its output is evidence rather than
canonical truth.

## Bounded implementation surface

Only these files are in scope:

- `evals/ig01c/contracts.py` — versioned metric and safety-event value objects;
- `evals/ig01c/metrics.py` — pure family metrics and hard-gate calculations;
- `evals/ig01c/engine.py` — case dispatch, corpus aggregation, controls and
  content-free report validation/writing;
- `evals/ig01c/__init__.py` — public evaluator API;
- `tests/test_ig01c_evaluator.py` — evaluator and anti-gaming tests;
- this contract, package report, independent review and the dedicated CI job.

No production intelligence, provider, embedding, ranking weight, extraction
rule, lifecycle behavior, V2 rollout or Phase 20 artifact may change here.

## Input/output boundary

The engine accepts primitive mappings keyed by `case_id`. A provider must
translate its output into one of these projections before evaluation:

- retrieval/context: ordered IDs, optional content-free metadata
  (`project_id`, `status`, `token_count`);
- extraction: typed proposition fields and optional confidence;
- reference: status, target ID, candidate targets and operation;
- lifecycle: operation, status transition and optional history;
- capture: bounded event/job counters;
- safety: an explicit list of gate names.

Reports contain case IDs, selected memory/target IDs, metric counts, hashes and
gate evidence.
The report validator recursively rejects prompt, query, transcript, text,
content, token, secret and diagnostic fields. Raw evidence is never copied to
CI artifacts or long-lived telemetry.

## Metric rules

Every metric is emitted as `{value, numerator, denominator,
not_applicable, empty_selection}`. A zero denominator is either an explicit
empty selection with value `0`, or `not_applicable` when the family has no
valid denominator. Case metrics are unweighted macro means; event/job/lifecycle
metrics use pooled numerators and denominators. Token-waste `value` is the raw
wasted-token sum (its denominator records the available selected-token total).
The engine publishes the aggregation mode and underlying counts.

Retrieval/context metrics are:

- Precision@K, with the declared K as denominator;
- Recall@K and mandatory recall;
- F1 and MRR (lexical stable ID order is the tie-break);
- noise ratio and token waste;
- context precision, mandatory coverage, redundancy and irrelevant-context
  rate where applicable.

Release-mode corpus runs enforce the IG01-A minimum population: at least five
answerable cases per family/language and a positive denominator for every
claimed metric. Exploratory unit fixtures must explicitly opt out with
`enforce_benchmark=False`; that flag cannot disable the mandatory retrieval
anti-gaming controls.

Extraction metrics are decision precision/recall, false-commitment rate,
assistant-as-user rate, wrong type/scope rates and ECE. Reference metrics are
correct-target rate, ambiguity abstention, wrong-project target and false
correction rates. Lifecycle and capture metrics follow the pooled formulas in
`IG01-A-EVALUATION-CONTRACT.md`.

## Safety and anti-gaming rules

The seven absolute-zero gates are independently reported and cannot be hidden
by an average:

```text
wrong_project_leakage = 0
forbidden_leakage = 0
assistant_as_user_commitment = 0
cross_project_target = 0
superseded_leakage = 0
resolved_leakage = 0
lifecycle_cycle = 0
```

`false_supersession` and `false_commitment` use the frozen `<= 0.01` target.
Every positive event must carry a content-free review record; a positive event
with no denominator fails closed rather than becoming `not_applicable`.

Every retrieval report contains deterministic `select_all` and `select_none`
controls. Selecting every candidate therefore exposes precision, noise and
token waste; recall alone cannot produce a green result.

The evaluator validates IDs and rejects duplicates, missing outputs,
unexpected outputs, non-finite numbers, unknown gate names and malformed
reports. The report validator requires the `select_all` and `select_none`
control rows for every retrieval/context case, and accepts only the closed,
content-free source schema (`git_sha`, `seed`, `retrieval_k`,
`source_fingerprint`). It never trusts provider-supplied project/status metadata for
fixture-owned labels when immutable candidate metadata is available.

## Version and reproducibility

The evaluator release is `1.0.0` (`EVALUATOR_VERSION`). A report records the
corpus version, split, evaluator version, retrieval K, seed, source fingerprint
and production revision supplied by the caller. A behavior change requires a
SemVer bump and new evidence; old reports remain immutable.

IG01-C tests use hand-authored controls and synthetic primitive mappings. They
do not tune or import production algorithms. Holdout labels remain owned by
IG01-B and are not modified by this package.

## Exit gate

IG01-C can receive `SHIP` only when:

- all evaluator formulas have deterministic tests;
- select-all/select-none controls prove anti-gaming behavior;
- absolute-zero and near-zero gate behavior is tested;
- raw-content report rejection is tested;
- missing/duplicate/unexpected outputs fail closed;
- evaluator tests pass on Ubuntu and Windows CI;
- the independent read-only reviewer returns exactly `SHIP`.

IG01-D baseline measurement remains unopened until this package passes the
independent review. Phase 20 stays locked and V2 stays shadow-only.
