# W-02 Successor Contract — Capture Queue Terminal-State Closure

**Status:** BOUNDED CONTRACT / INDEPENDENT REVIEW PENDING  
**Priority:** P1 capture reliability  
**Target:** `scripts/capture_queue.py` commit/recovery terminal transition  
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW

## Evidence-backed problem

The earlier W-02 claim transition is already independently shipped. A
separate crash window remains in `CaptureQueue.commit()`:

1. the processing document is renamed into `capture/completed/`;
2. its `status` is then rewritten from `PROCESSING`/`CLAIMED` to `COMMITTED`.

If the process exits after the rename and before the rewrite, the completed
folder contains a non-terminal document. `recover_expired_claims()` scans only
the claimed/processing folder, so the job is not reclaimed or repaired. A
later worker returns idle, while duplicate enqueue is classified from the
folder name and can report `COMMITTED` even though the document itself is
still `PROCESSING`. This is a durable terminal-state inconsistency, not a
canonical-memory duplication proof; it must be repaired without replaying the
effect.

## Objective

Make the queue's commit transition crash-safe and make every completed-folder
document terminal, observable and idempotent. Preserve the existing public
statuses, idempotency identity, single queue lock, content-free ledger and
worker-side canonical effect ordering.

## Bounded scope

Only the queue commit/recovery surface and its focused tests may change:

- `scripts/capture_queue.py::CaptureQueue.commit()`;
- the existing recovery/lookup path needed to reconcile a completed-folder
  document whose status is `CLAIMED` or `PROCESSING`;
- queue and IG-02 worker fault-injection tests and package evidence.

The preferred transition is:

1. while the queue lock is held, validate the claimed/processing source;
2. set `status=COMMITTED` and `committed_at`, and durably atomically rewrite
   the source document in its current folder;
3. rename that already-terminal document to `completed/`;
4. append the existing content-free terminal ledger entry.

Recovery must also repair an interrupted transition deterministically:

- a valid `COMMITTED` document stranded in the claimed/processing folder is
  moved to `completed/`;
- a valid completed-folder document with the pre-commit status
  (`CLAIMED`/`PROCESSING`) is explicitly reconciled to `COMMITTED`, durably
  and under the queue lock, without invoking the worker or canonical stores;
- malformed or identity-inconsistent documents remain visible as corruption
  and are never silently promoted.

The implementation may choose equivalent ordering if it proves the same
durability and recovery invariants. It must not replay evidence extraction or
canonical writes during queue repair.

## Required invariants

- A job in `completed/` is always `COMMITTED` after recovery; no silent
  `PROCESSING` terminal document remains.
- A crash before or during rename leaves a document discoverable by the next
  recovery/worker run.
- A crash after the worker's canonical effect and before queue finalization
  never causes a second canonical effect on retry or repair.
- Duplicate enqueue returns the actual durable terminal state and preserves
  the original idempotency key.
- Queue status/location pairs remain valid for `queued`, `claimed`,
  `processing`, `completed` and `dead-letter`.
- Existing retry limits, lease semantics, lock boundaries, ledger privacy,
  receipt identity and content-retention policy remain unchanged.
- Queue repair is idempotent: running it repeatedly produces no additional
  move, canonical effect or misleading ledger event.
- No queue code writes `MemoryStore`, `StateStore` or any other canonical
  authority; worker ordering remains the sole effect boundary.

## Required evidence and tests

Focused tests must include all of the following, in addition to the existing
queue and IG-02 suites (which remain unchanged):

- commit crash before the pre-rename durable rewrite;
- commit crash after the terminal rewrite but before rename;
- commit crash after rename and before any post-rename bookkeeping;
- recovery of stranded `COMMITTED` documents and completed-folder
  `CLAIMED`/`PROCESSING` documents;
- worker post-rename crash followed by a later worker run, proving one
  canonical effect and one terminal receipt;
- duplicate enqueue reports the reconciled terminal state;
- completed status/location invariant and content-free terminal ledger;
- malformed/identity-mismatched completed documents fail visibly and do not
  mutate canonical stores;
- repeated recovery is idempotent.

Acceptance also requires:

- existing `tests/test_capture_queue.py` and
  `tests/test_ig02_capture_closure.py` pass without modification;
- focused W-02 successor tests pass;
- full `pytest tests -q` is green except for documented unrelated failures;
- critical flake8 (`E9,F63,F7,F82`), `compileall` and `git diff --check` pass;
- a package report records exact revision, before/after metrics, failure
  injection evidence and known limitations;
- an independent read-only reviewer returns exactly `SHIP`, `FIX-FIRST` or
  `RETHINK`.

## Explicitly out of scope

No transcript ownership/provenance policy (W-03B), late locator policy
(W-04), prompt-event semantics (W-05), extraction, review approval,
maintenance/reminder delivery, canonical MemoryStore/StateStore changes,
queue retention redesign, V2 promotion, Phase 20 work or unrelated refactor.

## Exit gate

This package remains `FIX-FIRST / NOT ACCEPTED` until the exact-head focused
and full evidence is recorded and the independent review returns `SHIP`.
Implementation must not be treated as complete merely because the queue test
suite is green.

