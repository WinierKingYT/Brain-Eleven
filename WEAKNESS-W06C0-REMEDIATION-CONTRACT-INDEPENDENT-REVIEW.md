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

## P1-A implementation review — exact HEAD `0ea09d9`

**Verdict: FIX-FIRST**

Independent checks performed:

- `pytest tests/test_w06c0r1_contract.py -q` → **14 passed**
- Critical flake8 (`E9,F63,F7,F82`) on evaluator/tests → **PASS**
- `compileall` on evaluator/tests → **PASS**
- `git diff --check` → **PASS**
- `verify_manifest()`, `source_fingerprint()`, and `verify_seal()` → **PASS**
- Scope diff from `3f795f9` → **PASS**, with no production/forbidden paths

### Blocker A-01 — `--final-holdout` accepts a non-holdout split

`main()` validates the output path but never requires `args.split ==
"holdout"` when `--final-holdout` is supplied. I reproduced this with a
temporary canonical path and a stubbed `run_matrix`: the call proceeded with
`split="dev"`, `allow_holdout=True`, and the final flag. In a clean evidence
directory this can write a DEV report to the canonical `holdout.json` path and
corrupt the final-holdout boundary. The focused tests cover same-path and
alternate-path replay, but not this split mismatch.

The CLI must reject `--final-holdout --split dev` (and every non-`holdout`
split) before `run_matrix` or provider execution, with a focused test proving
the provider is not called.

### Blocker A-02 — final holdout evidence and package report hashes are stale

The current `evals/w06c0r1/evidence/holdout.json` contains the old seal hash
`sha256:9d9fcc...`, while the resealed canonical
`evals/corpus-v4/holdout/seal.json` contains
`sha256:d5803b...`. The package report records holdout report hash
`sha256:99cb95...`, but the current normalized holdout artifact hashes to
`sha256:616f6d...`. DEV/TEST hashes and manifest/source/seal verification pass;
the mismatch is specific to the final holdout evidence refresh.

The evidence chain must be regenerated or corrected under the bounded allowlist
so the final report's embedded seal reference, report hash, and package report
all describe the current sealed artifact. The one-time final-holdout boundary
must remain intact; the fix must not silently rerun or unlock HOLDOUT.

Until A-01 and A-02 are closed and independently rechecked, P1-A cannot be
accepted as SHIP.

## P1-A follow-up re-review — exact HEAD `fb82bd8`

The split guard is now correct: `main()` rejects every non-`holdout` split
before `run_matrix`, and the new focused test is present. The focused suite is
**15 passed**; critical flake8, compileall, and diff checks pass. Current
manifest, source, and seal verification also pass:

- manifest: `sha256:44c479...`
- source: `sha256:30aa849...`
- seal: `sha256:c27c3819...`

However, the committed final holdout artifact still embeds
`holdout_evidence.seal_hash = sha256:2c5cad...`, while the current canonical
seal is `sha256:c27c3819...`. The package report's raw DEV/TEST/HOLDOUT hashes
now match the current files, but the holdout artifact's internal seal binding
does not match the current seal. The final holdout evidence must be refreshed
or otherwise corrected under the bounded evidence allowlist, with a test that
checks the committed artifact's embedded seal and report hash against the
canonical seal. The one-time holdout boundary must remain intact.

**Follow-up verdict: FIX-FIRST.** A-01 is closed; A-02 remains open.

## P1-A final seal-binding re-review — exact HEAD `6b2f4fe`

The final follow-up closes A-02. Independent verification found:

- Focused W-06C0R1 suite: **16 passed**.
- `verify_manifest()`, `source_fingerprint()`, and `verify_seal()`: **PASS**.
- Committed DEV/TEST/HOLDOUT report hashes match the package report.
- Committed `holdout.json` embeds the current canonical seal
  `sha256:bad068ef...`.
- The new binding test checks the committed holdout artifact against the
  canonical seal.
- Scope verification passes, and the W-06C0R1 revision contains no production
  or forbidden runtime paths.
- Critical flake8, compileall, and diff checks pass.

The combined W-06C0/W-06C0R1 focused run remains **28 passed, 1 failed** only
because the historical W-06C0 scope test still compares against its old
predecessor boundary; that is the separately authorized P1-B compatibility
package and is explicitly retained as an open failure in the W-06C0R1 report.
It is not a P1-A implementation regression.

**Final P1-A verdict: SHIP.** The P1-A replay guard, canonical path, split
guard, evidence provenance, seal binding, and exact governance scope are
accepted. P1-B remains unimplemented and independently gated.

## P1-B implementation review — exact HEAD `9f67889`

**Verdict: FIX-FIRST**

Independent checks performed:

- Focused W-06C0 + W-06C0R1 suites: **31 passed**.
- Historical W-06C0 end revision resolves to the full
  `f676c91d0e41a7523dc2b96a131814b983401456` and is an ancestor of HEAD.
- Invalid and non-ancestor scope ends fail closed.
- The pinned old evaluator blob hash, W06C0R1 source/manifest/seal, and
  holdout artifact checks pass at the committed values.
- W06C0R1 scope verification, critical flake8, compileall, and diff checks
  pass. No production runtime paths changed.

### Blocker B-02 — compatibility metadata is not actually pinned

`_historical_scope_compatibility()` trusts the current contents of
`evals/w06c0r1/historical_scope_compat.json`. Its `compatibility_id` is checked,
but `scope_end_revision` and `expected_blob_sha256` are not compared against
immutable code constants or a separately authenticated metadata fingerprint.
The metadata path is inside the broadly allowed `evals/w06c0r1/` prefix.

I reproduced the bypass without changing tracked files: using a temporary
metadata object with the same compatibility ID, the current HEAD as
`scope_end_revision`, and the current old evaluator blob hash caused
`verify_scope_diff()` to return `PASS`. A later edit to the tracked metadata
could therefore authorize a different old evaluator revision/blob while the
scope gate still reports success. This violates the contract's “pinned,
one-time” exception and its requirement that later edits fail closed.

The implementation must authenticate the metadata itself or hard-bind the
expected full scope-end revision and old evaluator blob hash in a separately
versioned verifier path, then add a test that mutates both metadata values to
valid-looking alternatives and expects a hard failure. The exact additional
path rejection test should remain as well.

Until B-02 is closed and independently rechecked, P1-B cannot be accepted as
SHIP.
