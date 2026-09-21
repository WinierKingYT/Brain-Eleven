# IG-01 Product Evaluation Foundation

**Status:** CLOSED / SHIPPED — IG-01 CLOSURE HUMAN CHECKPOINT PASS
**Authority:** CONTRACT
**Opened from:** `18e88876495db77a2e99ea927f01a2d28c5d9ed6`
**Branch:** `ig/01-evaluation-foundation`
**Opened:** 2026-09-08

## Mission

IG-01 is a measurement package, not an intelligence-tuning package. Its
purpose is to establish a trustworthy way to measure Brain-Eleven capture,
extraction, lifecycle, retrieval and context behavior before any production
intelligence is changed.

The primary question is:

> Can Brain-Eleven's behavior be measured reliably enough that later score
> improvements mean a real product improvement?

The current approximate evaluation-quality score is **4/10**. The target for
this package is **at least 9/10**. This target concerns measurement quality,
not retrieval or extraction quality.

Phase 20 remains **FROZEN / LOCKED** and V2 remains **SHADOW** throughout this
package.

## Governance and production boundary

During IG-01, production behavior is frozen. The following are prohibited:

- retrieval-weight tuning;
- semantic-provider migration or Qwen embedding integration;
- extraction or correction algorithm improvements;
- task-model tuning;
- V2 promotion or Phase 20 work.

Only a minimal fix required to execute the evaluator or prevent evaluator
corruption may be made. Any such exception requires an explicit package
record. The evaluator must measure current production behavior rather than
quietly changing it.

The canonical authorities remain MemoryStore, StateStore and ProjectRegistry.
Evaluation artifacts, model output and telemetry cannot become canonical truth.

## Sequential internal packages

IG-01 is executed as five bounded packages. A package cannot begin until the
previous package has an independent **SHIP** verdict.

| Package | Scope | Exit requirement |
|---|---|---|
| **IG01-A — Evaluation Contract** | Freeze families, labels, answerability, privacy, metrics, hard gates and split/version rules. | Contract reviewed and SHIP. |
| **IG01-B — Corpus & Ground Truth** | Build public synthetic, private realistic and sanitized real-failure corpus mechanisms with immutable labels per version. | Corpus provenance and splits reviewed and SHIP. |
| **IG01-C — Evaluation Engine** | Implement deterministic metric and safety-gate calculations; test evaluator behavior independently of production algorithms. | Evaluator tests and anti-gaming checks reviewed and SHIP. |
| **IG01-D — Baseline Measurement** | Measure V1 and V2 on the same frozen corpus without tuning production. | Paired revision-bound report, no-HOLDOUT proof, feasibility result and independent SHIP. |
| **IG01-E — Independent Evaluation Audit** | Read-only audit of benchmark integrity, privacy, holdout discipline and interpretability. | Independent SHIP closes IG-01. |

IG01-A is shipped under the immutable `ig01a-ship` gate and IG01-B is shipped
under the immutable `ig01b-ship` closure. IG01-C is shipped under its exact
revision-bound package report and independent `SHIP`; implementation remains
limited to its approved contract and evidence. IG01-D baseline measurement is
the next bounded package and is active only for its paired baseline evidence;
IG01-D is accepted after its independent technical review and the user
checkpoint `IG01-D human checkpoint PASS` on 2026-09-09. IG01-E is shipped at
exact review head `a38433090da662a35379620b223ddfade21dd5a9` after its
independent read-only `SHIP`; the user supplied `IG-01 closure human checkpoint
PASS` on 2026-09-09. IG-01 is closed. The audit covered benchmark integrity,
privacy, holdout discipline and interpretability without changing production
behavior.
The full program keeps the following order
after IG-01: IG-03 semantic extraction, IG-02 capture closure, IG-04
correction/reference, IG-05 task-aware retrieval, IG-06 V2 runtime promotion,
IG-07 architecture consolidation, IG-08 dogfood and IG-09 final audit. IG-03
precedes IG-02 because it freezes the proposition shape used by the capture
pipeline.

## Evaluation families

Each family is reported independently; no aggregate score may hide a severe
failure in one family:

- capture;
- extraction;
- reference resolution;
- lifecycle;
- retrieval;
- context compilation;
- safety.

Required extraction and reference cases include decisions, preferences,
lessons, requirements, blockers, suggestions, hypotheticals, questions,
negations, corrections, quotations, assistant proposals, named targets,
pronouns, ambiguous targets and inactive targets.

## Dataset classes and language policy

Three corpus classes are reserved:

1. **PUBLIC_SYNTHETIC** — repository-safe, reproducible and versioned;
2. **PRIVATE_REALISTIC** — local-only; raw private data must never be uploaded
   through CI artifacts;
3. **SANITIZED_REAL_FAILURE** — derived from future dogfood failures after
   secrets and identifying content are removed.

Every public case must declare Turkish, English or Turkish-English mixed
technical language coverage. Clean English-only synthetic prompts are
insufficient. Private and failure corpora must preserve the same language
coverage without exposing raw user content.

## Split, provenance and answerability

Every corpus version reserves **DEV**, **VALIDATION** and **HOLDOUT** splits.
DEV supports iteration, VALIDATION supports architecture/configuration
decisions, and HOLDOUT is never used for tuning. Holdout labels are immutable
within a corpus version; changed labels or cases require a new version.

Each case must carry a stable identifier, family/category, language, query or
conversation, project scope, expected/required/acceptable/forbidden records as
applicable, rationale, provenance, version and split.

An **UNANSWERABLE CASE** is not a system failure. Before inclusion, ask:

> Could a competent system infer the expected result from the evidence
> actually available to it?

If the answer is no, mark the case `INVALID_BENCHMARK_CASE` and exclude it from
intelligence scoring. This prevents frozen-corpus artifacts such as rotating
IDs or unavailable context from being mistaken for product failures.

## Safety gates and anti-gaming rules

The following are hard gates and cannot be compensated for by average scores:

```text
wrong_project_leakage = 0
forbidden_leakage = 0
assistant_as_user_commitment = 0
cross_project_target = 0
superseded_leakage = 0
resolved_leakage = 0
lifecycle_cycle = 0
false_supersession <= 0.01
false_commitment <= 0.01
```

Metrics must penalize selecting everything. Retrieval therefore reports
Precision@K, Recall@K, F1, MRR, mandatory recall, noise ratio and token waste.
Extraction reports decision precision/recall, false commitment, assistant-as-
user, wrong-type and wrong-scope rates. Reference/lifecycle reports correct
target, ambiguity abstention, false supersession and wrong-project target
rates. Safety failures remain visible as individual violations.
These seven absolute-zero and two near-zero gates are the shared IG01 safety
contract and take precedence over older abbreviated lists. `secret_leakage` and
`authority_violation` remain separately reported with raw counts and review
records; they do not change the nine-gate IG01-A cardinality.

## Baseline policy

The baseline sequence is fixed:

```text
evaluation contract
    -> corpus freeze
    -> evaluator verification
    -> V1 and V2 baseline measurement
    -> later intelligence improvement
```

V1 and V2 must run on the same exact corpus and split definitions. No result
may be called a baseline if production weights, providers, extraction rules or
correction behavior were tuned first. Holdout labels never enter tuning.

The baseline report must preserve separate V1/V2 precision, mandatory recall,
noise and token results, plus all hard safety outcomes. Existing PRE-13
quality failures remain historical evidence; they must not be relabeled or
hidden by this package.

## Acceptance and stop point

IG01-OPEN-01 is accepted only when this contract exists, the generic `ig/**`
CI triggers are verified, Phase 20/V2 boundaries remain unchanged, and the
exact branch Validation/runtime evidence is recorded. Production intelligence
must remain unchanged.

After this opening package, stop. The next separately authorized package is
**IG01-A — Evaluation Contract**.
