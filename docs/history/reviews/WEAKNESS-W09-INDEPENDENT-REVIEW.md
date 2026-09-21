# W-09 — Independent Read-Only Implementation Review

PACKAGE: W-09 — Evaluation Evidence Integrity & Gate Semantics
REVIEW REVISION: `c90a9ca06a9fc6661e224ea23490f9e2e5e7346e`
CONTRACT BASELINE: `02a41b53c3ecfe2a92543aa4a9475b20234f9fdc`
PRIOR FIX-FIRST REVIEW: `f1820fe`
FIX REVISION: `f9c8f44`
REVIEW TYPE: independent read-only final implementation review

## Scope and evidence

I reviewed the frozen W-09 contract, the package report at the exact review
revision, the prior FIX-FIRST findings, and the corrective diff. I inspected
the IG01-D pair reconciliation and generic report-validation paths and ran the
focused W-09 tests only:

```text
.venv\Scripts\python.exe -m pytest -q tests/test_evaluation_metrics.py tests/test_evaluation_reporting.py tests/test_evaluation_runner.py tests/test_evaluation_baseline_snapshot.py tests/test_ig01c_evaluator.py tests/test_ig01d_baseline.py tests/test_w09_evaluation_evidence.py
66 passed in 1.54s
```

`git diff --check` passed.

I independently recomputed the evidence identifiers recorded in the package
report:

- Public DEV+TEST split fingerprint (HOLDOUT excluded):
  `sha256:28f18f9f01c59db148842052b4d26046f3a1517f081b2cb34a4cbdee0bda186c`.
- `evals/reports/w09/before-public.json` SHA-256:
  `404c28efed0ba419581d6a58eafac402994e9501dd5ac8753d11dfa2f8fd642a`.
- `evals/reports/w09/before-holdout.json` SHA-256:
  `3b058224712e9ad9545658c19ada2d02532e627dd8d57a8c22173f4b243d6ef2`.

## Prior findings

### Closed — IG01-D pair tamper handling

`reconcile_pair_report()` now fails closed for a persisted false candidate
gate before source access. With bound inputs, it freshly recomputes both
provider payloads and the comparison, compares them without timing telemetry,
and re-derives the pair status before returning verified evidence. Focused
tests cover both the false-gate case and comparison-payload tampering.

### Closed — generic bounded identifiers

Generic reports now enforce the bounded identifier grammar for provider,
fixture, suite, task, project, invariant, expected, selected, missing,
unexpected, forbidden, violation, and status-code identifiers. Identifier
arrays are length-bounded, and fields that require sorted uniqueness retain
that constraint. Focused tests reject oversized task and selected identifiers.

### Closed — content-free errors

Generic read failures now return the fixed message `evaluation report read
failed`, without a filesystem path or parser content. Validation errors no
longer interpolate rejected unknown keys, identifier values, task IDs, or
source values. Focused tests verify that a private report path is absent from
the error.

### Closed — package evidence documentation

The package report separately records the public split fingerprint and the
SHA-256 hashes of the public and HOLDOUT evidence reports. Independent
recomputation matched all three values.

## Boundary and compatibility

The correction remains inside the W-09 evaluation boundary. It does not change
production memory, capture, retrieval, routing, authority, compiler behavior,
corpus labels, thresholds, historical baseline artifacts, V2 promotion, or
Phase 20. Generic evidence remains legacy/unavailable without a provider
allowlist, and IG01-D promotion remains blocked when semantic feasibility is
unavailable.

No blocking findings remain at `c90a9ca06a9fc6661e224ea23490f9e2e5e7346e`.

VERDICT: SHIP
