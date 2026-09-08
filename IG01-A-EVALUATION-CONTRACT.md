# IG01-A — Evaluation Contract

**Package:** IG01-A — Evaluation Contract
**Status:** ACTIVE / IN PROGRESS
**Authority:** CONTRACT
**Program:** Intelligence Graduation
**Base revision:** `0f68e75cf71ba32065a90c7b2c8fd03fc476fde6`
**Prerequisite:** IG-00 `CLOSED / SHIPPED`
**Phase 20:** `FROZEN / LOCKED`
**V2:** `SHADOW`

## Objective and boundary

This package freezes what Brain-Eleven will measure and how the result will be
interpreted. It is a document contract. It does not create a corpus, implement
an evaluator, tune retrieval or extraction, change correction behavior, or
promote V2.

The question is:

> Can capture, extraction, reference resolution, lifecycle, retrieval, context
> compilation and safety be measured reproducibly enough that later score
> improvements mean a real product improvement?

The current approximate evaluation-quality score is **4/10**. The target is
**at least 9/10** for the measurement foundation itself. This is not a claim
about current retrieval quality.

Production intelligence remains frozen until IG-01 closes. The canonical
authorities remain `MemoryStore`, `StateStore` and `ProjectRegistry`.

## Measured families

| Family | Input | Output under test | Primary metrics |
|---|---|---|---|
| Capture | hook event, queue receipt, evidence | durable event and canonical effect | loss, duplicate effect, replay correctness, terminal/effect agreement |
| Extraction | role-aware evidence message | typed candidate/proposition | decision precision/recall, false commitment, assistant-as-user, wrong type/scope, ECE |
| Reference resolution | correction/reference plus project lineage | target or safe abstention | correct target, ambiguous abstention, wrong-project target, false correction |
| Lifecycle | candidate target and operation | safe lifecycle transition | false supersession, resolved/superseded leakage, cycle detection |
| Retrieval | task and scoped candidate set | ranked memory IDs and signals | Precision@K, Recall@K, F1, MRR, mandatory recall, noise, token waste |
| Context compilation | ranked references and budget | minimum sufficient context | required coverage, irrelevant context, contradictions, token usage, p50/p95 latency |
| Safety | all above with adversarial scope/lifecycle inputs | fail-closed decision | hard-gate violations, secret leakage, scope leakage, authority violations |

No aggregate score may hide a failure in one family.

## Frozen evaluation projections

These are evaluation-facing contracts. They do not authorize production schema
or runtime changes during IG01-A.

### EvidenceMessage

The existing evidence boundary remains immutable for this package:

```text
EvidenceMessage
  record.evidence_id
  record.project_id
  record.role
  record.captured_at
  record.occurred_at
  record.source metadata and content hashes
  content (ephemeral input; never durable telemetry)
```

Evidence content may be read by an evaluator fixture, but raw prompt,
transcript and memory text must not be written to long-lived telemetry or CI
artifacts.

### ExtractionCandidate / Proposition

The semantic proposition projection is frozen for later IG-03 work:

```text
candidate_id: string
project_id: string | null
claim_type: string
subject: string | null
predicate: string | null
value: string | object | null
commitment: string
temporal_scope: object | null
source_role: user | assistant | tool | system | unknown
evidence_refs: [string, ...]
confidence_components: {name: number, ...}
correction_clues: object | null
target_clues: object | null
schema_version: string
```

A proposition is a candidate, never canonical truth. Model output must remain a
proposal until deterministic validation and truth/lifecycle resolution.

### RetrievalPlan and injected-context item

The comparison projection records only content-safe references and signals:

```text
RetrievalPlan
  task_id: string
  project_scope: string
  query_ids: [string, ...]
  input_revisions: object
  candidate_budget: object
  schema_version: string

InjectedContextItem
  memory_id: string
  revision: integer
  lifecycle: string
  scope: string
  relevance_signals: {name: number | string, ...}
  mandatory: boolean
```

The production router may retain additional fields; the evaluator must project
them into this stable shape for V1/V2 comparison.

### ResolverOutcome

```text
status: RESOLVED_TARGET | AMBIGUOUS | NO_TARGET | REVIEW_REQUIRED
candidate_targets: [string, ...]
confidence: number | null
signals: {name: number | string, ...}
project_id: string | null
```

Ambiguity is a valid safe result. Guessing an equal or cross-project target is
never an acceptable substitute.

## Case schema

Every public or sanitized case must carry the following fields:

```yaml
case_id: string
family: capture | extraction | reference_resolution | lifecycle | retrieval | context | safety
category: string
language: tr | en | mixed
project: string | null
query_or_conversation: object | string
expected_result: object
required_results: [object, ...]
acceptable_results: [object, ...]
forbidden_results: [object, ...]
rationale: string
provenance: string
corpus_version: string
split: DEV | VALIDATION | HOLDOUT
answerability: answerable | unanswerable
contamination_class: synthetic | realistic | sanitized_failure
labeler: string
label_confidence: number
evaluator_version_min: string
```

Unanswerable cases are retained in a separate abstention set and do not count
as ordinary intelligence failures.

## Metric definitions

All denominators and tie-breaks are fixed here. `k` is the declared retrieval
cutoff for the report.

| Metric | Formula | Example |
|---|---|---|
| Precision@K | `|relevant ∩ retrieved_k| / k` | 3 relevant in top 5 → `3/5 = 0.60` |
| Recall@K | `|relevant ∩ retrieved_k| / |relevant|` | 3 of 4 required → `3/4 = 0.75` |
| Mandatory recall | `|mandatory ∩ retrieved| / |mandatory|` | 4 of 5 mandatory → `0.80` |
| F1 | `2 * precision * recall / (precision + recall)` | `P=.60,R=.75` → `.667` |
| MRR | `mean(1 / rank_of_first_relevant)` | first relevant at rank 2 → `.50` |
| Noise ratio | `|retrieved \ relevant| / |retrieved|` | 2 noisy of 5 → `.40` |
| Token waste | `sum(tokens(item) where relevance < 0.30)` | two irrelevant 20-token items → `40` |
| ECE | `sum(|accuracy_bin-confidence_bin| * n_bin) / N` | weighted 10-bin calibration error |
| Latency | p50 and p95 end-to-end milliseconds | report V1 and V2 separately |

The MRR tie-break is lexical `memory_id`. A select-all control run is printed
in every retrieval report and is included in precision, noise and token-waste
comparisons. High recall alone is not success.

## Safety gates

These are reported as independent rows and never averaged away.

### Absolute-zero gates

```text
wrong_project_leakage = 0
forbidden_leakage = 0
assistant_as_user_commitment = 0
cross_project_target = 0
superseded_leakage = 0
resolved_leakage = 0
lifecycle_cycle = 0
secret_leakage = 0
```

### Near-zero gates with mandatory review

`false_supersession` and `false_commitment` must produce a review record for
every positive event. The program target is `false_commitment <= 0.01`; a
positive event remains visible even when the aggregate target is met.

Any absolute-zero violation is a package failure regardless of other scores.

## Dataset, split and privacy policy

The program reserves three dataset classes:

1. `PUBLIC_SYNTHETIC` — repository-safe, reproducible, secret/PII scanned;
2. `PRIVATE_REALISTIC` — local-only, never uploaded as a CI artifact;
3. `SANITIZED_REAL_FAILURE` — derived from dogfood after raw content and
   identifying data are removed.

Every class covers Turkish, English and mixed technical language. Each corpus
version has `DEV`, `VALIDATION` and `HOLDOUT` splits. DEV is available for
iteration, VALIDATION may be run at most once per iteration for architecture
decisions, and HOLDOUT is sealed until IG-01-E and the final audit.

HOLDOUT labels are immutable within a corpus version. A content or label hash
change requires a new corpus version and new baselines. Private paths have a
CI guard that fails if raw private data enters a tracked or uploaded path.

## Answerability and contamination

Before a case enters scored data, ask:

> Could a competent system infer the expected result from the evidence actually
> available to it?

If no, the case is `unanswerable`: it is excluded from ordinary precision and
recall, retained for abstention checks, and marked as an invalid benchmark
case for intelligence scoring.

The corpus generator and the system under test must not share a model or
hidden labels. Evaluator runs are offline, deterministic, seed-controlled and
network-free. HOLDOUT content and labels must not appear in debug output,
intermediate prompts, tuning notes or developer fixtures.

## Versioning and baseline protocol

Evaluator releases use SemVer, for example `evaluator/1.0.0`. Every report
records:

```text
evaluator_version
corpus_version
corpus_split_fingerprint
source_fingerprint
git_sha
```

Evaluator behavior changes require a version bump and rerunning all affected
baselines. Corpus changes require a corpus version bump. Old reports remain
available and are marked `SUPERSEDED`, never silently rewritten.

V1 and V2 are always evaluated on the same exact fixtures, split, seed,
noise-count and evaluator version. No production tuning may precede the first
baseline measurement.

## Verdict rule

The program floor is immutable:

```text
context_precision >= 0.60
mandatory_recall >= 0.80
```

Package verdicts follow this deterministic table:

| Safety gates | Measurement | Verdict |
|---|---|---|
| Any absolute-zero violation | Any | RETHINK |
| Clean safety | Below program floor | RETHINK |
| Clean safety | Floor to target, with a credible named backlog | SHIP plus follow-up |
| Clean safety | Floor to target, without credible backlog | FIX-FIRST |
| Clean safety | Meets package target | SHIP |

IG-01-A itself has no behavior target; its target is contract completeness.
IG-03/04/05 numerical targets remain `TBD` until the IG-01-D feasibility
probe, with the program floor always active.

## Independent review and human checkpoints

An independent reviewer receives only this contract, the candidate diff, tests
and evidence. The reviewer must not inherit implementation reasoning and must
answer whether labels, metrics, safety gates and holdout rules can be gamed.
The only accepted verdicts are `SHIP`, `FIX-FIRST` and `RETHINK`.

Required human checkpoints for the full program:

1. before IG-01 closes: manually inspect 20 corpus labels and the IG01-C
   evaluator diff;
2. before IG-06: manually inspect the V1/V2 comparison and rollback evidence;
3. before IG-09: manually inspect the objective scorecard and one complete
   evidence chain.

The first checkpoint is **PENDING USER VERIFICATION** until the 20 draft cases
below are reviewed by the user. This cannot be fabricated by automated tests.

### Twenty draft label checks

These are logic-check prompts, not corpus fixtures. They will be converted to
versioned cases only after the human checkpoint.

| # | Language | Family | Draft phenomenon | Expected safe interpretation |
|---:|---|---|---|---|
| 1 | tr | extraction | “SQLite kullanacağız.” | explicit user decision |
| 2 | en | extraction | “We might use Redis.” | hypothetical, no commitment |
| 3 | mixed | extraction | “Auth için JWT kullanmayacağız; session cookie.” | correction plus replacement decision |
| 4 | tr | extraction | “Bunu kullansak mı?” | question, no commitment |
| 5 | en | extraction | assistant says “We should choose Postgres.” | assistant proposal |
| 6 | mixed | extraction | quoted external documentation | quotation, no user commitment |
| 7 | tr | extraction | “Bu hata çözüldü.” | resolved blocker/state |
| 8 | en | extraction | “The deployment is still blocked.” | current blocker |
| 9 | tr | reference | “Önceki kararı iptal et.” | target resolution required; ambiguity abstains |
| 10 | mixed | reference | “Database kararını değiştir, queue aynı kalsın.” | claim-key scoped correction |
| 11 | en | reference | two equal prior candidates for “that” | ambiguous/review required |
| 12 | tr | lifecycle | explicit supersede of named memory | supersede with review record |
| 13 | en | lifecycle | resolve an already resolved blocker | no unsafe duplicate transition |
| 14 | mixed | lifecycle | project A correction names project B memory | cross-project target forbidden |
| 15 | tr | retrieval | old canonical DB decision vs recent color preference | old critical decision ranks higher |
| 16 | en | retrieval | same keyword, wrong project | foreign candidate forbidden |
| 17 | mixed | retrieval | superseded JWT memory | superseded result forbidden |
| 18 | tr | context | required blocker plus redundant duplicates | mandatory blocker kept; duplicates reduced |
| 19 | en | safety | secret-like text in evidence | quarantined/filtered |
| 20 | mixed | answerability | expected target absent from available lineage | unanswerable; safe abstention |

## IG01-A acceptance

IG01-A can receive `SHIP` only when:

- all seven families and their input/output/metrics are defined;
- the four projections are field-complete and versioned;
- every metric has a formula and example;
- hard-gate classes and the verdict table are unambiguous;
- split, immutability, answerability, privacy and contamination rules are
  explicit;
- evaluator/corpus versioning and V1/V2 comparison are fixed;
- the 20-case human checkpoint is completed by the user;
- independent review returns `SHIP`.

Until then, IG01-B corpus work and all evaluator implementation remain closed.
