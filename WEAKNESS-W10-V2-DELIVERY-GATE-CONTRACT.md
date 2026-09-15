# W-10 — V2 Shadow Delivery Gate Contract

**Status:** CONTRACT / IMPLEMENTATION NOT AUTHORIZED

**Contract revision:** `6c828b2` (exact parent revision for this amendment)

**Program boundary:** Intelligence Graduation engineering weakness remediation

**Phase 20:** FROZEN / LOCKED

**V2 product status:** SHADOW

## 1. Objective

Restore the documented V2 rollout boundary at the native client edge. While
V2 is `SHADOW`, V2-rendered context may be computed for comparison and
diagnostics, but it must never be delivered to Claude or Codex as
`hookSpecificOutput.additionalContext`. The model-facing result must come from
the approved V1 delivery path and its provider metadata must describe the
actual delivered path.

This package addresses a rollout-boundary defect. It does not claim that V2
retrieval or compilation quality is solved.

## 2. Evidence-backed current defect

The current runtime has two distinct paths:

1. `compile_bootstrap()` in `brain_eleven/runtime/context.py` loads the legacy
   `context-compiler.py`, renders a V1 bootstrap, and labels the result `V1`.
2. Normal `compile_context()` calls `compile_task()` for the default
   `V1_LEGACY` retrieval mode. `compile_task()` builds `ContextCompilerV2` and
   returns `bundle.rendered_context`; there is currently no named normal-turn
   legacy V1 renderer. When runtime mode is `CANARY` or `ACTIVE`,
   `compile_context()` sets `delivered` from the non-empty result, and
   `brain_eleven/runtime/launcher.py` copies that context into
   `hookSpecificOutput.additionalContext`.

The normal result can therefore carry the V2 renderer marker while being
reported as `provider: V1`. This contradicts the current Phase 19 contract,
which says V2 shadow output is non-injecting and V1 remains the active
compiler. The finding is recorded as W-10 in
`ENGINEERING-WEAK-POINTS-AUDIT.md`.

## 3. Bounded scope

### In scope

- The model-facing decision in `brain_eleven/runtime/context.py`.
- The native output boundary in `brain_eleven/runtime/launcher.py` if a small
  guard is required there.
- A named, testable V1 normal-turn adapter for `V1_LEGACY`. This adapter must
  reuse only the existing legacy `ContextCompiler` project-scoped primitives
  (`_rank_memories`, `_resolve_current_state`, and
  `_generate_context_block` with related/unscoped notes empty), preserve its
  project scope and safety checks, and must not call the legacy public
  `compile()` projection because that method also reads unscoped Companion
  files. It must not invent new ranking or task-understanding behavior. The
  existing `W06B_TASK_AWARE` path remains a separate explicitly selected V1
  path.
- A single explicit delivery gate/configuration contract that distinguishes
  model-facing V1 delivery from diagnostic V2 shadow computation.
- Privacy-safe, content-free comparison metadata needed to prove which path
  was computed and which path was delivered.
- Focused regression tests, exact-revision evidence, and documentation of the
  resulting behavior matrix.

### Out of scope

- V2 promotion, retrieval-weight changes, embedding/provider changes, or
  compiler/ranking algorithm changes.
- Extraction, correction, capture, MemoryStore, StateStore, ProjectRegistry,
  canonical writes, or new persistence authority.
- Phase 20 or any new cognitive subsystem.
- Changes to the frozen V1 ranking/rendering semantics except the smallest
  routing needed to preserve V1 delivery.
- Raw prompt, transcript, memory content, tokens, or secrets in telemetry.
- Native client installation/trust changes and real-client dogfood; those are
  separate W-07B acceptance gates.

## 4. Required behavior matrix

The implementation must make the following outcomes explicit and testable.

| Runtime mode | V2 computation | Model-facing delivery | Provider metadata |
| --- | --- | --- | --- |
| `OFF` | none required | no context | bounded `OFF`/empty result |
| `SHADOW` | optional comparison only | SessionStart V1 bootstrap; normal UserPromptSubmit keeps the existing no-delivery behavior | `V1` for bootstrap; empty/no-delivery for normal prompt |
| `CANARY` | comparison allowed | `V1_LEGACY` uses the named adapter built from legacy project-scoped primitives; `W06B_TASK_AWARE` uses its existing V1 path | metadata matches delivered V1 path |
| `ACTIVE` | V2 still forbidden while product status is SHADOW; use the same V1 paths as CANARY | `V1_LEGACY` or explicitly selected W06B V1 path | metadata matches delivered V1 path |

`CANARY` and `ACTIVE` must not silently turn the compiler’s internal
`SHADOW` option into model-facing V2 promotion. `ACTIVE` is a valid persisted
runtime mode only after its existing graduation checks, but while the product
V2 status remains `SHADOW` its model-facing source is still the V1 adapter
above. If a future contract changes that policy, it must be a separate
reviewed promotion package.

When V2 is computed in shadow, its output may be retained only as bounded
comparison metadata: provider/version identifiers, status, selected opaque
IDs or hashes, revisions, token estimate, latency, and a reason for omission
or fallback. The V2 rendered text must not be returned from the native
model-facing API or written to telemetry.

The `provider` field, delivery flag, selected IDs, and context text must be
internally consistent. A result labeled `V1` must contain V1 output; a result
with no model-facing delivery must have `delivered == false` and an empty
model-facing context.

## 5. Safety and invariants

1. V2 remains downstream-only and read-only. No model output becomes
   canonical truth and no new write path is introduced.
2. Existing project scope, authority, lifecycle, revision, secret filtering,
   stale-input, and context-budget checks remain in force for the delivered
   V1 path.
3. A V2 failure, unavailable provider, invalid bundle, or metadata mismatch
   cannot cause V2 text to reach the client. The result must fall back to a
   bounded V1 result or fail visibly with empty context.
4. The native launcher must never infer promotion from a non-empty `context`;
   delivery requires an explicit approved-delivery marker and matching
   provider metadata.
5. Shadow comparison records are content-free and revision-bound. They must
   not include raw prompts, transcripts, memory text, rendered V2 context, or
   exception text.
6. Existing SessionStart V1 bootstrap ownership remains unchanged.
7. The normal-turn V1 adapter must be revision-bound to the same canonical
   memory/state snapshot checks as the current runtime result. It may reuse the
   legacy project-scoped primitives, but it must not read unscoped Companion
   notes, write bootstrap files, or mutate canonical stores during a hook
   request.

## 6. Implementation constraints

- Prefer a small explicit gate/helper over changing V2 internals.
- The normal `V1_LEGACY` implementation must have one explicit function name
  (for example `compile_task_v1`) and provenance `V1`; it must call the legacy
  project-scoped primitives rather than `ContextCompiler.compile()` or
  `ContextCompilerV2`.
- The adapter may return an empty/fail-closed result when the legacy projection
  is unavailable, stale, unsafe, or over budget. It must never substitute V2
  text and relabel it as V1.
- Preserve existing public result keys and compatibility fields unless a new
  bounded field is required to distinguish `computed_provider` from
  `delivered_provider`.
- Do not relabel V2 output as V1. If a V2 result is retained for comparison,
  its metadata must identify V2 and its text must remain non-delivered.
- Do not weaken `RuntimeConfig` rollout validation or the Phase 19 compiler’s
  `OFF`/`SHADOW` contract.
- No retrieval tuning or benchmark-label changes may be included in the diff.

## 7. Required tests and evidence

### Focused gate tests

1. Inject a sentinel V2-rendered bundle into the normal path and prove that
   `SHADOW`/`CANARY`/`ACTIVE` model-facing output never contains the sentinel
   while V2 remains SHADOW.
2. Prove the delivered context for `V1_LEGACY` is byte-equivalent to the
   existing project-scoped V1 bootstrap rendering (after the existing bounded
   result normalization) and `provider == "V1"`.
3. Prove an explicit future-approved V2 delivery marker is required before
   any V2 text could be delivered; absence or mismatch fails closed.
4. Prove V2 computation failure, malformed metadata, stale revisions,
   secret-bearing output, and budget overflow produce bounded fallback/empty
   output without leakage.
5. Prove launcher output contains `additionalContext` only when the explicit
   delivery marker, provider metadata, and non-empty safe context agree.
6. Seed `Companion/Last Session.md` and `Companion/Açık Döngüler.md` with
   unique sentinel text and prove neither sentinel appears in normal-turn V1
   delivery or telemetry. Also prove project isolation, existing SessionStart
   behavior, runtime `OFF`, normal `SHADOW` no-delivery behavior, W06B's
   explicit V1 path, and duplicate native delivery receipts remain unchanged.

### Regression and evidence

- Existing `tests/test_ig00_bootstrap.py`, `tests/test_pre13_runtime.py`,
  `tests/test_context_router.py`, `tests/test_context_compiler_v2.py`,
  `tests/test_context_compiler_v2_hardening.py`, and native launcher/runtime
  tests must pass without relaxing assertions.
- Run the new focused W-10 tests, the relevant runtime/context suite, then
  `pytest tests -q`.
- Run critical flake8 (`E9,F63,F7,F82`) on touched files, `compileall`, and
  `git diff --check`.
- Record exact `git rev-parse HEAD`, test commands/results, and a content-free
  delivery matrix. Do not claim native-client trust from mocked tests.
- Compare before/after V1 baseline IDs, scope, safety fields, and context
  budget behavior. No evaluation corpus or HOLDOUT label may change.

## 8. Exit gate

W-10 is eligible for independent review only when all are true:

- The explicit gate prevents V2 shadow text from native model-facing output.
- Delivered provider metadata matches delivered text.
- Fallback and fail-closed behavior is tested for failure, stale, scope,
  secret, and budget cases.
- Existing V1/native/runtime behavior remains green.
- No V2 promotion, retrieval tuning, canonical write, or Phase 20 change is
  present.
- Exact-revision local evidence is complete and reproducible.

An independent read-only reviewer must return exactly `SHIP`, `FIX-FIRST`, or
`RETHINK`. The implementer must not self-declare `SHIP`. Until that review,
W-10 remains `FIX-FIRST / REVIEW PENDING` and Phase 20 remains locked.

## 9. Package report template

```text
PACKAGE: W-10
REVISION: <exact evidence SHA>
OBJECTIVE: restore non-injecting V2 shadow boundary
FILES CHANGED: <list>
ROOT CAUSES ADDRESSED: <list>
TESTS ADDED: <list>
TESTS EXECUTED: <commands and results>
QUALITY METRICS BEFORE: <V1/V2 delivery evidence>
QUALITY METRICS AFTER: <delivery gate evidence>
SAFETY METRICS: <scope/secret/stale/fallback results>
KNOWN LIMITATIONS: <list>
OPEN FAILURES: <list>
INDEPENDENT REVIEW: <SHIP/FIX-FIRST/RETHINK or pending>
SCORE BEFORE: <0-10>
SCORE AFTER: <0-10>
VERDICT: REVIEW PENDING
```

**Contract status:** REVIEW PENDING — no implementation has started.
