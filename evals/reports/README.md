# Evaluation report artifacts

`evals.reporting` writes deterministic JSON reports with aggregate metrics,
hard-gate outcomes, and identifier-only per-case diagnostics. Reports never
copy task prompts or memory content.

`baseline-v1.json` is the committed public baseline. Its source fingerprint
covers the evaluator, schemas, corpus, fixture, and relevant compiler inputs;
a test refuses a stale or hand-edited snapshot. Refresh it deliberately with
`python -m evals.baseline_snapshot --write`.

Ad hoc or private-corpus reports belong in `evals/reports/local/`, which is
ignored by Git.
