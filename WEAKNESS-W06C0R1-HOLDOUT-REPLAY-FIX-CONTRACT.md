# W-06C0R1 P1-A — Final Holdout Replay Fix Contract

**Status:** CONTRACT REVIEW PENDING  
**Package:** W-06C0R1-P1A  
**Parent:** W-06C0R1 answerability/provenance harness  
**Phase 20:** FROZEN / LOCKED

## Objective

Close the independent-review P1 finding that the same final-holdout unlock
token can be replayed successfully by choosing a different output path. The
final holdout probe must have one durable, repository-owned evidence location;
an existing final output or any non-canonical output path must fail before a
provider is invoked.

## Evidence of the defect

`evals/w06c0r1/evaluation.py::main` currently rejects an existing output path,
but accepts a different path with the same token. The focused test only covers
reusing the same path. This contract changes that boundary only; it does not
change corpus labels, provider behavior, ranking, retrieval, or production
runtime.

## Bounded change

Allowed files:

- `evals/w06c0r1/evaluation.py`
- `tests/test_w06c0r1_contract.py`
- `evals/w06c0r1/evidence/dev.json`
- `evals/w06c0r1/evidence/test.json`
- `evals/w06c0r1/evidence/holdout.json`
- `evals/corpus-v4/holdout/seal.json`
- `docs/history/reviews/WEAKNESS-W06C0R1-CONTRACT-INDEPENDENT-REVIEW.md`
- `WEAKNESS-W06C0R1-HOLDOUT-REPLAY-FIX-CONTRACT.md`
- `WEAKNESS-W06C0-SCOPE-COMPAT-CONTRACT.md`
- `docs/history/reviews/WEAKNESS-W06C0-REMEDIATION-CONTRACT-INDEPENDENT-REVIEW.md`
- `WEAKNESS-W06C0R1-PACKAGE-REPORT.md`

The evaluator must define one canonical final evidence path under the existing
W-06C0R1 evidence directory. When `--final-holdout` is supplied, the CLI must
reject any output path whose resolved path differs from that canonical path,
before `run_matrix` or a provider is called. It must continue to reject a
second invocation when the canonical output already exists.

The W-06C0R1 scope verifier may allow only these four exact governance files
as `ALLOWED_SCOPE_FILES`; it must not broaden this to a directory, wildcard, or
arbitrary Markdown. They are review/contract evidence for this package and its
bounded remediation, not evaluator inputs.

The public `run_matrix(..., allow_holdout=True, unlock_token=...)` API remains
an evaluation primitive and does not claim to provide one-time global token
consumption. The one-time boundary is the final-holdout CLI/evidence path.

## Required tests and evidence

- Existing W-06C0R1 focused tests remain green.
- Add a test proving a different output path is rejected before provider work.
- Preserve the same-path replay rejection test.
- Verify canonical path resolution is stable on Windows and POSIX forms.
- Recompute source fingerprint, DEV/TEST evidence, and holdout evidence/seal
  fields required by the existing provenance contract.
- Run critical flake8, compile/import sanity, `git diff --check`, and the full
  suite. Any pre-existing W-06C0 historical failure remains visible.
- No production package, retrieval path, corpus case, label, or Phase 20 file
  may change.

## Exit gate

Implementation is **REVIEW PENDING** until an independent read-only reviewer
confirms the different-path replay is rejected before provider execution,
provenance/seal evidence is internally consistent, and the allowlist is clean.
Only that reviewer may return `SHIP`, `FIX-FIRST`, or `RETHINK`.

## Package report fields

`PACKAGE`, `REVISION`, `OBJECTIVE`, `FILES CHANGED`, `ROOT CAUSES ADDRESSED`,
`TESTS ADDED`, `TESTS EXECUTED`, `QUALITY METRICS BEFORE/AFTER`, `SAFETY
METRICS`, `KNOWN LIMITATIONS`, `OPEN FAILURES`, `INDEPENDENT REVIEW`, `SCORE
BEFORE/AFTER`, `VERDICT`.

**Plan status: CONTRACT REVIEW PENDING — implementation not authorized.**
