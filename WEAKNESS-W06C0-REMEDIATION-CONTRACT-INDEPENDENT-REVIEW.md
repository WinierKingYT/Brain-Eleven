# W-06C0 Remediation Contracts — Independent Review

**Review revision:** `04365f6d2001e2026609df5d5c6f638bb6369e64`
**Reviewer:** independent read-only review
**Review type:** bounded contract review; no implementation authorized
**Phase 20:** FROZEN / LOCKED

## Scope and method

Reviewed the two newly proposed remediation contracts, their allowed and
forbidden paths, required evidence, exit gates, and the existing W-06C0 and
W-06C0R1 scope verifiers. The working tree contains only the two new contract
documents as tracked changes; existing user-owned untracked artifacts were
left untouched.

## W-06C0R1 P1-A — Final holdout replay fix

**Verdict: SHIP**

The contract is bounded to the evaluator, its focused test, the three existing
evidence files, the existing holdout seal, and the package report. It explicitly
keeps the public `run_matrix` primitive separate from the final-holdout CLI
boundary, and requires the different-path rejection to happen before
`run_matrix` or provider execution. It also preserves same-path replay
rejection, requires platform-stable path resolution, and keeps production,
corpus labels, retrieval, ranking, and Phase 20 outside the allowlist.

The implementation must bind the canonical path to the existing
`evals/w06c0r1/evidence/holdout.json` path named by the allowlist. The contract
does not authorize a second durable token-consumption mechanism in the generic
API, which is the correct boundary for the reported CLI defect.

## W-06C0 P1-B — Historical scope compatibility

**Verdict: FIX-FIRST**

### Blocker B-01 — required W-06C0R1 regression is incompatible with the
allowlist

The contract permits changing `evals/w06c0/evaluation.py` and requires the
W-06C0R1 tests to remain green. However, the current W-06C0R1 scope verifier at
`evals/w06c0r1/evaluation.py::verify_scope_diff` compares from immutable base
`3f795f9` to the complete current index/worktree and explicitly treats the
`evals/w06c0/` prefix as forbidden. The proposed P1-B implementation changes
that exact forbidden prefix after `3f795f9`. Therefore, after P1-B is
implemented, `tests/test_w06c0r1_contract.py::test_explicit_corpus_version_and_source_scope`
will report the P1-B evaluator path as a forbidden W-06C0R1 scope change.

This is a deterministic cross-package failure, not a hypothetical concern.
The P1-B allowlist does not permit the W-06C0R1 scope verifier or its baseline
to be updated, so the stated “W-06C0R1 tests remain green” gate cannot be met
under the current contract. The contract must add an explicit compatibility
strategy before implementation, for example a versioned historical scope-end
boundary shared by the W-06C0R1 verifier, or a separately authorized narrow
scope-boundary update. The chosen strategy must preserve both packages'
fail-closed behavior and must not broaden either allowlist.

### Non-blocking precision note

`f676c91` is a short object name. The implementation should resolve and record
the full 40-character object ID in evidence while retaining the contract's
human-readable short reference. This is recommended for audit precision but
is secondary to B-01.

## Review gate result

P1-A is ready for implementation under its stated bounded contract. P1-B is
not implementation-ready until B-01 is resolved in the contract and the
allowlist/test interaction is independently re-reviewed.

**Overall review status: P1-A SHIP; P1-B FIX-FIRST.**

**Plan status:** contract review complete; no production implementation was
started or authorized by this review.

## P1-B amendment re-review — `4088516`

The amended contract adds the previously missing cross-package compatibility
boundary. It now permits only the two evaluator files, one pinned metadata
file, and narrowly scoped test/report assertions. The exception is constrained
by the full W-06C0 package-end revision, the expected post-fix blob hash, and
the requirement that no other `evals/w06c0/` path changes. It also requires
fresh W-06C0R1 source/evidence/seal fingerprints after its evaluator changes.
The existing short reference resolves to
`f676c91d0e41a7523dc2b96a131814b983401456`, which is an ancestor of review
HEAD.

The required tests now cover both the intended one-time exception and a later
or unpinned old-path edit failing closed. This addresses blocker B-01 without
turning the forbidden prefix into a broad allowlist entry. The historical W-06C0
range is pinned to its package end, while the current HEAD remains diagnostic.

**Amended P1-B verdict: SHIP.** Implementation remains subject to the
contract's independent package review and all listed evidence gates.

## P1-A governance-scope amendment re-review — `06923f8`

The amendment addresses the confirmed documentation-only scope failure with
four exact governance paths: the W-06C0R1 independent review, the P1-A
contract, the W-06C0 scope contract, and the remediation review. It explicitly
forbids directory, wildcard, and arbitrary-Markdown expansion. The existing
W-06C0R1 package report remains separately listed as an allowed package report;
the implementation must retain it while adding only these four exact paths.
No evaluator, provider, corpus, label, evidence, or runtime behavior is
changed by this amendment.

The amendment is narrow enough to let the known governance documents pass the
scope gate while preserving fail-closed behavior for any other documentation
or path. The required implementation tests must assert both that all named
exact files pass and that an unlisted Markdown file, directory, or wildcard
match fails.

**Amended P1-A verdict: SHIP.**
