# IG-03 — Semantic Extraction Bounded Contract

**Status:** CURRENT CONTRACT — implementation package not yet accepted

**Contract input:** IG01-A frozen proposition schema and IG01-C metrics

**Baseline:** `c2525a4d58aeae3a19715b837cc747e691f9e0c6`

**Gate:** IG-01 `CLOSED / SHIPPED`; Phase 20 `FROZEN / LOCKED`; V2 `SHADOW`.

## Objective

Add semantic meaning extraction behind deterministic safety controls while
preserving Brain-Eleven's canonical authority boundary. The result is a
structured candidate proposition for validation and review. It is not a memory
write, lifecycle mutation, state write, retrieval change or V2 promotion.

The package closes the gap between the current regex/rule baseline and a
provider-backed semantic proposal. It does not promise that a model is
available in every environment. Availability and quality must be measured
explicitly.

## Required flow

```text
Evidence message
  → deterministic safety prefilter
  → provider adapter (or explicit SEMANTIC_UNAVAILABLE)
  → strict structured proposition builder
  → deterministic validator
  → candidate/review/quarantine result
```

There is no model-to-`MemoryStore.write` path. Any worker or truth integration
consumes only validated proposal objects through the existing authority
boundary. IG-03 may run in shadow evaluation; it must not alter active runtime
delivery.

## In scope

* prefiltering secret/token/password-like material, full transcript payloads
  and quoted external material before a provider receives input;
* a provider-agnostic extraction interface with capability, model, schema and
  availability metadata;
* mapping provider output to the IG01-A proposition projection;
* deterministic validation of role, commitment, scope, temporal fields,
  confidence components and allowed schema fields;
* adapters for the deterministic baseline, an optional local model and an
  optional stronger model;
* dev/validation benchmark execution through IG01-C metrics and content-free
  evidence;
* review/quarantine records for rejected or uncertain propositions.

## Out of scope

Capture queue, lease, retry and worker completion remain IG-02. Conversational
reference targeting and lifecycle operations remain IG-04. Retrieval weights,
embeddings, task-aware ranking and context compilation remain IG-05/IG-06.
No new persistence authority, graph reasoner, agent framework, planner or
Phase 20 feature may be introduced.

## Proposition contract

The builder accepts only the following top-level fields, matching IG01-A:

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
evidence_refs: non-empty list[string]
confidence_components: object[name → finite number]
correction_clues: object | null
target_clues: object | null
schema_version: string
```

Unknown fields, duplicate IDs, malformed types, non-finite numbers and
out-of-range confidence components are rejected. `unknown` is accepted only as
an explicitly non-authoritative source label; it can never yield a committed
or canonical-eligible proposition. Provider-specific metadata is kept in a
bounded provenance envelope and is not copied into the proposition.

Nested objects are closed as well. `temporal_scope` contains only `start`,
`end` and `precision`; `correction_clues` contains only `explicit`,
`old_value`, `new_value`, `claim_key` and `reason`; `target_clues` contains
only `named_id`, `claim_key`, `lineage_id` and `reference_kind`. `value` may be
a scalar or a JSON object/array of scalar semantic values, with a bounded
depth. Every nested object rejects reserved authority/content keys such as
`canonical_commit`, `write_memory`, `write_state`, `prompt`, `transcript`,
`content`, `token`, `secret` and `password`. Provider and review metadata use
the same recursive content-free key check.

The builder must preserve semantic identity. A type-only answer such as
`decision` without a meaningful claim/value is incomplete and cannot score as
the expected proposition in IG01-C.

## Deterministic safety gates

Validation runs after parsing and before any evaluator or downstream caller.

1. `source_role` of `assistant`, `tool` or `system` can never produce
   `COMMITTED`. The validator emits a review/quarantine result instead.
2. A question or hypothetical can never produce `COMMITTED`, regardless of the
   provider's label. The prefilter attaches immutable evidence-derived flags
   to the provider call; the validator checks those flags independently of
   model output.
3. Quoted or externally attributed material is never a user commitment. Its
   prefilter flag cannot be cleared by a provider.
4. A missing or invalid `project_id` is `unresolved`; it cannot become a
   canonical project memory or state effect.
5. Temporal fields must be structurally valid and cannot claim an end before a
   start. Missing time remains explicit uncertainty, not invented certainty.
6. Confidence components must be finite, bounded and named. The scalar
   confidence is derived deterministically from components or remains null;
   provider prose cannot override the formula.
7. `canonical_commit`, `write_memory`, `write_state`, lifecycle operations and
   persistence handles are forbidden provider output fields. Any attempt is a
   `forbidden_leakage`/authority violation in evaluation.
8. Secret-like input is screened before provider invocation. Evidence output is
   content-free and stores hashes/IDs only.

Safety gates are absolute: assistant-as-user commitment, question commitment,
hypothetical commitment, prefilter leakage and direct canonical-write intent
must remain zero. A single observed violation is a package `RETHINK` signal,
not an aggregate average to be hidden.

## Provider interface and benchmark

Each adapter implements a narrow proposal-only interface equivalent to:

```text
extract(evidence, *, project_id, schema_version) →
  ProviderResult(status, propositions, review_records, metadata)
```

`ProviderResult` exposes `MEASURED`, `SEMANTIC_UNAVAILABLE` or `INVALID_OUTPUT`
and content-free provider/model/schema identifiers. It has no `MemoryStore`,
`StateStore` or lifecycle writer capability. Network use is opt-in and never
implicit in tests.

Its bounded result fields are `status`, `provider_id`, `model`,
`propositions`, `review_records`, `metadata`, `error_code`, `elapsed_ms` and
`schema_version`. `metadata` may contain only scalar capability/provenance
keys (`requested_schema_version`, `project_bound`, provider revision and
availability codes); it cannot contain prompts, transcripts, credentials or
writer handles.

The benchmark must run the same extraction cases and labels through:

* the current deterministic extractor control;
* a local Qwen-class adapter when the local runtime is installed; and
* a stronger optional adapter when explicitly configured.

Provider absence is recorded, not converted to a fabricated score. Selection
is based on DEV for iteration and VALIDATION for the package decision. IG01-B
HOLDOUT is sealed and excluded from every IG-03 tuning, debug and benchmark
run. The benchmark records provider/model/schema revisions, split fingerprints,
case counts, latency and content-free metric output.

## Metrics and acceptance targets

IG01-C remains the metric authority. At minimum report decision precision,
decision recall, false commitment rate, assistant-as-user rate, wrong type,
wrong scope and ECE, with denominators and applicability flags.

Reference targets from the IG plan are:

* decision precision `≥ 0.95` stretch, or the IG01-D derived gate target
  (`max(program floor + 0.05, measured baseline + 0.10)`) when a measured
  ceiling is available;
* decision recall `≥ 0.90` stretch and never below the program floor;
* false commitment `≤ 0.01`, with a review record for every positive event;
* assistant-as-user commitment `= 0`;
* question/hypothetical commitment `= 0`;
* ECE `≤ 0.10` where confidence is applicable. Confidence components are
  finite values in `[0,1]`, and the derived scalar is their arithmetic mean;
  missing components make calibration `not_applicable`, never a fabricated
  confidence.

If the measured provider cannot meet the target but all absolute safety gates
are clean and a named improvement backlog is credible, the reviewer may use
the program's `SHIP + follow-up` rule. Missing or unmeasurable evidence is not
a pass. No result may be tuned against HOLDOUT.

## Tests and evidence

Focused tests must cover:

* strict schema and unknown-field rejection;
* assistant/tool/system, question, hypothetical and quotation rejection;
* secret/token prefilter before provider invocation;
* unresolved scope and malformed temporal data;
* confidence component validation and ECE input;
* malicious provider output attempting canonical write;
* unavailable provider and malformed provider output;
* identical DEV/VALIDATION case inputs across all available providers;
* absence of production imports granting canonical write capability.

Full regression is required after focused tests. Evidence must bind to the
exact Git SHA and include test counts, provider statuses, split fingerprints,
latency and safety events without raw prompts, transcripts, memory content,
tokens or secrets. A provider benchmark report is generated evidence, not a
current instruction.

## Exit gate

IG-03 can be proposed for independent review only when all are true:

* bounded prefilter, provider adapters, proposition builder and deterministic
  validator exist;
* every provider is either measured or explicitly `SEMANTIC_UNAVAILABLE`;
* three candidate provider slots are benchmarked without HOLDOUT access;
* IG01-C extraction metrics and denominators are revision-bound;
* all absolute safety gates are zero and every near-zero event has review
  evidence;
* no canonical write or runtime promotion path changed;
* focused tests, full regression, latency and privacy checks pass;
* the exact-head CI result is recorded; and
* an independent read-only reviewer returns exactly `SHIP`, `FIX-FIRST` or
  `RETHINK`.

Until that verdict, IG-03 remains open and IG-02 implementation may not begin.
IG-01 is already closed, but Phase 20 stays locked and V2 stays shadow even if
IG-03 eventually ships.
