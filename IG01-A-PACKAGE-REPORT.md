# IG01-A Package Report — Evaluation Contract

**PACKAGE:** IG01-A — Evaluation Contract
**REVISION:** `06bc1cc5f0c12f80cc48ad0ceecca0348fd39aec`
**BASE REVISION:** `0f68e75cf71ba32065a90c7b2c8fd03fc476fde6`
**DATE:** 2026-09-09
**CONTRACT:** `IG01-A-EVALUATION-CONTRACT.md`
**STATUS:** FIX-FIRST / NOT ACCEPTED

## OBJECTIVE

Freeze the evaluation semantics, schemas, metrics, hard safety gates, corpus
provenance, split/holdout discipline and V1/V2 comparison protocol before any
corpus or evaluator implementation.

## FILES CHANGED

- `IG01-A-EVALUATION-CONTRACT.md`
- `IG01-EVALUATION-FOUNDATION.md`
- `PROJECT-STATUS.md`
- `DOCUMENTATION-AUTHORITY.md`
- `.github/workflows/test.yml`
- `.github/workflows/runtime.yml`

No production intelligence, retrieval, extraction, correction, evaluator or
runtime behavior was changed by IG01-A.

## ROOT CAUSES ADDRESSED

- Missing explicit evaluation contract and package boundary.
- Ambiguous metric denominators and context-precision interpretation.
- Incomplete schema/version and provenance requirements.
- Missing required category coverage and split-overlap controls.
- Unclear false-supersession and V1-equivalent recall gates.

## TESTS ADDED

No production or evaluator tests were added. This package is contract-only.

## TESTS EXECUTED

- `git diff --check`: PASS.
- Exact-head [Validation run 34286972242](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34286972242): SUCCESS at this revision. Unit, integration, privacy, smoke, coverage, Bandit, dependency, secret and Docker jobs passed; master-only public/evidence jobs were skipped as not applicable.
- Exact-head [PRE-13 runtime run 34286972245](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34286972245): Ubuntu PASS, Windows PASS, Bandit PASS; historical quality job FAIL retained.

## QUALITY METRICS BEFORE / AFTER

No production behavior was measured or changed. Evaluation-quality score
remains approximately **4/10**. Retrieval and extraction metrics are deferred
to IG01-D and are not claimed here.

## SAFETY METRICS

The contract defines independent zero-leakage and authority gates. No runtime
candidate or canonical mutation was executed by this document-only package.

## KNOWN LIMITATIONS / OPEN FAILURES

1. The required human checkpoint is pending: the user must inspect the 20
   contract spot-check cases. This is distinct from the later 20 random frozen
   corpus-label check required before IG-01 closes.
2. IG01-B corpus work and all evaluator implementation remain closed.
3. The current branch contains the prior user-side documentation archive
   commit; it is preserved and not rewritten.

## INDEPENDENT REVIEW

- Review at `a7730e0…`: FIX-FIRST; metric, provenance and schema gaps were
  addressed in subsequent commits.
- Review at `72fed79…`: FIX-FIRST; required coverage, context precision,
  denominator, provenance and V2 target gaps were addressed in `06bc1cc…`.
- Fresh review of `06bc1cc…`: pending at report creation; it must return SHIP
  before package closure.

## SCORE BEFORE / AFTER

| Dimension | Before | After |
|---|---:|---:|
| Evaluation quality | 4/10 approx. | Not yet scored; contract strengthened |
| Production intelligence | unchanged | unchanged |

## VERDICT

**FIX-FIRST / NOT ACCEPTED**

IG01-A cannot receive SHIP until the user completes the 20-case contract
checkpoint and a fresh independent reviewer returns SHIP. Phase 20 remains
**FROZEN / LOCKED**, V2 remains **SHADOW**, and IG01-B must not start.
