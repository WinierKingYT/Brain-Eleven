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
2. Produce a new corpus version at the exact path
   `evals/corpus-v3/`, with `dev/`, `test/`, and `holdout/` directories and a
   `manifest.json`. It contains all 70 DEV, 60 TEST, and 30 HOLDOUT cases from
   the reviewed v3 set; every case receives an answerability label. The
   existing `corpus-v2` files, manifest, labels, and reports remain immutable.
3. Retain every reviewed case in its original split and mark cases whose
   required result cannot be inferred from the query plus available candidate
   metadata as `unanswerable` or `review_required`. Do not repair them by
   adding hidden scenario labels to production inputs. A case may be removed
   only in a later corpus version with a manifest entry and a bounded removal
   reason.
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
  "status": "answerable",
  "reason": "query_and_candidate_metadata_support_target",
  "review_version": "w06c0-v1",
  "provenance_hash": "sha256:<64 lowercase hex characters>"
}
```

The exact reason enum for `w06c0-v1` is:

| Reason | Meaning |
|---|---|
| `query_and_candidate_metadata_support_target` | The target is inferable from the query and allowed candidate metadata. |
| `query_lacks_target_discriminator` | The query does not distinguish the labeled target from alternatives. |
| `gold_label_depends_on_hidden_fixture_metadata` | The label depends on an opaque scenario/fixture value unavailable to a provider. |
| `candidate_snapshot_incomplete` | Required evidence is absent from the candidate snapshot supplied to the provider. |
| `annotation_disagreement` | Independent reviewers disagree; the case is `review_required`. |
| `privacy_or_schema_review` | The case needs review before it can enter a scored split. |

Reasons must not contain raw prompts, memory content, secrets, filesystem
paths, or private project identifiers beyond the existing public case ID
boundary. Every public label is reviewed by two independent labelers. Any
disagreement becomes `review_required`; a single implementer cannot resolve a
disagreement by changing the label. The label set, reason enum, reviewer
roles, and `review_version` are frozen in the v3 manifest. HOLDOUT labels are
created before provider tuning, stored in the sealed HOLDOUT directory, and
are not read by implementation or DEV/TEST report code until the final probe.

`unanswerable` and `review_required` cases are retained for audit visibility but
excluded from quality aggregates. They remain visible in counts and cannot
silently become scored by provider selection.

### 3.2 Splits, manifest, fingerprints, and immutability

The v3 manifest is fixed before implementation:

```text
path: evals/corpus-v3/manifest.json
schema_version: 1
corpus_version: 3
suite_counts: {"dev": 70, "test": 60, "holdout": 30}
split_directories: ["dev", "test", "holdout"]
answerability_reason_version: "w06c0-v1"
```

Each split contains exactly the stated number of JSON case files. The manifest
stores a SHA-256 for every normalized UTF-8 file (CRLF and CR normalized to
LF), plus a split fingerprint formed by sorting relative POSIX paths and
hashing length-prefixed `(relative_path, normalized_bytes)` frames. Reports
must copy the manifest hash, split fingerprint, source fingerprint, case count,
scored count, and excluded counts. Missing, extra, duplicate, or symlinked
case files fail closed.

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
requested slot, actual provider ID, availability (`AVAILABLE` or `UNAVAILABLE`),
run status (`COMPLETE`, `NOT_MEASURED`, or `ERROR`), bounded error code,
latency, candidate count, selected count, and content-free evidence hashes.
They must not include raw prompt, memory content, transcript, token,
credential, or API response text. A fallback must identify its actual provider
and set `availability=AVAILABLE`, `run_status=COMPLETE`, and `fallback=true`;
it may not be reported as the requested provider. An unavailable configured
provider produces `availability=UNAVAILABLE`, `run_status=NOT_MEASURED`, and a
finite error code; it is never a synthetic vector and never a quality pass.

### 4.1 Normalized answerability mapping

The v3 adapter maps only `answerable` to a scored quality case. Both
`unanswerable` and `review_required` remain visible and run safety checks but
are excluded from quality aggregates with separate counts. Any other status
literal is invalid and aborts the report. Existing W-09A `corpus-v2` parsing,
the legacy `status == "NO"` behavior, and all existing W-09A reports remain
byte-stable; the v3 adapter does not silently reinterpret v2 values.

## 5. Metrics and hard gates

For `answerable` cases only, report:

- Precision@K for `K=1`, `K=3`, `K=5`, and `K=10`, using the provider's
  ordered IDs truncated to the first K. Duplicate IDs are an evidence failure
  (the row is rejected, rather than silently collapsed), matching the existing
  IG01-C metric contract.
- mandatory recall and recall,
- F1 and MRR,
- noise ratio and token waste,
- selected-count/abstention rate,
- p50/p95 latency and provider availability.

Metrics are macro-averages over answerable cases in the split. Empty selection
has precision, recall, F1, MRR, and mandatory recall equal to `0`; an
answerable case with no required labels is invalid. The evaluator must expose
both the fixed-K and variable-K rows and must count truncation/duplicate
violations as evidence failures.

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

Expected changes are limited to this exact allowlist:

```text
evals/corpus-v3/**
evals/w06c0/**
tests/test_w06c0_*.py
WEAKNESS-W06C0-PACKAGE-REPORT.md
```

Any other tracked file change is a scope failure. In particular,
`brain_eleven/**`, `scripts/**`, `context_compiler_v2/**`, `authority/**`,
`context_router/**`, `.claude/**`, `evals/w09a/**`, and `evals/corpus-v2/**`
must have zero diff. A machine-checkable allowlist must fail before a report
is accepted, and the package must record an exact before/after tree assertion
for these forbidden paths. Temporary vault/provider/cache artifacts may exist
only below an isolated temporary directory and must be deleted or excluded
from the commit.

The package may add a new evaluation provider adapter, but it must consume the
existing normalized `NormalizedEvaluationResult` boundary and must not write a
vault, memory, state, graph, cache, or embedding artifact outside its isolated
temporary evaluation directory.

## 7. Evidence and exit gate

The package cannot close until all gates pass:

1. **Corpus gate:** `corpus-v3` answerability labels, manifest, split hashes,
   and provenance are reviewed; `corpus-v2` is unchanged.
2. **Evaluator gate:** metric unit tests cover perfect/select-all/select-none,
   answerability exclusion, malformed reports, hard safety failures, duplicate
   IDs, empty selections, all four K values, and provider-unavailable behavior.
3. **Parity/privacy gate:** V1, W-06B, V2, and `authority_lexical` run on
   identical inputs; configured embedding and reranker slots are also run when
   available and otherwise emit explicit `NOT_MEASURED` rows. Reports contain
   no raw content; existing W-09A report validation remains green.
4. **Feasibility gate:** DEV and TEST provider matrix is reproducible, with
   one row for every six provider slots, explicit `NOT_MEASURED` rows for
   unavailable optional providers, and no hidden-label tuning. HOLDOUT is run
   only after the first three gates are frozen and its label directory remains
   sealed until that probe.
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
