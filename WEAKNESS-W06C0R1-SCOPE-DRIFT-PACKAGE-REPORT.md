# W-06C0R1 Scope Drift Maintenance — Package Report

**PACKAGE:** W-06C0R1-SCOPE-DRIFT  
**REVISION:** `a6ac0971b684d637f88dfd9c7d13017f4ea7f3bf`  
**OBJECTIVE:** Bind the W-06C0R1 scope assertion to its immutable historical
package end and isolate later unrelated packages without weakening the
allowlist or evaluator safety gates.

## FILES CHANGED

- `evals/w06c0r1/evaluation.py`
- `tests/test_w06c0r1_contract.py`
- `evals/corpus-v4/manifest.json` (source-fingerprint/reseal binding only)
- `evals/corpus-v4/holdout/seal.json` (resealed generated binding only)
- `evals/w06c0r1/evidence/{dev,test,holdout}.json` (fresh generated evidence)
- `WEAKNESS-W06C0R1-SCOPE-DRIFT-PIN.json`
- `WEAKNESS-W06C0R1-SCOPE-DRIFT-PIN-R2.json`
- `WEAKNESS-W06C0R1-SCOPE-DRIFT-PIN-R3.json`
- `WEAKNESS-W06C0R1-SCOPE-DRIFT-PIN-R4.json`
- `WEAKNESS-W06C0R1-SCOPE-DRIFT-CONTRACT.md`

Corpus cases, attestations, labels, provider implementations, metrics,
holdout task decisions, runtime, retrieval, and Phase 20 files were not
changed.

## ROOT CAUSES ADDRESSED

- `verify_scope_diff()` previously compared the W-06C0R1 base directly with
  the current checkout, so later W-03B runtime and documentation commits were
  falsely reported as W-06C0R1 scope violations.
- The historical range is now pinned to
  `3f795f94dde199ba4e970705d37686ee4f50bc5d` →
  `0b5a262c437da13813e542c569857a68c2db7a69`.
- Later unrelated paths are reported diagnostically; later evaluator,
  corpus, evidence, compatibility, or contract-test changes fail closed
  unless they are the exact one-time hash-bound maintenance set.
- The original W-06C0 compatibility exception for
  `evals/w06c0/evaluation.py` remains pinned and fail-closed.

## TESTS ADDED

- Immutable scope-end and later-package separation assertions.
- Invalid/non-ancestor scope-end rejection.
- Explicit post-end owned-path detection.
- Scope-drift pin evidence tampering rejection.
- Unpinned post-end evaluator/evidence path rejection.

## TESTS EXECUTED

- W-06C0 + W-06C0R1 focused suites: **36 passed**.
- W-03B/capture/runtime focused suite: **127 passed, 2 warnings**.
- Full `pytest tests -q`: **1124 passed, 2 warnings** on the clean rerun.
- Critical flake8 (`E9,F63,F7,F82`): **PASS**.
- `compileall`: **PASS**.
- `git diff --check`: **PASS**.
- `verify_manifest()` and `verify_seal()`: **PASS**.
- `verify_scope_diff()`: **PASS**, with historical, post-end, and worktree
  path sets reported separately.

## QUALITY METRICS BEFORE / AFTER

- W-06C0R1 full regression at W-03B HEAD: **1116 passed, 2 failed** →
  **1124 passed, 0 failed** on the clean rerun. An earlier run had one
  unrelated cold-native-start flake; its focused bootstrap rerun passed 11/11.
- Historical scope reproducibility: current-HEAD dependent → pinned package
  end with explicit current-HEAD diagnostics.
- Corpus/provider quality metrics: unchanged after source-bound evidence
  refresh (case, candidate, task, metric, and safety fingerprints preserved).

## SAFETY METRICS

- Historical allowlist broadening: **0**.
- W-03B runtime/capture behavior changes in this package: **0**.
- Corpus case/label/attestation mutation: **0**.
- Provider/safety/holdout semantics changed: **0**.
- Invalid pin, invalid end revision, and unpinned post-end owned path: fail
  closed in focused tests.

## KNOWN LIMITATIONS

- The scope assertion intentionally requires a new bounded package and new
  pin for any future W-06C0R1 evaluator/corpus/evidence/test change.
- Documentation-only closure files are explicit exceptions; arbitrary later
  documentation is not admitted to the historical allowlist.
- This package changes evaluation provenance bindings only; it does not claim
  retrieval quality improvement or V2 promotion.

## OPEN FAILURES

- None observed in the exact local full regression or focused safety suites.
- Independent implementation review is still pending after immutable R4
  anchor enforcement.

## INDEPENDENT REVIEW

- Contract review: **SHIP** at `211c28b` (independent read-only review).
- Implementation review: **PENDING** (R4 implementation review required).

## SCORE BEFORE / AFTER

- Evaluation quality: **9.0 → 9.0** (measurement behavior unchanged).
- Repository truthfulness/scope evidence: **7.5 → provisional 8.5** pending
  independent implementation review.
- Capture/runtime scores: unchanged by this evaluator-only package.

## VERDICT

`REVIEW PENDING` — implementation and full regression are complete; the
independent reviewer must return exactly `SHIP`, `FIX-FIRST`, or `RETHINK`.
