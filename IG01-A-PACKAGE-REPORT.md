# IG01-A Package Report — Evaluation Contract

**PACKAGE:** IG01-A — Evaluation Contract
**REVISION UNDER REVIEW:** `84ed60d69e554dd893497b184db6de5bcecfceaa`
**REPORT COMMIT:** this evidence file is attached after the reviewed revision;
all test/review claims below are bound to `REVISION UNDER REVIEW`.
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

- Exact-head local focused suites at `da9ef22`: **179 passed**; the following
  contract-only gate-normalization commit changed no runtime code.
- Exact-head local syntax/critical checks: `flake8` critical **PASS**,
  `pyproject.toml` parse **PASS**, compile/import sanity **PASS**, `git diff --check`
  **PASS**.
- Exact-head local full unit/integration collection was **blocked by the host
  environment** because `defusedxml` is not installed in the active interpreter;
  no repository change caused this collection error.
- [Validation run 34289631318](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34289631318) at the reviewed revision: **SUCCESS**. Ubuntu/Windows unit, integration, privacy, smoke, coverage, Bandit, dependency, secret and Docker jobs passed; master-only public/evidence jobs are `NOT APPLICABLE`.
- [PRE-13 runtime run 34289631307](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34289631307) at the reviewed revision: Ubuntu runtime **PASS**, Windows runtime **PASS**; historical quality job **FAIL** remains visible and is deferred to later intelligence packages.

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
- Review at `759c03e…`: FIX-FIRST; family formulas, fail-closed case coverage,
  NA safeguards, safety alignment, comparability fields, package ordering and
  retrieval preference coverage were addressed in `da9ef22…`.
- Review at `da9ef22…`: FIX-FIRST; the nine-gate cardinality and report
  revision binding were the remaining document blockers; the gate set is
  normalized in `84ed60d…` and this report binds its evidence to that revision.
- Fresh independent read-only review of `84ed60d…` (`ig01a_reviewer6`):
  **SHIP**, with P0/P1/P2 findings absent. The reviewer confirms the contract
  is sound; the human 20-case checkpoint remains the only acceptance gate
  intentionally pending.

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
