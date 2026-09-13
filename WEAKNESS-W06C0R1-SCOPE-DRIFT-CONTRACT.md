# W-06C0R1 — Historical Scope Drift Maintenance Contract

**Status:** CONTRACT REVIEW PENDING  
**Package:** W-06C0R1-SCOPE-DRIFT  
**Parent:** frozen W-06C0R1 evaluation/provenance harness  
**Phase 20:** FROZEN / LOCKED

## Finding

At exact W-03B HEAD `bf7fa5ddff3bd4bdd45409cede612e63d8f4c312`, the W-06C0R1
contract tests fail before any provider or corpus work runs. The current
`evals/w06c0r1/evaluation.py::verify_scope_diff()` compares
`IMPLEMENTATION_BASE_REVISION = 3f795f9` with the entire current checkout and
therefore treats later W-03B capture files and audit documents as if they were
W-06C0R1 implementation files. The failure is historical scope drift, not a
W-03B runtime or evaluator behavior change.

## Objective

Make the W-06C0R1 scope assertion a reproducible historical package check:
compare the W-06C0R1 base with its immutable package-end revision, while still
failing closed for new W-06C0R1/evidence/test changes made after that end.
Later unrelated packages must not invalidate an already closed evaluator.

## Bounded change

Allowed files:

- `evals/w06c0r1/evaluation.py`
- `tests/test_w06c0r1_contract.py`
- `WEAKNESS-W06C0R1-SCOPE-DRIFT-CONTRACT.md`
- `WEAKNESS-W06C0R1-SCOPE-DRIFT-PACKAGE-REPORT.md` (evidence only)
- `ENGINEERING-WEAK-POINTS-AUDIT.md` (ledger evidence only)

No corpus case, label, manifest, provider, metric, safety rule, runtime,
retrieval, capture, canonical store, or Phase 20 file may change.

## Required implementation contract

1. Add a full immutable `IMPLEMENTATION_SCOPE_END_REVISION` for the last
   W-06C0R1 evaluator/evidence scope commit (`0b5a262c437da13813e542c569857a68c2db7a69`,
   or a later exact revision only if the package report proves it is still the
   same package scope).
2. `verify_scope_diff()` must resolve and validate base, scope-end, and current
   HEAD revisions. Base must precede scope-end; scope-end must be an ancestor of
   HEAD. Invalid, missing, or non-ancestor revisions fail closed.
3. The historical package diff must be computed from base **to the pinned
   scope-end**, not from base to the current HEAD. The existing allowlist and
   one-time `evals/w06c0/evaluation.py` compatibility exception remain exact;
   they must not be broadened or removed.
4. Staged/unstaged worktree changes relative to current HEAD must still be
   checked. A changed path outside the existing W-06C0R1 allowlist/exception
   fails closed. Standing untracked local artifacts are not part of this
   evaluator scope.
5. Commits after the pinned end that touch W-06C0R1-owned source, corpus,
   evidence, or contract-test paths must fail closed and require a new bounded
   package end. This explicitly includes `evals/w06c0r1/evidence/**`,
   `evals/w06c0r1/evaluation.py`, `evals/w06c0r1/__init__.py`,
   `evals/w06c0r1/__main__.py`, `evals/corpus-v4/**`,
   `evals/w06c0/**`, and `tests/test_w06c0r1_*.py`.
6. `WEAKNESS-W06C0R1-PACKAGE-REPORT.md` and the named governance/review
   documents are documentation-only paths already present in the allowlist.
   Their post-end closure edits do not change evaluator scope and are allowed;
   they must never be used to permit an evaluator, corpus, evidence, or test
   edit. Commits in unrelated packages (including W-03B runtime and docs) are
   ignored by this historical assertion.
7. Returned evidence must expose `base_revision`, `scope_end_revision`,
   `head_revision`, `historical_changed_paths`, `post_end_changed_paths`,
   `worktree_changed_paths`, and a clear PASS status. No provider, corpus,
   label, metric, holdout, or safety result may change.

## Required tests and evidence

- Existing W-06C0R1 contract tests remain green.
- Prove current W-03B HEAD passes despite unrelated post-package files.
- Prove an invalid/non-ancestor scope end fails closed.
- Prove a staged/unstaged forbidden path fails closed.
- Prove a post-end change to evaluator/source/corpus/test paths fails closed.
- Prove a post-end change to `evals/w06c0r1/evidence/**` fails closed while a
  package-report-only closure edit remains allowed.
- Prove the old compatibility blob/hash and metadata tampering checks still
  fail closed.
- Run W-06C0 and W-06C0R1 focused suites, critical flake8 (`E9,F63,F7,F82`),
  compile/import sanity, `git diff --check`, and the full test suite.
- Re-run the W-03B focused suite after this package; no capture behavior or
  ownership code may change.

## Exit gate

Implementation is **REVIEW PENDING** until an independent read-only reviewer
confirms the pinned historical range, post-end fail-closed behavior, unchanged
allowlist/compatibility semantics, and full regression. The reviewer must
return exactly `SHIP`, `FIX-FIRST`, or `RETHINK`.

## Package report fields

`PACKAGE`, `REVISION`, `OBJECTIVE`, `FILES CHANGED`, `ROOT CAUSES ADDRESSED`,
`TESTS ADDED`, `TESTS EXECUTED`, `QUALITY METRICS BEFORE/AFTER`, `SAFETY
METRICS`, `KNOWN LIMITATIONS`, `OPEN FAILURES`, `INDEPENDENT REVIEW`, `SCORE
BEFORE/AFTER`, `VERDICT`.

**Plan status: CONTRACT REVIEW PENDING — implementation not authorized.**
