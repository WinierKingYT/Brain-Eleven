# W-06C0 Package Report

PACKAGE: W-06C0 — Retrieval Feasibility & Answerability Foundation  
REVISION: 62b8aea (implementation and focused-test revision; this report is documentation-only)  
OBJECTIVE: Measure answerability and provider feasibility without changing production retrieval.

## FILES CHANGED

- `evals/corpus-v3/**` was frozen at the contract revision and was not changed by the implementation.
- `evals/w06c0/evaluation.py` adds explicit optional-provider probing, quality-state reporting, token-waste metrics, and a machine-enforced scope allowlist.
- `tests/test_w06c0_contract.py` adds optional-provider, insufficient-answerability, and scope-gate tests.
- No `brain_eleven/**`, `scripts/**`, active retrieval, authority, capture, or Phase 20 files changed.

## ROOT CAUSES ADDRESSED

- Optional embedding/reranker slots were always reported as not measured even when a probe was explicitly requested.
- A split with zero answerable cases was represented only by `null` aggregates, which could be misread as a quality pass.
- `token_waste` and the bounded scope assertion were absent from the evaluator evidence.

## TESTS ADDED

- Explicit `INSUFFICIENT_ANSWERABLE_CASES` state for TEST/HOLDOUT-style splits.
- Injected available embedding adapter path (`measure_optional=True`).
- Scope allowlist rejection/acceptance surface.

## TESTS EXECUTED

- Focused W-06C0 contract suite: 13 passed.
- Full repository suite at the implementation revision: 1094 passed, 2 warnings.
- Critical flake8 (`E9,F63,F7,F82`): pass.
- `compileall`: pass.
- `git diff --check`: pass.
- DEV/TEST/HOLDOUT matrices: reproducible; HOLDOUT required explicit `--final-holdout`.

## QUALITY METRICS BEFORE / AFTER

The preceding W-06B independent review recorded TEST precision `0.176667`, mandatory recall `0.825`, and MRR `0.424722`; those failures remain visible and were not tuned here.

W-06C0 v3 answerability counts are:

- DEV: 1 answerable, 69 unanswerable.
- TEST: 0 answerable, 60 unanswerable.
- HOLDOUT: 0 answerable, 30 unanswerable.

On the single answerable DEV case at K=5: V1 precision `0.20`, W-06B precision `0.20`, V2 precision `0.333333`, and deterministic authority lexical precision `0.333333`. TEST and HOLDOUT quality aggregates remain `null` with explicit state `INSUFFICIENT_ANSWERABLE_CASES`; this is not a pass.

The evaluator now reports `token_waste` for every scored K row and makes optional-provider execution explicit. The implementation does not claim retrieval improvement or authorize W-06C1.

## SAFETY METRICS

DEV, TEST, and HOLDOUT runs reported zero wrong-project, forbidden, superseded, resolved, and secret leakage for every measured core provider. Unavailable optional providers remain `UNAVAILABLE / NOT_MEASURED`; no synthetic vectors are emitted.

## KNOWN LIMITATIONS

- TEST and HOLDOUT contain no answerable cases, so provider quality feasibility is not measurable on those splits. The corpus labels remain frozen; creating a useful successor corpus requires a separately versioned contract.
- This machine has no configured real embedding or reranker provider. The injected adapter test proves the execution path, while the real slots remain explicitly `NOT_MEASURED`.
- `provenance_hash` format is validated and case-level immutability is enforced by the manifest fingerprints. The original v3 label-generation recipe is not recoverable from repository history, so derivation-level recomputation is not claimed.

## OPEN FAILURES

- P1: create a reviewed, versioned corpus with answerable TEST/HOLDOUT cases before using quality numbers for W-06C1 selection.
- P1: preserve or formally replace the provenance-generation recipe in that next corpus version.
- No production retrieval change is authorized while these remain open.

## INDEPENDENT REVIEW

The initial implementation review identified the limitations above as FIX-FIRST. A fresh read-only review of revision `62b8aea` and this report is required; self-review is not accepted.

## SCORE BEFORE / AFTER

- Evaluation quality before W-06C0: `6.5/10`.
- Evaluation quality after W-06C0: pending independent review; evidence integrity improved, but quality feasibility is intentionally not graduated.

VERDICT: REVIEW PENDING
