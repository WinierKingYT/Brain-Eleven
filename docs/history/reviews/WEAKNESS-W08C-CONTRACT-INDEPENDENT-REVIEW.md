# W-08C State Reference Guard Contract — Independent Read-Only Review

**PACKAGE:** W-08C — StateStore memory-reference commit guard  
**CONTRACT REVISION:** `7f175b3`  
**SOURCE REVISION NAMED BY CONTRACT:** `8932018`  
**REVIEW TYPE:** Independent read-only contract review  
**PHASE 20:** FROZEN / LOCKED  
**V2:** SHADOW  
**PRODUCTION/TEST CHANGES:** None

## Scope and method

I reviewed the W-08C contract at the exact revision above, then independently
checked the source surfaces named by it: `scripts/state_store.py`,
`scripts/state_resolver.py`, `scripts/memory_store.py`,
`scripts/memory_store_lock.py`, `brain_eleven/infrastructure/locking.py`,
`brain_eleven/runtime/migration.py`, `scripts/memory_backup.py`, the state
CLI, lifecycle/API writers, and the existing state/authority/evaluation
tests. The working tree had no tracked production or test changes attributable
to this review. This document is a contract review only; it does not authorize
implementation and does not treat a future implementation as complete.

## Current-reality verification

### Validation-to-commit race — PASS

The current code validates a memory through `StateService._validate_memory_reference`
at `scripts/state_store.py:993-1007`, then enters the independent state
transaction at `:1027-1035` for `add_memory_reference`. The blocker path calls
the same validator at `:1047-1051` before its state transaction. The contract
correctly identifies that the state CAS alone cannot detect a memory change in
that gap and bounds the fix to these two paths.

### Canonical authorities and persistence — PASS

`MemoryStore.transact` reloads and mutates under `memory_store_lock` at
`scripts/memory_store.py:158-177`; `StateStore._transact_project` reloads,
checks its project revision, appends the existing audit event and persists
under the state sidecar lock at `scripts/state_store.py:598-657`. The contract
does not introduce a second writer, direct JSON write, schema field or
cross-authority revision in either document.

### Lock order — PASS

The contract freezes only:

```text
memory_store_lock(vault) -> file_lock(project-state.json)
```

This matches the existing explicit order in `brain_eleven/runtime/migration.py`.
The current MemoryStore and StateStore transactions are individually locked,
and the W-08B backup reader does not hold either authority lock while reading.
The contract explicitly forbids adding the reverse order, a second lock name,
or unbounded work while the nested locks are held. That makes the proposed
linearization boundary reviewable and keeps deadlock analysis bounded.

### Lifecycle and scope policy — PASS

The repository fixtures and authority tests contain active, resolved and
superseded records; `scripts/search-api.py` also uses the canonical
`MemoryStore.transact` path for soft deletion. The contract’s closed policy is
consistent with those facts:

- only `validated_memory` can be referenced;
- global records are project-independent;
- project records require the exact opaque project ID;
- missing/status-less records preserve legacy active behavior;
- resolved and superseded records remain valid historical evidence;
- deleted and unknown explicit statuses fail closed;
- rejected-memory-only IDs remain unreferenceable.

It correctly separates reference validity from ordinary retrieval eligibility,
so preserving a historical blocker reference does not authorize stale memory
retrieval.

### State CAS, replay and audit — PASS

The existing state CAS at `scripts/state_store.py:631-632`, duplicate-reference
guard at `:1020-1025`, audit event shape at `:641-649`, and operation-receipt
handling at `:620-630` are named as compatibility boundaries. The contract
requires stale revisions and guard failures to leave both authorities and the
audit lineage unchanged, while a successful reference creates one existing
event and one revision. It also covers the `add_blocker(memory_ref=...)` path,
which prevents the same race from surviving through a second public API.

### Resolver compatibility — PASS

`StateResolver._reference_health` currently returns the stable
`valid`/`dangling`/`wrong_project` shape. The contract keeps that shape, adds
only the explicitly bounded classification of deleted/unknown-status targets
as dangling, and preserves resolved/superseded historical references when
scope still matches. No state schema, event shape, or evaluator label change
is authorized.

### Privacy and failure boundaries — PASS

The proposed snapshot contains only a revision, opaque memory ID, scope,
project ID and normalized status; it is explicitly ephemeral. The contract
forbids content, roots, prompts, secrets and unbounded underlying exception
text in new guard errors, result metadata, audit additions and evidence. It
also requires memory lock timeout and snapshot mismatch to map to a closed set
of typed reasons, with no hidden retry or successful empty reference. Existing
opaque-ID compatibility messages are clearly bounded.

### Evaluation and regression boundary — PASS

The focused evidence list covers valid/invalid lifecycle states, scope,
TOCTOU contention, lock timeout, blocker references, stale state CAS,
duplicate replay, audit lineage, privacy sentinels and package identity. The
contract preserves the frozen `evals/task_state_eval.py` cases, labels,
thresholds and baseline fields, and requires exact-head focused/full/static
verification. W-08D, retrieval, capture, V2 and Phase 20 remain outside the
package.

## Implementation cautions (non-blocking)

1. The held memory lock must remain active through the call to
   `StateStore._transact_project`; a helper that returns a validated ID and
   releases the lock before `_mutate` would recreate the original TOCTOU.
2. The lock-contention test must use a separate thread/process or an explicit
   deterministic hook. Calling `MemoryStore.transact` synchronously from the
   lock holder would self-block and would not prove serialization.
3. The existing active-project check is performed before the StateStore lock
   (`StateService._mutate:724`). W-08C should preserve and test the existing
   precondition, but must not claim that registry status changes are made
   linearizable; registry lifecycle coordination is outside this package.
4. `StateResolver` remains a read-side view and may observe a later lifecycle
   mutation after a valid reference was committed. The contract correctly
   leaves that visibility policy to the resolver and W-08D rather than adding
   a second writer or reference rewrite.

These cautions do not block the bounded contract because each is explicitly
covered by the implementation boundary, the required evidence, or the
deferred W-08D scope.

## Gate review

| Gate | Result | Evidence |
|---|---|---|
| Exact contract/source binding | PASS | Contract revision `7f175b3`; source revision `8932018`; implementation has not started. |
| Bounded scope | PASS | Only the two StateService reference paths and narrow resolver classification are in scope. |
| Linearizable memory/state commit | PASS | Held memory lock through existing state transaction; stale unlocked validation is explicitly forbidden. |
| Lock/deadlock safety | PASS | Existing memory→state order is confirmed; reverse order and unbounded nested work are forbidden. |
| Lifecycle/status policy | PASS | Active/resolved/superseded/deleted/unknown behavior is closed and testable. |
| Scope isolation | PASS | Global/project rules and exact opaque project identity are preserved. |
| CAS/replay/audit compatibility | PASS | Existing state CAS, duplicate guard, operation receipt and event shapes are frozen. |
| Authority boundary | PASS | No new store, direct file write, schema field or cross-authority revision. |
| Privacy | PASS | New guard failures and ephemeral metadata are bounded; sentinel tests are required. |
| Evaluation/holdout discipline | PASS | State evaluator and all corpus/threshold data remain immutable. |
| Implementation authorization boundary | PASS | Review accepts the contract only; future code still requires package review. |

## Open findings

No contract-level P0 or P1 finding remains at this revision. The
implementation must still prove every required race, lock, status, privacy,
replay, CLI and regression case at its exact head. This review is not evidence
that W-08C implementation is shipped.

## Verdict

**SHIP**

The W-08C contract is bounded, technically consistent with the current
authority and lock surfaces, and ready for a separately reviewed
implementation. W-08C implementation remains `REVIEW PENDING` until its exact
head evidence and independent implementation review pass. W-08D remains
deferred.
