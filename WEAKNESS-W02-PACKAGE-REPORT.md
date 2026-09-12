# W-02 Package Report — Capture Queue Claim Crash Safety

**PACKAGE:** W-02 / capture queue claim crash safety  
**REVISION:** 46f2ff86878d0d176d2b717dc2cb8d2ec9b6798e
**OBJECTIVE:** Eliminate the crash window that could leave a `QUEUED`
document stranded in the `processing` directory.  
**FILES CHANGED:** `scripts/capture_queue.py`, `tests/test_capture_queue.py`  
**ROOT CAUSES ADDRESSED:** Claim state was persisted only after the queue-file
rename, so a process exit between the two filesystem operations produced an
unrecoverable location/state combination.

## Implementation

`claim_next()` now durably writes the incremented attempt, `CLAIMED` status and
claim timestamp while the document is still in `queued`, then moves that
document to `processing`. If the move fails before completion, the existing
queued-state path can retry the same idempotency key. If the process exits
after the move, the processing document is already a valid `CLAIMED` job and
lease recovery handles it normally.

The same write-before-rename ordering is used for retry requeue, retry
dead-letter, and lease recovery requeue/dead-letter transitions. Recovery also
repairs a processing-directory document whose durable status is already
`QUEUED` or `DEAD_LETTER`, covering a crash between the state write and rename.

No public status, retry/dead-letter limit, ledger privacy, worker extraction,
canonical store, V2 or Phase 20 behavior changed.

## Tests executed

- Focused queue + IG-02 capture suite: **49 passed**.
- Full suite: **961 passed, 2 warnings**.
- Critical flake8 (`E9,F63,F7,F82`): **PASS**.
- `compileall`: **PASS**.
- `git diff --check`: **PASS**.

Fault-injection tests cover failures before and after rename for claim,
retry-requeue, retry-dead-letter, and lease-recovery transitions. They prove
that the same job is recoverable and re-claimable without identity loss, and
that dead-letter terminal state is preserved.

## Safety metrics

- Jobs stranded by claim/retry/recovery rename/write ordering: **0 in
  fault-injection tests**.
- Duplicate job identity: **0**.
- Existing retry/lease behavior regressions: **0**.
- New canonical write paths: **0**.

## Known limitations

This package does not address missing/late transcript enqueueing, prompt-event
dead-letter semantics, transcript provenance, retention or worker extraction.
Those remain separate W-03/W-04/W-05 packages.

## Independent review

Independent read-only review is required before this package is considered
closed. The verdict must be `SHIP`, `FIX-FIRST` or `RETHINK`; self-review is not
accepted.

## Quality and verdict

**QUALITY METRICS BEFORE:** Queue claim, retry, and lease recovery had
  rename/write crash windows; full suite was 953 passed after the initial W-02
  implementation.
**QUALITY METRICS AFTER:** All three transition families have pre/post-rename
  fault-injection coverage; full suite is 961 passed.
**SCORE BEFORE/AFTER:** Capture runtime 7.5 → 8.0 (provisional; transcript
boundary and late-event loss remain open).  
**OPEN FAILURES:** None known in W-02; independent review of revision-bound
  evidence is pending.
**VERDICT:** REVIEW PENDING
