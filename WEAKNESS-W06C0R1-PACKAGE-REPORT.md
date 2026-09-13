# W-06C0R1 Package Report

**PACKAGE:** W-06C0R1 — answerability and provenance correction
**REVISION:** P1-A implementation/evidence chain `9ff0757` → `27c8ed2` →
`57365b8` → `6fdaf7f` → `8203c05` → `6de8474` → `fb82bd8` → `42f45b6`
**OBJECTIVE:** Replace the insufficient W-06C0 feasibility corpus with an
answerable, independently attested corpus-v4 and a machine-checkable
provenance/provider-parity evaluator. Production retrieval code remains
unchanged.

## Files changed

- `evals/corpus-v4/**`: 60 DEV, 60 TEST, 30 HOLDOUT cases, attestations,
  manifest, and sealed holdout metadata.
- `evals/w06c0r1/**`: evaluator, CLI entry points, and content-free DEV/TEST/
  HOLDOUT evidence reports.
- `tests/test_w06c0r1_contract.py`: 16 focused contract tests.
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

- Focused: `pytest tests/test_w06c0r1_contract.py -q` → **16 passed** after
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

- Manifest: `sha256:b4352aa1814a2be6a3bfb8b73d2a9cf78f579d01052d512a70cefd30c4fe8be7`.
- Source fingerprint: `sha256:0dbc0ceac9b37e2cd3901de22746701c6e5014c70ec28d04776a7c8cd93a95c1`.
- Holdout seal: `sha256:bad068ef503cdc45960bd89599c17026cac0cde9ba34c96adc92f3b4987b58dd`.
- DEV/TEST/HOLDOUT report hashes:
  `sha256:408fc00a1b38e0fb7e7df0b792d0b2887f2f72b7961fec45af4451ea08c3d54a`,
  `sha256:388acceef226e1f0a92cc9dc24052948eae99b58c24157d7210838d5bd7b5d52`,
  `sha256:9cd0e427faba9ecfda0791c6c6f8fdc317f95ac6cde56baa20e4b75d4375066f`.
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
