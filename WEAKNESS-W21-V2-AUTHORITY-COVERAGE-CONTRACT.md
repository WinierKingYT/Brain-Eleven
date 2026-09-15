# W-21 — V2 Authority Coverage Contract

**Status:** CONTRACT REVIEW PENDING — implementation not started

**Contract revision:** This document is accepted only at the exact committed
revision recorded when the contract-review commit is made; an uncommitted
working-tree copy is not evidence.

**Program:** Engineering Weak-Point Improvement Goal

**Phase 20:** FROZEN / LOCKED — **V2:** SHADOW

## Objective

Make the shadow retrieval decision boundary fail closed when Router candidates
do not have a corresponding Phase 18 authority result. A candidate must never
be selected, or reported as authority-covered, merely because an authority
object was supplied with no usable coverage.

## Observed weakness

`retrieval_decision_v2/engine.py::RetrievalDecisionEngine.select()` currently
treats a missing `resolution_result` as an empty authority map. It also accepts
`EMPTY` authority output and allows a `SUCCESS`/`DEGRADED` result to cover only
some Router candidates while the uncovered candidates continue through the
selection loop. The returned telemetry can then say `authority_used=true` even
when the selected candidate was not represented by authority.

## Bounded behavior contract

1. **Shadow-only boundary.** Change only the V2 decision engine's authority
   hand-off validation. Do not promote V2, alter SessionStart/client delivery,
   change Router scope, tune ranking, add embeddings, or unlock Phase 20.
2. **Safe OFF behavior and precedence.** The existing Router status/scope and
   input validation run first. If an authority result is supplied, its
   existing invalid/stale status and revision checks also retain their current
   precedence. After those checks, `DecisionOptions(mode="OFF")` returns the
   existing empty result without requiring a resolution result when one was not
   supplied. It performs no candidate selection and preserves the current OFF
   telemetry contract.
3. **Authority is required for selection.** When mode is `SHADOW` and the
   Router contains candidates eligible for consideration, a resolution result
   must be present and have status `SUCCESS` or `DEGRADED`. The eligible set is
   computed *before* authority lookup from the Router candidates in their
   existing order, after duplicate candidate IDs, trusted scope, lifecycle and
   source-revision filters have run. Candidates filtered out by those existing
   rules do not create an authority-coverage requirement. Every eligible
   candidate must have exactly one authority row whose `candidate_id` and
   `project_id` match the Router candidate (global candidates must also obey the
   existing global-scope rule).
4. **Empty/missing/partial/duplicate coverage fails closed.** Missing
   resolution, `EMPTY` resolution with eligible Router candidates, partial
   coverage, and duplicate authority rows return a content-free `FAILED`
   decision with the exact stable error code
   `AUTHORITY_COVERAGE_UNAVAILABLE`. `selected` remains empty. Existing
   Router/authority revision, status and scope checks still run and retain
   their current precedence where they already produce `STALE_INPUT`,
   `SCOPE_ERROR` or `AUTHORITY_INPUT_UNAVAILABLE`.
5. **Degraded but complete coverage remains visible.** A `DEGRADED` authority
   result may proceed only when coverage is complete; the final decision keeps
   the existing degraded status/reason behavior. Authority candidate statuses
   such as `UNRESOLVED` remain policy metadata and are not silently converted
   into missing coverage.
6. **Telemetry truthfulness.** `authority_used=true` is emitted only after the
   coverage check passes for at least one eligible candidate. A no-eligible
   result reports `authority_used=false`. Failure telemetry may expose only
   bounded counts and a stable coverage status: `full`, `empty`, `partial`,
   `missing`, or `duplicate`. The failure error remains exactly
   `AUTHORITY_COVERAGE_UNAVAILABLE`; never expose IDs, content, prompts,
   memory text or secrets.
7. **No authority or canonical changes.** The package remains read-only. It
   must not write MemoryStore, StateStore, ProjectRegistry, authority cache or
   compiler cache data, and must not change authority resolution itself.

## Required tests

- `resolution_result=None` with an eligible Router candidate fails closed.
- `EMPTY` authority with an eligible candidate fails closed.
- Partial authority coverage fails closed and selects nothing.
- Duplicate authority rows fail closed before any dictionary collapse, including
  a duplicate with the same ID in another project.
- Complete `SUCCESS` coverage preserves the current selection and telemetry.
- Complete `DEGRADED` coverage preserves degraded visibility.
- A Router with no eligible candidates remains a deterministic empty result.
- OFF mode remains empty without authority input.
- OFF with a supplied stale/invalid authority result preserves the existing
  stale/invalid precedence; OFF with no result does not require authority.
- Existing stale revision, scope, lifecycle, duplicate and content-free
  behavior remains unchanged.
- No canonical revision or authority cache changes occur during selection.

Run the focused retrieval/authority/compiler tests, then the full test suite,
critical flake8 (`E9,F63,F7,F82`), compileall and `git diff --check` at an
exact committed revision. Holdout corpus, labels, thresholds and provider
selection must remain byte-identical.

## Exit gate

W-21 may be marked `SHIP` only after an independent contract review returns
`SHIP`, implementation and focused safety tests pass, exact-head full
regression is green, and an independent read-only implementation review
returns exactly `SHIP`.

Until then: **W-21 = OPEN / NOT ACCEPTED**.
