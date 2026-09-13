# W-09 — Independent Read-Only Implementation Review

PACKAGE: W-09 — Evaluation Evidence Integrity & Gate Semantics  
REVIEW REVISION: `9a635541eb3c20ffb80e77e5969d03299f1f15c5`  
CONTRACT BASELINE: `02a41b53c3ecfe2a92543aa4a9475b20234f9fdc`  
REVIEW TYPE: independent read-only implementation review  

## Scope and evidence

I reviewed `WEAKNESS-W09-EVALUATION-EVIDENCE-CONTRACT.md`,
`WEAKNESS-W09-PACKAGE-REPORT.md`, the implementation diff from the approved
baseline through `9a63554`, the focused evaluation tests, and the IG01-C and
IG01-D source/reconciliation paths. The focused contract command passed 41
tests; critical flake8, `compileall`, and `git diff --check` also passed. The
full regression result recorded by the package report is 1057 passed with two
pre-existing dependency warnings.

## Findings

### P0 — IG01-D pair reconciliation can certify a failed safety comparison

`evals/ig01d/contracts.py:522-547` permits a versioned pair report whose
`comparison.candidate_gate.passed` is `false` while both invariant maps are
empty, and validates the pair status fields without relating them to that
gate. `evals/ig01d/baseline.py:183-207` reconciles only the nested provider
reports and feasibility. It does not reject a false candidate gate or
recompute/compare the pair comparison before returning the pair status.

I reproduced this against the exact review revision by building a fresh pair,
changing `candidate_gate.passed` to `false`, marking feasibility as measured,
and setting the persisted pair status to complete/eligible. The report passed
`validate_pair_report()` and `reconcile_pair_report(root='.',
corpus_root='evals/corpus-v2')` returned `evidence.state: verified`,
`measurement: complete`, and `promotion: eligible`.

This violates the contract's pair rule that a pair cannot be verified when
`comparison.candidate_gate.passed` is false, and the tamper matrix requiring
gate/payload mismatches to block measurement and promotion. A persisted safety
comparison can therefore remain promotion-eligible after its gate is changed.
The verifier must fail closed and bind the pair status to a freshly recomputed
comparison before it can certify the pair.

### P1 — Generic report identifiers are not bounded

`evals/reporting.py:495-500`, `:519-523`, and `:549-555` validate task IDs,
invariant names, and identifier arrays only as non-empty strings. The module
defines `_SAFE_CODE_RE`, but the generic validator does not apply a bounded
identifier rule to these evidence fields. I confirmed that a 1000-character
task ID and a 1000-character invariant name are accepted by
`_validate_report()` after the corresponding case/summary fields are updated.

This does not meet the generic strictness requirement for bounded identifiers
and leaves the content-free report boundary weaker than the IG01-C/IG01-D
contracts. Apply the bounded identifier grammar consistently to evidence keys
and identifier values, with bounded errors.

### P1 — Generic read/validation errors can disclose paths and untrusted keys

`evals/reporting.py:624-632` includes the filesystem path and parser exception
in `EvaluationReportError` when reading a report. Several generic validation
errors also interpolate untrusted field names (for example unknown fields and
source keys). The contract requires bounded, content-free error codes and
explicitly excludes filesystem paths and rejected untrusted content from
validation errors. The read and validation boundary should normalize failures
to bounded field/reason codes before this package can claim the privacy gate.

### Evidence documentation gap

The package report records test counts and the semantic-unavailable outcome,
but does not list the required public split fingerprints or generated report
hashes from the regression evidence plan. Add those exact hashes/fingerprints
when the implementation is corrected so the package evidence is independently
reproducible.

## Compatibility and boundary review

The unsupported case semantics are correctly non-passing. Generic reports are
marked unavailable/legacy, schema-one historical reports remain readable, and
baseline-v1/v2 manifests are not rewritten. The IG01-C digest uses the exact
three-file allowlist, IG01-D fingerprints exclude HOLDOUT, the 50-DEV probe
keeps seed 17/noise 24 with `holdout_included: false`, and the observable
public HOLDOUT read guard passes. These passing areas do not clear the pair
certification defect or the strict generic-boundary gaps above.

VERDICT: FIX-FIRST
