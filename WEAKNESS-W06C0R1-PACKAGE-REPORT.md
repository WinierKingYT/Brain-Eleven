# W-06C0R1 Package Report

**PACKAGE:** W-06C0R1 — answerability and provenance correction
**REVISION:** `09f6f7eac59ca3d4c8f28346606ffd3ad8ca8471`
**OBJECTIVE:** Replace the insufficient W-06C0 feasibility corpus with an
answerable, independently attested corpus-v4 and a machine-checkable
provenance/provider-parity evaluator. Production retrieval code remains
unchanged.

## Files changed

- `evals/corpus-v4/**`: 60 DEV, 60 TEST, 30 HOLDOUT cases, attestations,
  manifest, and sealed holdout metadata.
- `evals/w06c0r1/**`: evaluator, CLI entry points, and content-free DEV/TEST/
  HOLDOUT evidence reports.
- `tests/test_w06c0r1_contract.py`: 13 focused contract tests.

The exact allowlist check reports only these three prefixes; no production,
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
  replay of an existing final output is rejected before provider execution.
- Safety leakage is a hard gate, including global-task rejection of
  project-scoped candidates.

## Tests executed

- Focused: `pytest tests/test_w06c0r1_contract.py -q` → **13 passed**.
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

- Manifest: `sha256:2402edeea32d08b8b5fc342dcaa7051de8d5744033a56900f04d04da17b6e295`.
- Source fingerprint: `sha256:c967074ac969999e48c97101c878d5896539416e9893675923b0fd306ef3d510`.
- Holdout seal: `sha256:9d9fcc4324802d0bc2c9c4271598a9888c2c28e8e9f27b7ec77fb9ba440f940c`.
- DEV/TEST/HOLDOUT report hashes:
  `sha256:c2078cf5c7b3c02f6051638d37f83abc26e52c5a42935219c33c29fc0e0d57be`,
  `sha256:d29965f7affaa1c01a60a98f5e6d43569f75239fe4792dd1089fc2b0e5f2de9c`,
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
- The existing W-06C0 historical scope test fails on the accumulated master
  history and needs its own bounded compatibility decision.
- Independent read-only review has not yet been completed.

## Independent review

**REVIEW PENDING.** The implementation review must independently verify the
allowlist, answerability labels, holdout seal chronology, privacy boundary,
provider parity, and the stated historical regression.

## Score

**Before:** Evaluation quality 6.5/10 (W-06C0R1 blocker: no measurable
TEST/HOLDOUT quality).
**After:** Measurement infrastructure is evidence-complete for DEV/TEST/
HOLDOUT, but no retrieval-quality score increase is claimed until an
independent reviewer accepts the corpus and the historical full-suite failure
is dispositioned.

**VERDICT: REVIEW PENDING**
