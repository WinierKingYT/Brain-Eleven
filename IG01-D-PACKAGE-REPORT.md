# IG01-D Package Report — Baseline Measurement

**Status:** ACTIVE / IMPLEMENTATION IN PROGRESS
**Verdict:** FIX-FIRST / NOT ACCEPTED

This report is a placeholder until the exact implementation revision has
produced paired V1/V2 evidence and the independent read-only reviewer has
returned a strict `SHIP`, `FIX-FIRST` or `RETHINK` verdict. It intentionally
does not imply that IG01-D is closed.

| Field | Value |
|---|---|
| PACKAGE | IG01-D — Baseline Measurement |
| REVISION | pending implementation commit |
| OBJECTIVE | Measure V1 and V2 on one frozen public corpus without tuning production |
| FILES CHANGED | `evals/ig01d/**`, `tests/test_ig01d_baseline.py`, CI measurement job |
| ROOT CAUSES ADDRESSED | No revision-bound paired baseline; no explicit split/fingerprint contract |
| TESTS ADDED | IG01-D report, fingerprint, no-HOLDOUT and content-free contract tests |
| TESTS EXECUTED | pending exact-head local/remote evidence |
| QUALITY METRICS BEFORE | V1 compatibility report: precision 0.18, recall 0.803846 (130 public cases) |
| QUALITY METRICS AFTER | pending paired V1/V2 run |
| SAFETY METRICS | Existing V1 report has zero wrong-project, forbidden, superseded and resolved leakage; paired report pending |
| KNOWN LIMITATIONS | Normalized provider contract has no token counts; real embedding + cross-encoder spike may be unavailable |
| OPEN FAILURES | Exact-head CI, paired evidence, feasibility evidence and independent review |
| INDEPENDENT REVIEW | pending; self-review is not acceptance |
| SCORE BEFORE | Evaluation quality 4/10 (program estimate) |
| SCORE AFTER | pending independent score |
| VERDICT | FIX-FIRST / NOT ACCEPTED |

IG01-E and IG-03 remain unopened. Phase 20 remains `FROZEN / LOCKED` and V2
remains `SHADOW`.

