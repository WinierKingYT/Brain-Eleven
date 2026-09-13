# W-06C0R1 Package Report

**PACKAGE:** W-06C0R1 — answerability and provenance correction
**REVISION:** P1-A implementation/evidence chain `9ff0757` → `27c8ed2` →
`bbc2711` → `d70699a`
**OBJECTIVE:** Replace the insufficient W-06C0 feasibility corpus with an
answerable, independently attested corpus-v4 and a machine-checkable
provenance/provider-parity evaluator. Production retrieval code remains
unchanged.

## Files changed

- `evals/corpus-v4/**`: 60 DEV, 60 TEST, 30 HOLDOUT cases, attestations,
  manifest, and sealed holdout metadata.
- `evals/w06c0r1/**`: evaluator, CLI entry points, and content-free DEV/TEST/
  HOLDOUT evidence reports.
- `tests/test_w06c0r1_contract.py`: 14 focused contract tests.
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
  replay of an existing final output or a different output path is rejected
  before provider execution.
- Safety leakage is a hard gate, including global-task rejection of
  project-scoped candidates.

## Tests executed

- Focused: `pytest tests/test_w06c0r1_contract.py -q` → **14 passed** after
  P1-A evidence refresh.
- Critical syntax/static checks: critical flake8 (`E9,F63,F7,F82`),
  `compileall`, and `git diff --check` → **PASS**.
- Full suite at this revision: **1105 passed, 2 failed** on the first run.
  The cold native SessionStart failure was rerun in isolation and passed.
  The remaining failure is the pre-existing `tests/test_w06c0_contract.py`
  scope assertion: the frozen W-06C0 verifier compares from `fa5b920` and
  now necessarily sees later packages/documentation. No W-06C0 file was
  changed in this package; this remains an open regression for a separately
  authorized compatibility fix.
- Final holdout probe: `python -m evals.w06c0r1 --corpus-version 4 --split
  holdout --providers v1 --final-holdout ...` → **MEASURED**, with replay
  rejection verified.

## Evidence and metrics

- Manifest: `sha256:dc289344e6c2f2f90eeab06c6c4052bae129b9fb0c3135b311c2330d717306fd`.
- Source fingerprint: `sha256:8530deb30881aac3430e875552d910df8133f28120a3cac54a42a359d74dfa06`.
- Holdout seal: `sha256:d5803bb6f6b4b41099597487dfa8301f72267c5d935a202ba430571ad51fc81f`.
- DEV/TEST/HOLDOUT report hashes:
  `sha256:b8b691ac263bdfb61c2cb66dc79412882d4870f8b08e88f5cf11a02a25d2c954`,
  `sha256:f2a7c00b7fe77aea186698c6149091641c6ef3ff57836a9ad9f56474a6bde983`,
  `sha256:99cb95dad04f93c7c237624ab1ffd8d99b84c052613ee1ed86a45dd2c7555266`.
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
- The existing W-06C0 historical scope test remains open until the separately
  authorized P1-B compatibility package is implemented and reviewed.
- P1-A implementation has not yet received its independent implementation
  review; this report remains REVIEW PENDING.

## Independent review

**REVIEW PENDING.** The implementation review must independently verify the
canonical final-holdout path, exact governance allowlist, answerability labels,
holdout seal chronology, privacy boundary, provider parity, and the stated
historical regression.

## Score

**Before:** Evaluation quality 6.5/10 (W-06C0R1 blocker: no measurable
TEST/HOLDOUT quality).
**After:** P1-A closes the alternate-path replay defect in the evaluator, but
no retrieval-quality score increase is claimed until an independent reviewer
accepts the implementation and the historical full-suite failure is
dispositioned by P1-B.

**VERDICT: REVIEW PENDING**
