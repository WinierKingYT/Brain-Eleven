# W-06C0R1 Package Report

**PACKAGE:** W-06C0R1 — answerability and provenance correction
**REVISION:** P1-A/P1-B remediation chain `9ff0757` → `27c8ed2` →
`57365b8` → `6fdaf7f` → `8203c05` → `6de8474` → `fb82bd8` → `42f45b6`
→ `ca42787` → `aa44ac6` → `b79846b` → `4e61526` → `4bde156`
**OBJECTIVE:** Replace the insufficient W-06C0 feasibility corpus with an
answerable, independently attested corpus-v4 and a machine-checkable
provenance/provider-parity evaluator. Production retrieval code remains
unchanged.

## Files changed

- `evals/corpus-v4/**`: 60 DEV, 60 TEST, 30 HOLDOUT cases, attestations,
  manifest, and sealed holdout metadata.
- `evals/w06c0r1/**`: evaluator, CLI entry points, and content-free DEV/TEST/
  HOLDOUT evidence reports.
- `tests/test_w06c0r1_contract.py`: 18 focused contract tests.
- `evals/w06c0r1/historical_scope_compat.json`: one-time, hash-pinned
  compatibility metadata for the frozen W-06C0 evaluator.
- Exact governance/review documents listed in the evaluator scope allowlist.

The exact allowlist check permits only the corpus/evaluator/test prefixes, the
package report, and the four named governance documents; no production,
retrieval, predecessor corpus, or Phase 20 file changed.

## Root causes addressed

- The prior corpus had no answerable TEST/HOLDOUT cases, so provider quality
  was not measurable.
- Case payloads and two-labeler decisions are now bound by canonical hashes.
- Manifest, split, source, candidate-content, candidate-order, source-revision,
  and task-set fingerprints are reproduced and compared across providers.
- Provider inputs use opaque per-run task handles; public IDs and labels remain
  outside the provider boundary.
- HOLDOUT labels are sealed and require an explicit final-probe invocation;
  replay of an existing final output, a different output path, or a non-holdout
  split is rejected before provider execution.
- The historical W-06C0 scope verifier is pinned to its immutable package-end
  revision and rejects invalid/non-ancestor ends; W-06C0R1 accepts only the
  exact post-fix evaluator blob hash through the pinned compatibility metadata.
- Safety leakage is a hard gate, including global-task rejection of
  project-scoped candidates.

## Tests executed

- Focused: `pytest tests/test_w06c0_contract.py tests/test_w06c0r1_contract.py -q`
  → **31 passed** after
  P1-A evidence refresh.
- Critical syntax/static checks: critical flake8 (`E9,F63,F7,F82`),
  `compileall`, and `git diff --check` → **PASS**.
- Full suite after P1-B: **1112 passed, 2 warnings**.
- Critical flake8 (`E9,F63,F7,F82`), compileall, and `git diff --check`:
  **PASS**.
- Final holdout probe: `python -m evals.w06c0r1 --corpus-version 4 --split
  holdout --providers v1 --final-holdout ...` → **MEASURED**, with replay
  rejection verified.

## Evidence and metrics

- Manifest: `sha256:53050df3a3aee7fdb6b7626c3d7936d322c723b3b050c5cd6653e200add6492f`.
- Source fingerprint: `sha256:937b3bbcef835c0d6e855f1914383e1b512827d43dd3cc1a1a4805e76584d98c`.
- Holdout seal: `sha256:fc4dfbe36cc20f24f88362db49a2e40995d6041414af3a3e14b1c5a9f0a74fda`.
- DEV/TEST/HOLDOUT report hashes:
  `sha256:7a654ad9b2124d4bc91884d74d0e1bad7247216e8b1793b1bff2e9501edc0b65`,
  `sha256:621c90f71ca0bd20d5111bf30ca8a7b2af40f081ef427294aa3fa183e640fd6a`,
  `sha256:ca1439013d844be73fc47d1fc8c827a19ee6f40907c34282e3eb68b1d50fd787`.
- DEV/TEST/HOLDOUT each contain the required nine retrieval phenomena and meet
  the answerable minimum (60/60, 60/60, 30/30).
- V1/V2 and authority metrics are recorded in the evidence reports; optional
  embedding/reranker probes are explicitly `UNAVAILABLE/NOT_MEASURED` when the
  local provider is not installed. No provider is promoted by this package.
- All recorded safety counters are zero; a non-zero safety result raises a
  hard evaluator failure.

## Known limitations and open failures

- This package measures feasibility; it does not tune ranking, install an
  embedding provider, or change runtime retrieval.
- P1-A is independently SHIP. P1-B implementation still requires its own
  independent read-only review before the parent package can close.

## Independent review

**REVIEW PENDING.** P1-A is independently SHIP. P1-B requires independent
verification of the fixed historical range, pinned blob exception, fail-closed
unpinned edits, and full regression before W-06C0R1 can close.

## Score

**Before:** Evaluation quality 6.5/10 (W-06C0R1 blocker: no measurable
TEST/HOLDOUT quality).
**After:** P1-A closes the alternate-path replay defect in the evaluator, but
no retrieval-quality score increase is claimed until an independent reviewer
accepts the implementation and the historical full-suite failure is
dispositioned by P1-B.

**VERDICT: REVIEW PENDING**
