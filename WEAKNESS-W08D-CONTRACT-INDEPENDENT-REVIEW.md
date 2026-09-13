# W-08D Typed API Lifecycle Contract — Independent Read-Only Review

**PACKAGE:** W-08D Typed API lifecycle
**CONTRACT REVISION:** `f4d83b1b1c01f4d8f7a2fa04d686d7dc3570de50`
**SOURCE REVISION NAMED BY CONTRACT:** `ecee32bfb00a1900f0bb79219df65be23e05745b`
**REVIEW TYPE:** Independent read-only contract review
**PHASE 20:** FROZEN / LOCKED
**V2:** SHADOW
**PRODUCTION/TEST CHANGES:** None

## Scope and method

I reviewed the amended contract at exact revision `f4d83b1`, the amendment
from `c244548`, and the unchanged source surfaces named by the contract at
`ecee32b`. The source revision is an ancestor of the contract revision. The
revision range contains only documentation changes (`ENGINEERING-WEAK-POINTS-
AUDIT.md`, the W-08C review, and this contract); no production, test,
evaluation, holdout, or Phase 20 file changed. This review accepts the
contract only. It does not authorize or implement W-08D.

## Amendment verification

### Transition matrix and lifecycle fields — PASS

Section 2 now freezes the API operations and source/target states: ordinary
active updates, resolve, supersede, delete, and same-terminal no-op repeats.
It requires the lifecycle fields needed by the existing manager, closes
terminal-to-terminal changes, rejects deleted-through-PUT and unknown/empty
statuses, and requires fixed 422 rejection without revision or graph effects.
Section 3 preserves the manager's timestamps, actor/source fields, notes and
supersession lineage while forbidding a second lifecycle authority. The
focused evidence list requires every legal and illegal matrix case,
terminal-repeat behavior, metadata preservation and package/legacy identity.

### Project scope request semantics — PASS

Section 5 makes the request boundary concrete: `MemoryUpdate.project_id` and
the DELETE query value are optional only at the boundary; global records ignore
the value, while project records require an exact match to the stored opaque
`project_id`. Missing and mismatched values have distinct fixed 422 codes and
are checked before any write. `project_root` is prohibited, absolute roots may
not enter canonical data, and fingerprint recomputation must preserve project
scope. The required focused tests cover missing, wrong and accepted scope
identities.

### Graph failure and privacy error table — PASS

Sections 6–8 place graph rebuild/invalidation after the successful canonical
commit and require projection failure to be visible as 503
`GRAPH_PROJECTION_DEGRADED`, with only committed status, bounded memory ID and
the fixed projection code in that payload. The fixed table covers 404 not
found, 409 revision conflict, 422 lifecycle/scope/capture safety failures and
the 503 projection failure. The same section forbids prompt content, project
roots, filesystem paths, secrets and raw tracebacks in API errors. Required
tests cover post-commit ordering, degraded projection behavior and privacy
sentinels.

### Caller inventory and source binding — PASS

The inventory binds the API mutation handlers and endpoint tests, the legacy
lifecycle manager and CLI, the package bridge, the canonical dedupe caller and
adapter, and lifecycle compatibility tests to exact source locations at
`ecee32b`. The repository source confirms the API endpoint is the current HTTP
lifecycle mutation surface and that the manager/dedupe package remains the
existing lifecycle authority. The implementation boundary explicitly keeps
those callers behaviorally unchanged.

### Verification and diff discipline — PASS

The regression section now requires focused lifecycle/API evidence, the full
test suite, critical flake8 checks, compile/import sanity, frozen evaluation
comparison and `git diff --check`. `git diff --check f4d83b1^ f4d83b1` is clean.
The exact revision comparison shows no production, test, evaluator, holdout or
Phase 20 changes.

## Remaining contract checks

- The one-store transaction/CAS boundary, lock/atomic-replace/backup behavior
  and no-hidden-retry rule remain explicit.
- Graph is a derived projection and cannot become an authority or precede the
  canonical commit.
- Existing lifecycle concepts, package/legacy identity, response compatibility,
  frozen evaluation data, V2 status and all deferred packages remain outside
  implementation scope.
- The listed focused tests and before/after fixture comparison are acceptance
  evidence for the future implementation; this document is not implementation
  evidence.

## Open findings

No contract-level P0/P1 finding remains at this revision. The future
implementation must still prove the complete matrix, exact field bounds and
manager-field mapping, scope isolation, CAS/concurrency behavior, graph
failure visibility, privacy boundary, regression suite and frozen-file diff at
its exact head.

## Verdict

**SHIP**

The W-08D contract is bounded, source-bound, privacy-aware and reviewable at
exact revision `f4d83b1`. This is a contract verdict only. W-08D remains
`REVIEW PENDING — implementation not authorized` until its production changes,
focused evidence, full regression, static gates and separate implementation
review pass.
