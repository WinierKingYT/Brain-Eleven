# W-02 Contract — Capture Queue Claim Crash Safety

**Status:** BOUNDED CONTRACT / IMPLEMENTATION AUTHORIZED BY ENGINEERING GOAL  
**Priority:** P1 capture reliability  
**Target:** `scripts/capture_queue.py` claim/retry/recovery transitions  
**Phase 20:** FROZEN / LOCKED

## Problem

`claim_next()` currently renames a queued job into `processing` and only then
rewrites its document as `CLAIMED`. A process crash between those operations
can leave a `QUEUED` document in the processing directory. Lease recovery
rejects that state and the capture can remain stranded forever.

## Scope

Make the claim transition recoverable without changing the queue's public
statuses, retry budget, idempotency key, ledger privacy, or worker ownership.
The preferred bounded sequence is to durably persist the updated `CLAIMED`
document in the queued location before moving it to processing; an interrupted
move then remains visible to the existing queued-state recovery path. If a
compatibility repair for an already-stranded processing document is needed, it
must be explicit, deterministic and tested.

The same failure-injection matrix must cover claim, retry and lease-recovery
rename/rewrite transitions so no transition silently loses a job. Existing
retry/dead-letter limits and the single queue lock remain unchanged.

## Out of scope

No transcript provenance policy, worker extraction behavior, prompt-event
semantics, queue retention, canonical MemoryStore/StateStore changes, V2,
Phase 20 or unrelated queue refactor.

## Acceptance evidence

- a failure immediately before/after claim rename leaves a recoverable job;
- the next claim/recovery processes the same idempotency key exactly once;
- retry and lease recovery remain bounded and preserve existing statuses;
- no job is silently lost or duplicated and the content-free ledger remains;
- existing queue and IG-02 worker tests pass unchanged;
- new fault-injection tests prove the crash window and recovery behavior;
- critical flake8 (`E9,F63,F7,F82`), compileall and `git diff --check` pass;
- full suite is green, apart from no unrelated pre-existing failure;
- independent read-only review returns only `SHIP`, `FIX-FIRST` or `RETHINK`.

## Package report fields

`PACKAGE`, `REVISION`, `OBJECTIVE`, `FILES CHANGED`, `ROOT CAUSES ADDRESSED`,
`TESTS ADDED`, `TESTS EXECUTED`, `QUALITY METRICS BEFORE/AFTER`, `SAFETY
METRICS`, `KNOWN LIMITATIONS`, `OPEN FAILURES`, `INDEPENDENT REVIEW`, `SCORE
BEFORE/AFTER`, `VERDICT`.
