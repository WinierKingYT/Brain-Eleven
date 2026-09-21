# W-09A Independent Review

REVISION: `31a436c3e7ad05ef11d714cf5ac0f39e2f179fd8`

VERDICT: SHIP

The W-09A implementation satisfies the frozen evaluation boundary. Public
evaluation reads exactly DEV+TEST (130 cases), while HOLDOUT is explicit,
separate, fingerprinted, and guarded. V1 and V2 execute against the same
generated candidate snapshot, candidate ordering, task fingerprints, seed,
K, normalization, and tie-breaking configuration. Reports include source,
corpus, candidate-content, and candidate-order fingerprints and remain
content-free.

The metric implementation covers precision, recall, F1, MRR, mandatory recall,
noise, selected count, over-K rejection, select-all/select-none controls, and
explicit token-unavailable status. Safety counters cover wrong-project,
forbidden, superseded, and resolved leakage, with invalid/unsupported quality
and blocked promotion states. No production retrieval, V2 rollout, or Phase
20 files changed in the W-09A implementation diff.

Validation performed:

- `python -m evals.w09a --provider both --split public` completed with
  `evidence=verified` and `quality=measured`.
- Public pair reports contain 130 cases for both V1 and V2; holdout evidence
  remains separate and blocked when quality is unavailable.
- `python -m compileall -q evals/w09a` passed.
- `git diff --check` passed.
- Package report records 9 focused tests and 1071 full-regression tests passed.

The local focused pytest command could not initialize because the checkout
environment lacks the pre-existing `defusedxml` dependency imported by the
repository root `conftest.py`; this does not change the recorded package
regression evidence or the successful direct W-09A execution.
