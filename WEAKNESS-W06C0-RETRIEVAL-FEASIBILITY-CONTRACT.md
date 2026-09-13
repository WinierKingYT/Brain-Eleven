# W-06C0 — Retrieval Feasibility & Answerability Foundation Contract

**Status:** CONTRACT REVIEW PENDING  
**Program:** Engineering Weak-Point Improvement Goal  
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW  
**Package type:** evaluation-only; no production retrieval change

## 1. Problem

W-06B's bounded lexical task-aware selector is safe but does not meet its
quality contract. The independent review recorded TEST precision `0.176667`,
below the `>=0.60` floor, and TEST MRR `0.424722`, below the V1 value
`0.491944`. The lexical selector also inherits the legacy V1 candidate pool,
so changing weights or thresholds cannot establish whether the missing
relevant records were discarded before task-aware ranking.

The current corpus contains cases whose expected memory is not inferable from
the task text and available metadata. Several cases identify only a project and
a scenario number while the scenario number is not represented in the memory
content. Such a case is not a valid quality target unless it is explicitly
marked unanswerable. The evaluator currently exposes an `answerability`
concept in the contract language, but does not make it a real scored gate.

This package makes answerability and provider feasibility measurable before a
successor retrieval implementation is selected. It does not tune or promote a
retriever.

## 2. Scope

### 2.1 Included

1. Add a versioned retrieval corpus contract that records, for every case:
   - `answerability.status` (`answerable`, `unanswerable`, or
     `review_required`), aligned with the existing IG01-C evaluator vocabulary,
   - a bounded, content-free `answerability.reason`,
   - immutable split/provenance metadata.
2. Produce a new corpus version (`corpus-v3`) only from reviewed cases. The
   existing `corpus-v2` files, manifest, labels, and reports remain immutable.
3. Remove or mark `NO` cases whose required result cannot be inferred from the
   query plus the available candidate metadata. Do not repair them by adding
   hidden scenario labels to production inputs.
4. Build an evaluation-only feasibility harness that runs the same exact
   candidate snapshot and split inputs through:
   - V1 baseline,
   - W-06B task-aware V1,
   - V2 shadow provider,
   - existing deterministic lexical/authority candidate strategies,
   - configured real embedding and reranker adapters when explicitly
     available.
5. Keep provider output content-free in reports. Record provider/model/schema
   identity, status, error code, latency, candidate counts, and selected IDs or
   hashes only where the existing evaluation privacy contract permits them.
6. Add evaluator tests proving that answerability exclusion, split isolation,
   provider unavailability, variable-K metrics, and safety gates behave
   deterministically.

### 2.2 Explicitly excluded

- No change to `brain_eleven/runtime/task_aware.py`, V1 ranking weights,
  `scripts/context-compiler.py`, `memory-retriever.py`, `hybrid-search.py`,
  `semantic-search.py`, or any active retrieval path.
- No embedding cache migration, model download, API-key handling change, or
  provider promotion.
- No change to canonical MemoryStore, StateStore, ProjectRegistry, authority
  writers, capture, extraction, correction, or lifecycle behavior.
- No V2 default/canary promotion, SessionStart change, Phase 20 work, or new
  graph/agent subsystem.
- No tuning against HOLDOUT and no modification of `corpus-v2` after its
  existing measurements.

## 3. Corpus and answerability contract

### 3.1 Case validity

A retrieval case is benchmarkable only when a competent system can infer the
expected result from the task text and the candidate snapshot available to the
provider. A scenario index, opaque fixture ID, or hidden label that is absent
from both is not sufficient evidence of answerability.

Each `corpus-v3` case must retain the existing task, candidate, required,
useful, forbidden, lifecycle, project, and safety fields and add:

```json
"answerability": {
  "status": "YES",
  "reason": "query_and_candidate_metadata_support_target",
  "review_version": "w06c0-v1"
}
```

Allowed reasons are a finite, versioned vocabulary. Reasons must not contain
raw prompts, memory content, secrets, filesystem paths, or private project
identifiers beyond the existing public case ID boundary.

`unanswerable` and `review_required` cases are retained for audit visibility but
excluded from quality aggregates. They remain visible in counts and cannot
silently become scored by provider selection.

### 3.2 Splits and immutability

- `DEV` is for implementation/evaluator iteration.
- `TEST` is the public acceptance comparison and is not used to tune provider
  or weights.
- `HOLDOUT` remains sealed and is used only after the package's DEV/TEST
  behavior is frozen.
- `corpus-v2` and all existing baseline/W-06B/W-09A reports remain byte-stable.
- Any changed case or label requires a new corpus version and manifest hash.

The harness must report scored count, excluded count by answerability status,
split fingerprint, and source fingerprint. A report that omits these values is
invalid.

## 4. Provider feasibility harness

All providers receive the same generated vault, task, candidate snapshot, and
scope policy. The harness must not pass gold labels, case IDs, or expected
memory IDs into a provider.

Provider slots are measurement-only:

| Slot | Role | Unavailable behavior |
|---|---|---|
| `v1` | existing baseline | existing baseline error contract |
| `w06b` | rejected lexical successor | existing bounded fallback |
| `v2` | current shadow path | existing unavailable/fallback result |
| `authority_lexical` | existing deterministic candidate strategy | explicit unavailable if surface cannot be loaded |
| `embedding` | configured OpenAI or local real provider | `SEMANTIC_UNAVAILABLE` |
| `reranker` | configured real reranker over a fixed candidate set | `RERANKER_UNAVAILABLE` |

The default run must remain offline and deterministic. External or local model
providers run only when explicitly selected by the probe command. A missing
provider is a measured result, never a synthetic vector and never a pass.

Provider reports must include provider ID, model, revision/schema identity,
status, bounded error code, latency, candidate count, selected count, and
content-free evidence hashes. They must not include raw prompt, memory content,
transcript, token, credential, or API response text.

## 5. Metrics and hard gates

For `YES` cases only, report:

- Precision@K and variable-K precision,
- mandatory recall and recall,
- F1 and MRR,
- noise ratio and token waste,
- selected-count/abstention rate,
- p50/p95 latency and provider availability.

Safety gates apply to every scored and excluded case and remain hard zero:

```text
wrong_project_leakage = 0
forbidden_leakage = 0
superseded_leakage = 0
resolved_leakage = 0
secret_leakage = 0
```

The package does not set a new production promotion threshold. It must,
however, prove that the metric implementation can distinguish:

- perfect selection,
- select-all/high-recall noise,
- select-none,
- an unanswerable case,
- wrong-project selection,
- forbidden/superseded/resolved selection.

No provider can receive `PASS` while its answerability, source fingerprint,
split identity, or safety evidence is missing. A provider being unavailable is
`NOT MEASURED`, not a quality pass.

## 6. Implementation boundaries

Expected changes are limited to evaluation code, versioned public corpus
artifacts, and tests/reports under the evaluation boundary. Production runtime
modules must have zero diff. The implementation must include a machine-checkable
allowlist that fails if a production retrieval/canonical file is changed.

The package may add a new evaluation provider adapter, but it must consume the
existing normalized `NormalizedEvaluationResult` boundary and must not write a
vault, memory, state, graph, cache, or embedding artifact outside its isolated
temporary evaluation directory.

## 7. Evidence and exit gate

The package cannot close until all gates pass:

1. **Corpus gate:** `corpus-v3` answerability labels, manifest, split hashes,
   and provenance are reviewed; `corpus-v2` is unchanged.
2. **Evaluator gate:** metric unit tests cover perfect/select-all/select-none,
   answerability exclusion, malformed reports, hard safety failures, and
   provider-unavailable behavior.
3. **Parity/privacy gate:** V1, W-06B, and V2 run on identical inputs; reports
   contain no raw content; existing W-09A report validation remains green.
4. **Feasibility gate:** DEV and TEST provider matrix is reproducible, with
   explicit `NOT MEASURED` rows for unavailable providers and no hidden-label
   tuning. HOLDOUT is run only after the first three gates are frozen.
5. **Full verification:** focused evaluation suite, full `pytest tests -q`,
   critical flake8 (`E9,F63,F7,F82`), compile/import sanity, and
   `git diff --check` pass. Production retrieval files are unchanged.
6. **Independent review:** a read-only reviewer checks corpus answerability,
   split/holdout integrity, provider isolation, privacy, safety gates, and
   package scope. Only `SHIP`, `FIX-FIRST`, or `RETHINK` is valid; no self-SHIP.

This package's output is a trustworthy feasibility decision. It does not by
itself authorize W-06C1 implementation or any retrieval promotion.

## 8. Proposed sequence after acceptance

1. Independently review and accept this contract.
2. Implement W-06C0 evaluation/corpus work only.
3. Record whether any provider/strategy can meet the frozen quality floor on
   answerable DEV/TEST cases without safety regression.
4. Independently review W-06C0.
5. Only if W-06C0 is `SHIP`, draft a separate W-06C1 bounded runtime contract
   selecting the measured candidate strategy. If no measured strategy is
   viable, keep retrieval unchanged and open a new bounded research decision.

**Contract status: REVIEW PENDING — no production implementation authorized.**
