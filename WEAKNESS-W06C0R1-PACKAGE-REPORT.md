# W-06C0R1 Package Report

**PACKAGE:** W-06C0R1 — answerability and provenance correction
**REVISION:** P1-A implementation/evidence chain `9ff0757` → `27c8ed2` →
`57365b8` → `6fdaf7f` → `c887e15` → `fb82bd8`
**OBJECTIVE:** Replace the insufficient W-06C0 feasibility corpus with an
answerable, independently attested corpus-v4 and a machine-checkable
provenance/provider-parity evaluator. Production retrieval code remains
unchanged.

## Files changed

- `evals/corpus-v4/**`: 60 DEV, 60 TEST, 30 HOLDOUT cases, attestations,
  manifest, and sealed holdout metadata.
- `evals/w06c0r1/**`: evaluator, CLI entry points, and content-free DEV/TEST/
  HOLDOUT evidence reports.
- `tests/test_w06c0r1_contract.py`: 15 focused contract tests.
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
- Safety leakage is a hard gate, including global-task rejection of
  project-scoped candidates.

## Tests executed

- Focused: `pytest tests/test_w06c0r1_contract.py -q` → **15 passed** after
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

- Manifest: `sha256:44c479541db5d4ebecc38ddb7d817b9cfd3ad625aa6db45c1dad3bd941060325`.
- Source fingerprint: `sha256:30aa8496316216af88b80bd9f1f8bc84e36a106fae094b18a725234e51ed7633`.
- Holdout seal: `sha256:c27c38190f4610b6c9c4b5537abce495efe34fea1249368f1c9415d24e658916`.
- DEV/TEST/HOLDOUT report hashes:
  `sha256:3f42b652e21ed772102d39851c45e1878a15d5a68459b05ea9fdf3b640bf3e69`,
  `sha256:95582d8430790af1a898902718a2529adb1257ba7c797edff7ecaef19ae6b992`,
  `sha256:90ea24dbcf987e0adebf50858cc5163586f209d809ee084f85d586e77006c72b`.
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
