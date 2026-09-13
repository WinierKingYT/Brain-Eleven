# W-06C0 P1-B — Historical Scope Compatibility Contract

**Status:** CONTRACT REVIEW PENDING  
**Package:** W-06C0-SCOPE-COMPAT  
**Parent:** frozen W-06C0 feasibility harness  
**Phase 20:** FROZEN / LOCKED

## Objective

Restore a green, reproducible historical W-06C0 scope assertion without
loosening its allowlist and without making W-06C0R1 files part of the old
package. The current test compares the original W-06C0 base revision with the
accumulated `master` history, so later packages are incorrectly reported as
W-06C0 changes.

## Bounded change

Allowed files:

- `evals/w06c0/evaluation.py`
- `tests/test_w06c0_contract.py` only if a focused compatibility assertion is
  required
- `WEAKNESS-W06C0-PACKAGE-REPORT.md` if its evidence format must record the
  fixed package end

No W-06C0 corpus, W-06C0R1 corpus/evaluator, production, retrieval, or Phase
20 file may change.

The historical verifier must compare `IMPLEMENTATION_BASE_REVISION` to one
immutable W-06C0 package-end revision: `f676c91`, the last revision of the
W-06C0 implementation/report chain before W-06C0R1. The verifier must expose
both `base_revision` and `scope_end_revision`, while retaining the current
checkout `head_revision` as diagnostic evidence. The allowlist and forbidden
prefix checks remain unchanged. A caller may not silently substitute the
current `HEAD` as the scope end.

The package-end revision must be validated as a repository revision before the
diff is trusted. If it is absent, malformed, or not an ancestor of the current
checkout, the verifier fails closed with `W06C0Error`.

## Required tests and evidence

- Existing `tests/test_w06c0_contract.py` tests remain unchanged and green
  unless a narrowly scoped assertion is necessary to bind the end revision.
- Prove the historical scope passes on current `master` while the current
  accumulated diff would include later W-06C0R1 paths.
- Prove a non-ancestor or invalid end revision fails closed.
- Preserve source allowlist, manifest, provider, safety, and holdout behavior.
- Run critical flake8, compile/import sanity, `git diff --check`, focused W-06C0
  tests, W-06C0R1 tests, and the full suite.
- The report must state that this is compatibility for a frozen historical
  package; it must not claim W-06C0R1 has shipped.

## Exit gate

Implementation is **REVIEW PENDING** until an independent read-only reviewer
confirms the fixed historical range, fail-closed revision validation, unchanged
allowlist semantics, and full regression. Only that reviewer may return
`SHIP`, `FIX-FIRST`, or `RETHINK`.

## Package report fields

`PACKAGE`, `REVISION`, `OBJECTIVE`, `FILES CHANGED`, `ROOT CAUSES ADDRESSED`,
`TESTS ADDED`, `TESTS EXECUTED`, `QUALITY METRICS BEFORE/AFTER`, `SAFETY
METRICS`, `KNOWN LIMITATIONS`, `OPEN FAILURES`, `INDEPENDENT REVIEW`, `SCORE
BEFORE/AFTER`, `VERDICT`.

**Plan status: CONTRACT REVIEW PENDING — implementation not authorized.**
