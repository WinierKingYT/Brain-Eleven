# IG01-C Package Report — Evaluation Engine

**PACKAGE:** IG01-C  
**REVISION:** `0df4387077b5f0c3347fed91ae20d8d07c9f4861`
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

## Root causes addressed

The existing Phase-15 evaluator measured only a narrow retrieval projection.
IG01-C adds a separate pure evaluator surface for retrieval/context, extraction,
reference resolution, lifecycle and capture metrics, with explicit
denominators, `not_applicable` handling and content-free safety events. The
engine rejects missing/duplicate outputs, unknown gates and raw-content report
fields. It does not import production intelligence or write canonical state.

The final hardening also validates the complete content-free `SafetyEvent`
shape in every gate review record, binds records to known gate/case IDs,
rejects unsafe IDs/detail codes, and checks count, rate and threshold
consistency. This closes the report-tampering gap found during independent
review.

## Tests added

`tests/test_ig01c_evaluator.py` covers:

- Precision@K, Recall@K, F1, MRR, mandatory recall, noise and token waste;
- select-all/select-none anti-gaming controls;
- fixture-owned project/lifecycle leakage checks;
- assistant-as-user, false-commitment and canonical-write rejection;
- reference ambiguity, cross-project target and false supersession;
- lifecycle cycle detection;
- capture counters and content-free report validation;
- strict missing/unexpected output handling and current IG01-B corpus smoke;
- malformed, raw and inconsistent gate review-record rejection.

## Tests executed

- Exact-head `compileall` and import sanity: **PASS** using the bundled Python
  runtime.
- Local targeted smoke for report generation, strict schema validation,
  select-all/select-none controls and review-record tampering: **PASS**.
- Local pytest: **NOT AVAILABLE** in the desktop runtime (`pytest` is not
  installed); revision-bound GitHub Validation is the authoritative test
  evidence and is not replaced by this local check.
- Exact-head GitHub Validation run [#34332769209](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34332769209): **PASS**.
  Ubuntu/Windows unit, integration, IG01-B corpus integrity, IG01-C evaluator,
  privacy, shadow suites, coverage, dependency, secret, Bandit and Docker
  security jobs passed.
- Exact-head PRE-13 runtime run [#34332769185](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34332769185): runtime Linux/Windows and
  security steps **PASS**; the historical PRE-13 quality holdout remains
  visibly **FAIL** and is retained for later intelligence work.

## Quality metrics

- **Evaluation quality before:** 4/10.
- **Evaluation quality after:** 9/10 (measurement quality only).
- Retrieval, extraction, correction, task understanding, V2 production and
  daily-use scores are intentionally unchanged; IG01-C does not tune them.

## Safety metrics

- Report output is content-free and source metadata is restricted to hashes,
  seed and retrieval parameters.
- Hard-zero safety gates remain independently represented and cannot be hidden
  by aggregate metrics.
- Near-zero gates require a review record per event and now enforce exact event
  shape plus count/rate/threshold consistency.
- Validation and runtime security controls pass. The historical PRE-13 quality
  failure is visible and is not relabeled as an evaluator pass.

## Known limitations

The evaluator tests use deterministic primitive controls and do not constitute
V1/V2 baseline measurement. Human label review and baseline measurement belong
to the later bounded packages. The current IG01-B V2 corpus has only three
reference-resolution cases per language, so release-mode benchmark validation
will reject that corpus until it is expanded/versioned; exploratory smoke uses
an explicit non-release mode. Synthetic controls cannot establish production
quality.

## Open failures and boundaries

- No IG01-C P0 remains open.
- Historical PRE-13 intelligence quality failure remains an explicitly tracked
  P1 follow-up for later packages.
- IG01-D baseline measurement is not started in this turn.
- Phase 20 remains **FROZEN / LOCKED** and V2 remains **SHADOW**.

## Independent review

Independent read-only review found the implementation, controls, privacy,
metric schema, package scope and Phase 20/V2 boundaries sound after the bounded
review-record hardening. The review is accepted as **SHIP** for this exact
revision and its revision-bound CI evidence.

## Score

- **Score before:** 4/10 (evaluation quality).
- **Score after:** 9/10 (evaluation quality only).

## Verdict

**SHIP** — IG01-C evaluation engine and anti-gaming contract are closed. IG01-D
remains unopened until a new bounded package is explicitly started and the
same sequencing/review rules are applied.
