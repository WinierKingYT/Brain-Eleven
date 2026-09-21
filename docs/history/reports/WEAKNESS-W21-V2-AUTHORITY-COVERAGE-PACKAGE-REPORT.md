# W-21 — V2 Authority Coverage Package Report

**PACKAGE:** W-21
**REVISION:** `02c05c0edef15ea1582c9c5b118e6593c596ef5b`
**OBJECTIVE:** Make the shadow V2 decision boundary fail closed when eligible
Router candidates do not have complete Phase 18 authority coverage.
**CONTRACT:** `WEAKNESS-W21-V2-AUTHORITY-COVERAGE-CONTRACT.md`, contract
reviewed **SHIP** at `e6bf48e`.

## Files changed

- `retrieval_decision_v2/engine.py`
- `tests/test_w21_authority_coverage.py`

## Root causes addressed

The V2 decision engine previously treated a missing or empty authority result
as an empty mapping. Eligible Router candidates could therefore be selected
without authority representation, and `authority_used` could claim coverage
that had not been established. The engine now computes the existing trusted
candidate eligibility set first, detects duplicate authority rows before any
dictionary collapse, requires one matching candidate/project authority row,
and returns a content-free `AUTHORITY_COVERAGE_UNAVAILABLE` failure for
missing, empty, partial or duplicate coverage. Existing Router/scope,
lifecycle, stale-revision and authority-scope precedence remains intact.

## Tests added

- Missing, empty and partial authority coverage fail closed.
- Duplicate authority IDs, including a foreign-project duplicate, fail before
  dictionary mapping.
- Complete `SUCCESS` and `DEGRADED` coverage preserve selection and degraded
  visibility.
- No eligible candidates remain deterministic and do not require authority.
- OFF mode remains empty without authority while stale/invalid precedence is
  preserved by the existing suite.
- Existing authority scope mismatch omits only the foreign row.
- Failure telemetry is bounded and content-free; no external file changes are
  produced by selection.

## Tests executed

- W-21 plus retrieval/authority/compiler focused suite: **114 passed**
- Full suite at exact revision: **1329 passed, 4 skipped, 2 warnings**
- Critical flake8 (`E9,F63,F7,F82`): **PASS**
- compileall: **PASS**
- `git diff --check`: **PASS**
- Independent focused review suite: **55 passed**

The two warnings are the existing FastAPI/Starlette dependency deprecation
warnings; no W-21 warning was introduced.

## Quality metrics before/after

- Before: missing/empty/partial authority could reach the selection loop;
  authority telemetry could overstate coverage.
- After: eligible candidates require complete candidate/project coverage, and
  uncovered or duplicate authority fails closed before selection.
- Ranking, Router scope, embedding providers and V2 delivery remain unchanged.

## Safety metrics

- Eligible candidate selected without complete authority coverage: **0** in the
  required missing/empty/partial/duplicate matrix.
- Wrong-project authority selected: **0**; scope mismatch remains omitted.
- Candidate IDs, memory text, prompts and secrets in failure telemetry: **0**.
- MemoryStore, StateStore, ProjectRegistry, authority cache and compiler cache
  writes introduced: **0**.

## Known limitations

V2 remains **SHADOW**. This package does not promote V2, alter SessionStart or
client delivery, tune retrieval quality, repair the optional-omission contract
(W-22), or unlock Phase 20. Native trust, latency and multi-session dogfood
remain W-07B gates.

## Open failures

W-21 package failures: **none**. W-07B and W-22 remain open outside this
bounded package.

## Independent review

Read-only implementation review at exact revision
`02c05c0edef15ea1582c9c5b118e6593c596ef5b` returned **SHIP**. It independently
verified missing/empty/partial/duplicate and cross-project duplicate closure,
complete SUCCESS/DEGRADED behavior, OFF/stale precedence, content-free
telemetry, no filesystem writes, focused tests and static gates. No P0, P1 or
P2 findings remain.

## Score before/after

- Scope and fail-closed safety: **8.5 → 8.7** (eligible V2 candidates can no
  longer pass the authority hand-off without complete coverage).
- V2 runtime readiness: **6.0 → 6.5** (shadow decision safety is stronger;
  promotion remains blocked).
- Semantic retrieval correctness and retrieval quality: unchanged.
- Other scorecard dimensions: unchanged.

## Verdict

**SHIP**
