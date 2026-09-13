PACKAGE: W-09A — Retrieval Evaluation Truth Foundation
REVISION: e4ae9427110d5c5487f3a5927fac4dd348ff01ba
OBJECTIVE: Establish a reproducible, content-free retrieval measurement boundary without changing retrieval behavior.
FILES CHANGED: evals/w09a/, tests/test_w09a_retrieval_evaluation.py, evals/reports/w09a/
ROOT CAUSES ADDRESSED: Frozen public/holdout split loading, same-input V1/V2 execution, candidate-content/source/corpus fingerprints, explicit quality/evidence/measurement/promotion states, hard safety counters, fail-closed candidate validation, and anti-select-all metrics.
TESTS ADDED: Public/holdout boundary, source and candidate fingerprints, real V1/V2 pair execution, content-free reports, hard safety counters, unknown-candidate rejection, over-K/select-all controls, and unavailable holdout quality handling.
TESTS EXECUTED: Focused W-09A suite: 9 passed. Critical flake8, compileall, and git diff --check passed. Full regression: 1070 passed, 2 existing dependency warnings at 7482dd9; the report-only revision does not change executable code and the same full suite is rerun for final evidence.
QUALITY METRICS BEFORE: W-09 public retrieval evidence remained low and generic reports were unavailable for verified promotion evidence.
QUALITY METRICS AFTER: Public DEV+TEST (130 cases, K=10): V1 precision@K 0.1723076923, recall@K 0.7653846154, F1 0.2780219780, MRR 0.4717948718, mandatory recall 0.7653846154, noise ratio 0.8276923077; V2 precision@K 0.1472100122, recall@K 0.4884615385, F1 0.1892385392, MRR 0.4214102564, mandatory recall 0.4884615385, noise ratio 0.8143284493. V2 is measured but does not beat V1; no promotion is authorized.
SAFETY METRICS: Public V1 and V2 wrong-project, forbidden, superseded, and resolved leakage are all 0. Public pair evidence is verified and content-free. Holdout is separate; V2 has one over-K invalid case, so holdout quality is unavailable and measurement remains incomplete.
EVIDENCE: public-pair.json SHA-256 0c1427dfb0329a407dc6dc0d1765d4bfce26573b7524fd4ce9d9007d239c1a22; holdout-pair.json SHA-256 1d5e3863032c69e653546014d803209f51b48fcc5b62f3590d106e5a3542fc0e.
KNOWN LIMITATIONS: Token counts are unavailable and reported explicitly; W-09A measures current providers but does not tune ranking, embeddings, labels, thresholds, V2 rollout, or Phase 20. Holdout is read-only evidence and is never used for tuning.
OPEN FAILURES: V2 remains below V1 on the public quality targets; this is an intentional visible finding for later retrieval work. Independent review is pending.
INDEPENDENT REVIEW: REVIEW PENDING — implementation author does not issue SHIP.
SCORE BEFORE: Retrieval evaluation truth 6.5/10.
SCORE AFTER: Pending independent review; measurement truth materially stronger, retrieval quality unchanged.
VERDICT: REVIEW PENDING
