# W-09 — Evaluation Evidence Integrity & Gate Semantics

PACKAGE: W-09 — Evaluation Evidence Integrity & Gate Semantics
REVISION: 2fbfac5 (implementation), follow-up report commit records reporting compatibility key
OBJECTIVE: Make evaluation safety, quality, capability, evidence, measurement and promotion states explicit without changing retrieval, corpus labels, thresholds, holdout inputs, V2, or Phase 20.

FILES CHANGED: evals/metrics.py, evals/reporting.py, evals/run.py, evals/baseline_snapshot.py, evals/ig01c/engine.py, evals/ig01c/contracts.py, evals/ig01d/baseline.py, evals/ig01d/contracts.py, focused evaluation tests, and the W-09 before-evidence JSON reports.
ROOT CAUSES ADDRESSED: Applicable unsupported invariants could serialize as passing; generic reports had no machine-readable quality/evidence distinction; strict report validation was shallow; IG01-C/IG01-D source identity was not recomputed against a checkout; timing telemetry had no bounded non-negative validation; CLI exposed an ambiguous gate field.

TESTS ADDED:
- tests/test_w09_evaluation_evidence.py: unsupported case semantics, generic measurement-only status, recursive unknown/raw-content rejection, schema-one legacy status, IG01-C exact three-file fingerprint/reconciliation and false-fingerprint tamper detection.
- tests/test_ig01d_baseline.py::test_timing_is_bounded_telemetry_not_identity: timing variation is accepted while negative timing is rejected.

BEFORE EVIDENCE:
- Exact pre-W-09 revision: 02a41b53c3ecfe2a92543aa4a9475b20234f9fdc.
- Focused command (metrics, reporting, runner, baseline snapshot, IG01-C and IG01-D): 56 passed in 1.09s.
- Public baseline report: evals/reports/w09/before-public.json; 101 cases, context_precision 0.18415841584158418, context_recall 0.8168316831683168, safety gate pass, exit 0.
- Dedicated HOLDOUT report: evals/reports/w09/before-holdout.json; 8 cases, context_precision 0.2, context_recall 0.75, safety gate pass, exit 0. It was generated separately and was not used for public evaluation.

TESTS EXECUTED:
- Focused W-09/IG01 command: 62 passed in 1.42s.
- Full regression: 1057 passed, 2 existing dependency warnings (exact current tree, reported by orchestration run).
- Critical flake8: .venv\\Scripts\\python.exe -m flake8 --select E9,F63,F7,F82 evals tests — PASS.
- Compile: .venv\\Scripts\\python.exe -m compileall -q evals — PASS.
- Diff: git diff --check — PASS.
- Generated IG01-D pair smoke: schema 2; provider reports carry explicit status; semantic feasibility remained unavailable as expected.

QUALITY METRICS BEFORE: Public precision 0.18415841584158418; recall 0.8168316831683168. No thresholds or labels changed.
QUALITY METRICS AFTER: Same measurement behavior; reports now distinguish measured/unavailable quality. Generic reports are never promotion evidence. IG01-D semantic feasibility remains SEMANTIC_UNAVAILABLE when no real provider exists.
SAFETY METRICS: Unsupported applicable invariants are non-passing; fail and unsupported states remain hard gate failures; no retrieval/capture behavior changed.
EVIDENCE RECONCILIATION: Generic reports are legacy/unavailable and excluded from verified evidence. IG01-C hashes exactly evals/ig01c/engine.py, contracts.py and metrics.py and exposes read-only reconcile_report(). IG01-D uses its frozen fingerprint allowlist plus public corpus and exposes read-only reconcile_baseline_report()/reconcile_pair_report(). Self-consistent false fingerprints classify tampered; old revision with matching old payload classifies stale. Baseline-v3 remains immutable; the compatibility adapter accepts only its known pre-W-09 source fingerprint while comparing all deterministic payload fields.
HOLDOUT BOUNDARY: Public reports remain DEV+TEST only; the captured HOLDOUT report is separate. No code reads HOLDOUT during public fingerprinting or public runner validation.
KNOWN LIMITATIONS: Generic Phase 15 reports have no provider-specific source allowlist and therefore remain evidence unavailable. IG01-D promotion is blocked when semantic feasibility is unavailable. Pair reconciliation verifies nested provider identity and status; future work may add a full pair recomputation contract. Existing schema-one artifacts are read-only legacy evidence and are not silently rewritten.
OPEN FAILURES: None introduced by W-09. Historical quality remains low and is intentionally visible for later bounded packages.
INDEPENDENT REVIEW: REVIEW PENDING — implementation author does not issue SHIP.
SCORE BEFORE: Evaluation evidence 6.5/10.
SCORE AFTER: Pending independent review; evidence semantics materially stronger, retrieval quality unchanged.
VERDICT: REVIEW PENDING

Status: REVIEW PENDING — independent read-only review required.
