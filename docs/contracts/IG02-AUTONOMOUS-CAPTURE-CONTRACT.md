# IG-02 Autonomous Capture Closure Contract

**PACKAGE:** IG-02  
**STATUS:** CURRENT CONTRACT / IMPLEMENTATION COMPLETE / ACCEPTANCE PENDING
**BOUNDARY:** Claude/Codex hook delivery through queue, worker, evidence and
canonical-effect verification

## Objective

Prove that an opted-in Claude or Codex SessionEnd event can travel through the
bounded local pipeline without losing the event, duplicating a canonical effect,
or acknowledging a job before its durable effect has been verified.

## Allowed scope

This package may change the capture queue, native hook adapter, worker,
evidence reader, content-free receipts, runtime observability and focused tests.
It may not promote V2, change retrieval ranking, add a semantic provider, alter
Phase 20, create a second canonical store or bypass MemoryStore/StateStore
authority.

## Required flow

```text
native hook
  -> content-safe CaptureEvent
  -> durable at-least-once queue
  -> leased worker
  -> incremental EvidenceReader
  -> deterministic extraction / review boundary
  -> MemoryStore or StateStore effect (or durable review effect)
  -> content-free effect receipt
  -> queue terminal state
```

## Invariants

1. Hook fast paths never read transcript content or invoke extraction.
2. Queue jobs are idempotent by event identity and replay-safe.
3. A `COMMITTED` queue job must have a matching schema-versioned
   `EFFECT_VERIFIED` receipt whose job, event, project and checkpoint identities
   match.
4. Canonical writes remain behind MemoryStore/StateStore transaction receipts.
5. Review effects are durable and content-safe; a failed review write keeps the
   queue retryable.
6. Worker failures expose bounded machine codes, retry at most the configured
   attempts, recover expired leases and dead-letter terminal failures.
7. Receipts contain identifiers, counts, hashes or statuses only; no prompt,
   transcript, token or memory content.
8. Replaying a job after a crash before queue acknowledgement never creates a
   second canonical memory or state record; a receipt is accepted only when its
   canonical operation receipts and surviving effects are still present.
9. Cursor progress is persisted only after the effect receipt is durable. A
   receipt write failure therefore replays from the prior cursor rather than
   silently acknowledging an empty tail.
10. Unknown, corrupt, deleted or rewritten evidence fails visibly and never
   produces a successful queue acknowledgement.
11. Project and client scope remain fail-closed.

## Acceptance tests

The package must include focused evidence for duplicate delivery, worker crash
before/after canonical write and before queue acknowledgement, lock timeout,
corrupt/deleted/rewritten transcript, invalid project, queue corruption, expired
lease, MemoryStore CAS conflict and StateStore conflict. A native-style Claude
and Codex golden path must verify queue delivery, effect receipt and canonical
verification without exposing content.

## Exit gate

IG-02 is `SHIP` only when local and exact-head cross-platform CI pass, queue
completion is receipt-verified, replay/crash tests pass, dead-letter and lease
recovery are observable, the golden E2E succeeds, and independent read-only
review returns `SHIP`. IG-03 remains closed; IG-04 cannot start until this gate
is accepted. Phase 20 remains `FROZEN / LOCKED` and V2 remains `SHADOW`.
