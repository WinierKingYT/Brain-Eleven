# W-02 Package Report — Capture Queue Claim Crash Safety

**PACKAGE:** W-02 / capture queue claim crash safety  
**REVISION:** pending commit  
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

No public status, retry/dead-letter limit, ledger privacy, worker extraction,
canonical store, V2 or Phase 20 behavior changed.

## Tests executed

- Focused queue + IG-02 capture suite: **41 passed**.
- Full suite: **953 passed, 2 warnings**.
- Critical flake8 (`E9,F63,F7,F82`): **PASS**.
- `compileall`: **PASS**.
- `git diff --check`: **PASS**.

New fault-injection tests cover both a failure before rename and a failure
after rename, then prove the same job is recoverable and re-claimable without
identity loss.

## Safety metrics

- Jobs stranded by claim rename/write ordering: **0 in fault-injection tests**.
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

**QUALITY METRICS BEFORE:** Queue claim crash window was untested; full suite
was 951 passed after W-01.  
**QUALITY METRICS AFTER:** Fault-injection coverage added; full suite is 953
passed.  
**SCORE BEFORE/AFTER:** Capture runtime 7.5 → 8.0 (provisional; transcript
boundary and late-event loss remain open).  
**OPEN FAILURES:** None known in W-02; independent review pending.  
**VERDICT:** REVIEW PENDING
