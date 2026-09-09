# IG01-C Package Report — Evaluation Engine

**PACKAGE:** IG01-C  
**REVISION:** `320450c13eb7a28c8e8cbaaf8b101be3badc069b`
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
- Review remediation chain: independent reviews returned **FIX-FIRST** for
  `faba5c6`, `32dc910` and `89b426e`; the findings covered aggregation,
  proposition identity, privacy, anti-gaming, scope, token-waste, ECE,
  counter invariants, report controls, context exclusion and auditability.
  They are addressed in `32dc910`, `c018b38`, `89b426e`, `fe3affd` and
  `320450c`.
- Exact-head GitHub Validation run [#34330234587](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34330234587): **PASS**.
  IG01-C evaluator, unit, integration, privacy, shadow, coverage and security
  jobs passed.
- Exact-head PRE-13 runtime run [#34330234633](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34330234633): runtime Linux/Windows and
  security steps **PASS**; the historical PRE-13 quality holdout remains
  visibly **FAIL** and is retained for later intelligence work.
- Independent read-only final review of this exact revision: **PENDING**.

## Quality and safety metrics

Evaluation quality before: **4/10**.  After implementation: **pending review**.
The package does not claim improved retrieval, extraction, correction or daily
use behavior. The nine IG01-A safety gates remain independently reported;
positive near-zero events require review records.

## Known limitations

The evaluator tests use deterministic primitive controls and do not constitute
V1/V2 baseline measurement. Human label review and baseline measurement belong
to the later bounded packages. The current IG01-B V2 corpus has only three
reference-resolution cases per language, so release-mode benchmark validation
will reject that corpus until it is expanded/versioned; exploratory smoke uses
an explicit non-release mode. Synthetic control outputs cannot establish
production quality.

## Open failures

Independent read-only final review and package acceptance remain open.
IG01-D is not started. The exact implementation-head CI gate is closed by the
two revision-bound runs above.

## Verdict

**FIX-FIRST / NOT ACCEPTED** until the independent read-only re-review returns
`SHIP`. Exact-head CI is green after the remediation, but this package remains
open until review acceptance is recorded. Phase 20 remains `FROZEN / LOCKED`
and V2 remains `SHADOW`.
