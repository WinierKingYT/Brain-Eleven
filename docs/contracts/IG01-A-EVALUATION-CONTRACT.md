# IG01-A — Evaluation Contract

**Package:** IG01-A — Evaluation Contract
**Status:** ACTIVE / IN PROGRESS
**Authority:** CONTRACT
**Program:** Intelligence Graduation
**Base revision:** `0f68e75cf71ba32065a90c7b2c8fd03fc476fde6`
**Prerequisite:** IG-00 `CLOSED / SHIPPED`
**Phase 20:** `FROZEN / LOCKED`
**V2:** `SHADOW`
**SHIP tag:** `ig01a-ship` (created only after all acceptance gates pass)

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
  schema_version: integer (the existing EVIDENCE_SCHEMA_VERSION)
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
  schema_version: string
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
schema_version: string
candidate_targets: [string, ...]
confidence: number | null
signals: {name: number | string, ...}
project_id: string | null
```

Ambiguity is a valid safe result. Guessing an equal or cross-project target is
never an acceptable substitute.

## Case schema

Every case in every dataset class, including `PRIVATE_REALISTIC`, must carry the
following fields:

```yaml
case_id: string
dataset_class: PUBLIC_SYNTHETIC | PRIVATE_REALISTIC | SANITIZED_REAL_FAILURE
family: capture | extraction | reference_resolution | lifecycle | retrieval | context_compilation | safety
category: string (one of the required coverage vocabulary keys below)
case_kind: answerable | adversarial | control | abstention
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
data_lineage: synthetic | private_realistic | sanitized_failure
contamination_class: synthetic | real | holdout
labeler: string
label_confidence: number
evaluator_version_min: string
generator_identity: string
sut_identity: string
source_case_ids: [string, ...]
```

`case_kind=abstention` is valid only with `answerability=unanswerable`; an
`unanswerable` case must use `case_kind=abstention`. `answerable`,
`adversarial` and `control` cases must be answerable and remain in ordinary
scoring (an adversarial case may still contain forbidden expected outcomes).
Unanswerable cases are retained in a separate abstention set and do not count
as ordinary intelligence failures.

## Required coverage vocabulary

`category` is not an unrestricted label. Each corpus version must include at
least one answerable and one adversarial case for every required category below
in each applicable language (Turkish, English and mixed technical language).
The corpus manifest fails closed if a category is missing.

```text
capture:
  duplicate_event, replayed_event, crash_after_evidence_read,
  crash_before_canonical_write, crash_after_canonical_write,
  crash_before_receipt, lock_timeout, corrupt_transcript, deleted_transcript,
  invalid_project, corrupt_queue_record, expired_lease,
  statestore_conflict, memorystore_cas_conflict, golden_e2e

extraction:
  explicit_decision, implicit_decision, preference, lesson, requirement,
  blocker, resolved_blocker, suggestion, hypothetical, question, negation,
  correction, assistant_proposal, quoted_material, mixed_statement

reference_resolution:
  exact_named_target, previous_decision, pronoun_reference, claim_key_target,
  ambiguous_target, no_valid_target, wrong_project_target, inactive_target

lifecycle:
  confirm, supersede, correct, resolve, reopen, lifecycle_cycle

retrieval:
  exact_relevant, paraphrase, related_relevant, old_critical_decision,
  current_state, current_blocker, historical_context, global_lesson, preference,
  recent_irrelevant, lexical_trap, wrong_project, superseded_or_resolved

context_compilation:
  mandatory_coverage, minimum_sufficient_context, redundancy_reduction,
  contradiction_visibility, token_budget, latency

safety:
  wrong_project_leakage, forbidden_leakage, superseded_leakage,
  resolved_leakage, secret_leakage, assistant_as_user,
  false_supersession, cross_project_target
```

The manifest records coverage counts by `dataset_class`, language, family,
category, split, `case_kind` and `answerability`. Every category/language pair
must contain at least one `answerable` case and one `adversarial` case; every
`abstention` case must be `unanswerable`, and every `unanswerable` case must be
`abstention`. Family/category compatibility is validated against the vocabulary
above; the manifest also records and validates the allowed
`dataset_class`/`data_lineage`/`contamination_class` combinations. CI fails
closed when any count is missing or inconsistent. Coverage gaps are a package
failure, not a tuning opportunity.

The manifest validator uses a closed family-to-category map (the map above),
rejects unknown combinations, and checks lineage compatibility row by row:
`PUBLIC_SYNTHETIC` requires `data_lineage=synthetic`,
`PRIVATE_REALISTIC` requires `data_lineage=private_realistic`, and
`SANITIZED_REAL_FAILURE` requires `data_lineage=sanitized_failure`.
`contamination_class` remains an independent cross-split control, but every
value and its counts must be present in the manifest.

## Metric definitions

All denominators and tie-breaks are fixed here. `k` is the declared retrieval
cutoff for the report.

| Metric | Formula | Example |
|---|---|---|
| Precision@K | `|relevant ∩ retrieved_k| / k`; if `k=0`, report `0` and `empty_selection=true` | 3 relevant in top 5 → `3/5 = 0.60` |
| Recall@K | `|relevant ∩ retrieved_k| / |relevant|`; if no relevant labels, report `not_applicable` | 3 of 4 required → `3/4 = 0.75` |
| Mandatory recall | `|mandatory ∩ retrieved| / |mandatory|`; if no mandatory labels, report `not_applicable` | 4 of 5 mandatory → `0.80` |
| F1 | `2 * precision * recall / (precision + recall)`; if both are zero with relevant labels, report `0`; with no relevant labels, `not_applicable` | `P=.60,R=.75` → `.667` |
| MRR | `mean(1 / rank_of_first_relevant)`; no relevant result contributes `0`, while a case with no relevant labels is `not_applicable` | first relevant at rank 2 → `.50` |
| Noise ratio | `|retrieved \ relevant| / |retrieved|`; empty retrieval is `0` with `empty_selection=true` | 2 noisy of 5 → `.40` |
| Token waste | `sum(tokens(item) where relevance(item) < 0.30)`; relevant=`1`, acceptable=`0.5`, otherwise `0` | two irrelevant 20-token items → `40` |
| Context precision | `|relevant compiled items| / |all compiled items|`; empty context is `0` with `empty_selection=true` | 3 useful of 5 → `.60` |
| ECE | `sum(|accuracy_bin-confidence_bin| * n_bin) / N`; ten bins `[0,.1),...,[.9,1]`; `N=0` is `not_applicable` | weighted calibration error |
| Latency | p50 and p95 end-to-end milliseconds over at least 5 samples, using nearest-rank percentiles; fewer samples are `not_applicable` | report V1 and V2 separately |

The MRR tie-break is lexical `memory_id`. A select-all control run is printed
in every retrieval report and is included in precision, noise and token-waste
comparisons. High recall alone is not success.

Expected/acceptable/forbidden records are matched by normalized stable IDs and
typed proposition keys, never by free-text substring coincidence. Mandatory
records are the case `mandatory_ids` projection of `required_results`.
`context_precision` is computed per answerable case as
`count(selected IDs in required ∪ acceptable and not forbidden) /
count(selected IDs)`, with an empty selection reported as `0` and an explicit
flag. The aggregate is the macro mean across answerable cases; forbidden IDs
are always counted separately as a hard-gate violation. Every metric reports
its denominator, `not_applicable` flag and empty-set flag. False-commitment
rate uses the number of expected committed decisions as denominator; with none,
it is `not_applicable`. Answerability-abstention rate uses only cases labeled
`unanswerable` as its denominator.

## Family metric formulas and aggregation

The following formulas complete the family-level contract. Unless stated
otherwise, aggregate values are macro means over answerable cases with a
published case count; zero-denominator cases are `not_applicable` and cannot
be silently dropped.

Case-scored metrics use the unweighted macro mean across eligible cases.
Event/job/operation rates (capture, replay, lifecycle and authority) use a
pooled numerator and denominator within each family/language/split and also
publish the per-case counts; they are not allowed to be reweighted by a
different case mix. All family aggregates publish both the numerator and
denominator so macro and pooled interpretations remain auditable.

| Family metric | Formula | Example |
|---|---|---|
| Capture loss rate | `lost_events / emitted_events` | `1/100 = .01` |
| Duplicate canonical effect rate | `duplicate_effects / replayed_events` | `0/20 = 0` |
| Replay correctness | `idempotent_correct_replays / replayed_events` | `20/20 = 1` |
| Terminal/effect agreement | `completed_jobs_with_verified_effect / completed_jobs` | `9/10 = .90` |
| Decision precision | `correct_decisions / predicted_decisions` | `8/10 = .80` |
| Decision recall | `correct_decisions / expected_decisions` | `8/10 = .80` |
| False commitment rate | `false_commitments / expected_committed_decisions` | `1/100 = .01` |
| Assistant-as-user rate | `assistant_committed_as_user / assistant_proposals` | `0/20 = 0` |
| Wrong type/scope rate | `wrong_type_or_scope / typed_predictions` | `1/25 = .04` |
| Correct target rate | `correct_targets / resolvable_targets` | `9/10 = .90` |
| Ambiguous abstention rate | `correct_abstentions / ambiguous_cases` | `10/10 = 1` |
| False supersession rate | `false_supersessions / supersession_attempts` | `0/20 = 0` |
| Wrong-project target rate | `cross_project_targets / target_attempts` | `0/50 = 0` |
| Lifecycle transition safety | `safe_transitions / lifecycle_operations` | `50/50 = 1` |
| Leakage rate | `forbidden_or_wrong_scope_hits / selected_items` | `0/100 = 0` |
| Mandatory context coverage | `mandatory_items_present / mandatory_items_expected` | `9/10 = .90` |
| Irrelevant-context rate | `irrelevant_compiled_items / compiled_items` | `1/10 = .10` |
| Contradiction visibility rate | `contradictions_explicitly_marked / detected_contradictions` | `4/4 = 1` |
| Context token usage | `sum(rendered_context_tokens)` | `820 tokens` |
| Redundancy rate | `duplicate_or_equivalent_items / compiled_items` | `2/10 = .20` |
| Context latency | nearest-rank p50/p95 over end-to-end samples | `p95=180ms` |
| False correction rate | `false_corrections / correction_attempts` | `0/20 = 0` |
| Authority violation rate | `authority_violations / authority_decisions` | `0/50 = 0` |
| Answerability abstention rate | `correct_abstentions / unanswerable_cases` | `9/10 = .90` |

For MRR, a case with relevant labels but no retrieved relevant item contributes
`0`; a case with no relevant labels is `not_applicable`. For F1, P=R=0 with
expected labels yields `0`. For answerability abstention, no unanswerable
cases is `not_applicable`. Safety rates retain raw violation counts in
addition to aggregates so that a zero aggregate cannot hide a single violation.

### Minimum evidence and not-applicable safeguards

Each release-gating report must contain at least five answerable cases per
applicable family and language, plus at least one positive denominator for
each metric it claims. A required family with fewer than five scored cases, or
a run in which all cases for a required metric are `not_applicable` or empty,
is `INVALID_BENCHMARK_RUN` and cannot pass a floor. A genuinely inapplicable
family must be declared in the manifest with its reason; it may not be created
by removing cases after seeing results. Reports publish per-family and
per-language denominators, `not_applicable` counts, empty-selection counts,
and excluded-case counts before any aggregate is computed.

## Safety gates

These are reported as independent rows and never averaged away.

### Nine IG01-A hard gates

The IGFULLPLAN cardinality is fixed at nine gates: seven absolute-zero gates
and two near-zero gates that require review for every positive event.

```text
wrong_project_leakage = 0
forbidden_leakage = 0
assistant_as_user_commitment = 0
cross_project_target = 0
superseded_leakage = 0
resolved_leakage = 0
lifecycle_cycle = 0
```

### Review-required candidate gate

Every `false_commitment` and `false_supersession` event must produce a review
record. The program target for each is `<= 0.01`, but every positive event
remains visible even when the aggregate target is met. Exploratory candidate
mistakes remain quarantined and may never be committed to canonical lifecycle
state. These two near-zero gates plus the seven absolute-zero gates are the
complete nine-gate IG01-A set.

`secret_leakage` and `authority_violation` remain independently reported safety
metrics with raw violation counts and review records. They are monitored here
without changing the IG01-A nine-gate cardinality; later runtime/security
packages may promote them to an explicit release gate.

Any absolute-zero violation is a package failure regardless of other scores.
Any near-zero rate above `0.01`, or any positive event without its required
review record, is also a package failure.

## Dataset, split and privacy policy

The program reserves three dataset classes:

1. `PUBLIC_SYNTHETIC` — repository-safe, reproducible, secret/PII scanned;
2. `PRIVATE_REALISTIC` — local-only, never uploaded as a CI artifact;
3. `SANITIZED_REAL_FAILURE` — derived from dogfood after raw content and
   identifying data are removed.

`dataset_class` describes storage/privacy, `data_lineage` describes origin,
and `contamination_class` describes synthetic/real/holdout contamination
controls. They are orthogonal fields and may not be collapsed into one label.

Every class covers Turkish, English and mixed technical language. Each corpus
version has `DEV` (60%), `VALIDATION` (20%) and `HOLDOUT` (20%) splits unless a
versioned manifest records another ratio. DEV is available for iteration,
VALIDATION may be run once per implementation iteration for architecture
decisions, and HOLDOUT is sealed until IG-01-E and the final audit. IG-01-D
baselines use DEV+VALIDATION only.

HOLDOUT labels are immutable within a corpus version. A content or label hash
change requires a new corpus version and new baselines. The manifest records a
SHA-256 content/label hash and CI fails on any unexpected HOLDOUT change.
Private paths have a CI guard that fails if raw private data enters a tracked
or uploaded path.

## Answerability and contamination

Before a case enters scored data, ask:

> Could a competent system infer the expected result from the evidence actually
> available to it?

If no, the case is `unanswerable`: it is excluded from ordinary precision and
recall, retained for abstention checks, and marked as an invalid benchmark
case for intelligence scoring. Reports include
`answerability_abstention_rate` and the exclusion count. A corpus version that
excludes more than 30% of candidate cases (where
`exclusion_rate = unanswerable_candidates / all_candidate_cases` before
filtering), or has unresolved label disagreement, triggers RETHINK. HOLDOUT
answerability requires two labels, each with confidence in `[0,1]`, and an
adjudication record for disagreement. The manifest stores both the numerator
and denominator; developers may not redefine the candidate pool after seeing
results.

The corpus generator and the system under test must not share a model or
hidden labels. Every manifest and run records `generator_provider`,
`generator_model`, `generator_version`, `sut_provider`, `sut_model` (or
`deterministic`), and label provenance. Each case records `data_lineage`,
`source_case_ids`, generator identity and SUT identity. A CI overlap check
compares normalized content hashes across DEV/VALIDATION/HOLDOUT and fails on
cross-split duplicates. The manifest must also assert that generator identity
and SUT identity differ, unless the generator is explicitly deterministic and
has no hidden labels. Evaluator runs are offline, deterministic, seed-controlled
and network-free. HOLDOUT content and labels must not appear in debug output,
intermediate prompts, tuning notes or developer fixtures.

## Versioning and baseline protocol

Evaluator releases use SemVer, for example `evaluator/1.0.0`. Patch bumps are
reserved for non-behavioral fixes, minor bumps for compatible metric/schema
behavior changes and major bumps for incompatible changes. Every report
records:

```text
evaluator_version
corpus_version
corpus_split_fingerprint
source_fingerprint
git_sha
retrieval_k
seed
noise_count
generator_provider/model/version
sut_provider/model/version
hash_algorithm
```

Evaluator behavior changes require a version bump and rerunning all affected
baselines. Corpus changes require a corpus version bump. Old reports remain
available and are marked `SUPERSEDED`, never silently rewritten.

V1 and V2 are always evaluated on the same exact fixtures, split, `k`,
seed, noise-count, evaluator version, source fingerprint and report revision.
The run also records the exact production `git_sha` for each path and the
same privacy/safety configuration. A baseline is invalid if any of those
fields differ or if either path has a safety violation; clean-safety is a
conjunction, not an averaged comparison. No production tuning may precede the
first baseline measurement.

Before any later tuning, IG-01-D must record an accepted V1-equivalent recall
threshold using the same corpus and evaluator. The V2 promotion gate is
always `V2_precision > V1_precision` and
`V2_mandatory_recall >= accepted_v1_equivalent_recall`; the accepted threshold
may not be lower than the program floor `0.80`. The exact numeric threshold is
`TBD` until IG-01-D, but the rule itself is frozen now.

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

The IG01-A contract spot-check is **PENDING USER VERIFICATION** until the 20
draft cases below are reviewed by the user. The full IG-01 checkpoint later
requires 20 randomly selected frozen-corpus labels plus the IG01-C evaluator
diff. Neither checkpoint can be fabricated by automated tests.

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
| 9 | tr | reference_resolution | “Önceki kararı iptal et.” | target resolution required; ambiguity abstains |
| 10 | mixed | reference_resolution | “Database kararını değiştir, queue aynı kalsın.” | claim-key scoped correction |
| 11 | en | reference_resolution | two equal prior candidates for “that” | ambiguous/review required |
| 12 | tr | lifecycle | explicit supersede of named memory | supersede with review record |
| 13 | en | lifecycle | resolve an already resolved blocker | no unsafe duplicate transition |
| 14 | mixed | lifecycle | project A correction names project B memory | cross-project target forbidden |
| 15 | tr | retrieval | old canonical DB decision vs recent color preference | old critical decision ranks higher |
| 16 | en | retrieval | same keyword, wrong project | foreign candidate forbidden |
| 17 | mixed | retrieval | superseded JWT memory | superseded result forbidden |
| 18 | tr | context_compilation | required blocker plus redundant duplicates | mandatory blocker kept; duplicates reduced |
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
- the IG01-A 20-case contract spot-check is completed by the user (the random
  frozen-corpus label checkpoint remains required before IG-01 closes);
- independent review returns `SHIP`.

Until then, IG01-B corpus work and all evaluator implementation remain closed.
