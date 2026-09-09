# IG01-C Package Report — Evaluation Engine

**PACKAGE:** IG01-C  
**REVISION:** `faba5c6b27ad2baca4eaffd473e00e57742b7b67`
**OBJECTIVE:** Implement a deterministic, production-independent evaluator
for the frozen IG01-B corpus and normalized outputs.

## Files changed

- `IG01-C-EVALUATOR-CONTRACT.md`
- `evals/ig01c/contracts.py`
- `evals/ig01c/metrics.py`
- `evals/ig01c/engine.py`
- `evals/ig01c/__init__.py`
- `tests/test_ig01c_evaluator.py`
- `.github/workflows/test.yml`
- `README.md`, `PROJECT-STATUS.md`, `IG01-EVALUATION-FOUNDATION.md`,
  `DOCUMENTATION-AUTHORITY.md`

## Objective and root causes addressed

The existing Phase-15 evaluator measured only a narrow retrieval projection.
IG01-C adds a separate pure evaluator surface for retrieval/context, extraction,
reference resolution, lifecycle and capture metrics, with explicit
denominators, `not_applicable` handling and content-free safety events. The
engine rejects missing/duplicate outputs, unknown gates and raw-content report
fields. It does not import production intelligence or write canonical state.

## Tests added

`tests/test_ig01c_evaluator.py` covers:

- Precision@K, Recall@K, F1, MRR, mandatory recall, noise and token waste;
- select-all/select-none anti-gaming controls;
- fixture-owned project/lifecycle leakage checks;
- assistant-as-user, false-commitment and canonical-write rejection;
- reference ambiguity, cross-project target and false supersession;
- lifecycle cycle detection;
- capture counters and content-free report validation;
- strict missing/unexpected output handling and current IG01-B corpus smoke.

## Tests executed

- Exact-head `compileall` and import sanity: **PASS** using the bundled Python
  runtime.
- Local pytest: **NOT AVAILABLE** in the desktop runtime (`pytest` is not
  installed); the dedicated revision-bound GitHub Validation job is required
  evidence and is not replaced by this local check.
- Exact-head GitHub Validation run [#34325013315](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34325013315): **PASS**.
  The IG01-C evaluator job reported `9 passed in 0.11s`; unit, integration,
  privacy, router/authority/compiler shadow and coverage jobs also passed.
- Exact-head PRE-13 runtime run [#34325013480](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34325013480): runtime Linux/Windows and
  Bandit/security steps **PASS**. The historical independent PRE-13 quality
  holdout remains **FAIL** (`precision=0.6667`, `required_recall=0.7059`), as
  expected; this is retained as a future intelligence-remediation failure and
  does not get relabeled as an evaluator failure.
- Independent read-only review: **PENDING**.

## Quality and safety metrics

Evaluation quality before: **4/10**.  After implementation: **pending review**.
The package does not claim improved retrieval, extraction, correction or daily
use behavior. The nine IG01-A safety gates remain independently reported;
positive near-zero events require review records.

## Known limitations

The evaluator tests use deterministic primitive controls and do not constitute
V1/V2 baseline measurement. Human label review and baseline measurement belong
to the later bounded packages. Synthetic control outputs cannot establish
production quality.

## Open failures

Independent read-only review and final package acceptance remain open. IG01-D
is not started. The exact implementation-head CI gate is closed by the two
revision-bound runs above.

## Verdict

**FIX-FIRST / NOT ACCEPTED** until the independent read-only review returns
`SHIP`. Exact-head CI is green, but this package remains open until review
acceptance is recorded. Phase 20 remains `FROZEN / LOCKED` and V2 remains
`SHADOW`.
