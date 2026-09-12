# W-08 Contract Independent Read-Only Review

**PACKAGE:** W-08 Persistence Consistency Contract
**CONTRACT REVISION:** `90ac899`
**REVIEW TYPE:** Independent read-only contract review
**PHASE 20:** FROZEN / LOCKED
**V2:** SHADOW

## Scope and boundedness

- The first implementation slice is explicitly limited to the existing
  `ProjectRegistry` authority: additive revision metadata, stale-write checks,
  backup durability and rollback.
- W-08B coordinated backup, W-08C state-reference TOCTOU and W-08D typed API
  lifecycle updates are deferred contracts, not implementation authorization.
- MemoryStore, StateStore, ProjectRegistry replacement, capture, retrieval, V2
  and Phase 20 remain outside the slice.
- Existing package/legacy/bare-module identity and caller signatures are
  explicitly protected.

## Evidence and acceptance review

- Current registry evidence identifies the lock boundary, mutators, schema,
  missing revision/CAS and incomplete fsync/backup path.
- Schema version is frozen at `1`; revision is additive, missing legacy
  revisions normalize to `0`, and the first successful mutation persists the
  additive revision.
- CAS comparison is required after the latest load while holding the existing
  registry lock. Callers without `expected_revision` retain the current latest
  snapshot mutation behavior; CAS applies only when supplied explicitly.
- The two-writer test is now deterministic: one writer succeeds, the stale
  writer receives a typed conflict, and an explicit retry after reloading may
  succeed.
- Backup path, envelope, typed backup error, exact rollback API, monotonic
  rollback revision and stale rollback behavior are fixed in the contract.
- Required fault, corruption, identity, CLI parity, migration and mutation
  revision evidence is listed without expanding into deferred authorities.

## Prior FIX-FIRST findings and closure

The initial review returned `FIX-FIRST` for four gaps:

1. The two-writer acceptance criterion required both a stale conflict and both
   writes in the final set without defining a retry. The contract now requires
   explicit loser retry before both writes can be present.
2. The schema/revision representation was open-ended. The contract now freezes
   schema `1`, additive revision metadata and revision-zero legacy normalization.
3. Backup and rollback details were not concrete. The fixed path, envelope,
   typed errors and `rollback(expected_revision=...)` semantics are now exact.
4. Baseline refresh conflicted with the baseline freeze. Section 7 now permits
   only an official source-fingerprint-only refresh when corpus, labels,
   metrics, invariants and thresholds remain unchanged, and explicitly states
   that this exception overrides the general prohibition.

These changes close the review blockers without authorizing implementation.

## Open state

No production implementation has started under this contract. W-08A still
requires its own implementation evidence, full regression, fault-injection
tests and independent package review.

## Verdict

**SHIP**

The W-08 contract is bounded and reviewable at exact revision `90ac899`.
