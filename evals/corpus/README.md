# Phase 15 public golden corpus

This directory contains only synthetic or anonymized evaluation tasks. A task
is valid only when it conforms to `../schemas/golden-task.schema.json` and its
memory identifiers exist in the selected synthetic vault fixture.

Suites are intentionally separated:

- `dev/` is visible while a retrieval algorithm is being developed.
- `test/` is the deterministic suite run on normal pull requests.
- `holdout/` is reserved for graduation and must not be used for tuning.

The initial `dev/` task is a contract smoke case, not a representative quality
claim. Phase 15-05 adds 108 generated, versioned public cases. The committed
tree therefore contains 109 tasks total: 54 in `dev/` (53 managed generated
cases plus the legacy smoke task), 47 in `test/`, and 8 in `holdout/`.
The runner’s `public` suite includes `dev/` and `test/` (101 tasks), while
`holdout` remains isolated. Regenerate or verify managed files only through
`python -m evals.corpus_builder --write` or `--check`.

The public corpus covers relevance, project isolation, lifecycle, supersession,
global/project combination, ambiguity, noise, conflict, and future-authority
cases. Holdout is committed for graduation only and is not a tuning suite.

Phase 15-04 evaluates normalized results deterministically: required and
useful records define precision/recall, while forbidden, wrong-project,
superseded, and resolved selections are reported as safety gates. Deliberate
synthetic noise is reported as unlabeled context and lowers precision.
Unsupported provider capabilities are explicitly reported as `unsupported`,
never treated as a pass.

Never put real personal memories in this tree. Local private corpus material
belongs under `evals/private/`, which is ignored by Git.
