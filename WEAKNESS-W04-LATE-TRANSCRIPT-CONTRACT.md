# W-04 — Late Transcript Durability Contract

**Status:** BOUNDED CONTRACT / IMPLEMENTATION PENDING  
**Program:** Engineering Weak-Point Improvement Goal  
**Phase 20:** FROZEN / LOCKED  
**V2:** SHADOW

## Objective

Do not lose a SessionEnd event merely because the native client has supplied a
valid transcript locator before the transcript file is visible. The event
must enter the durable queue and remain retryable until the existing bounded
retry/dead-letter policy decides its terminal state.

## Current failure

`brain_eleven/runtime/worker.py:111-120` currently stats the locator before
building the event. A normal client write race therefore returns
`TRANSCRIPT_NOT_FOUND` before `CaptureQueue.enqueue`, leaving no durable job,
ledger record or retry opportunity.

## Bounded implementation

1. Extend the W-03A resolver with an explicit `allow_missing` mode used only
   by enqueue. It still requires an absolute locator, trusted client root,
   traversal/symlink/containment safety, and a valid parent/root; it may return
   a canonical path that does not exist yet.
2. `worker.enqueue` uses that mode and creates the normal `SESSION_END` event
   and queue job without calling `stat` first. The idempotency key includes a
   stable pending marker when the file is absent, so duplicate hook delivery
   still maps to one job.
3. `Worker.process` keeps strict W-03A resolution. A missing file raises the
   existing content-free `TRANSCRIPT_NOT_FOUND` processing error, which uses
   the existing retry/dead-letter and lease machinery. No new canonical write,
   queue status or retry policy is introduced.
4. If the transcript becomes readable before terminal retry, the same job is
   processed and receipt/effect verification proceeds normally. If it never
   appears, the visible dead-letter result remains bounded and explainable.
5. A missing locator is not guessed. SessionEnd without a locator remains an
   explicit degraded result because no safe future source identity exists.

## Invariants

- Root confinement and client boundary from W-03A remain mandatory.
- One event/job identity survives enqueue retry and late-file arrival.
- No queue completion or canonical effect occurs before evidence is read and
  verified.
- No raw transcript content is placed in queue, ledger, receipt or evidence
  metadata.
- Existing max-attempt, lease, replay and dead-letter semantics are unchanged.
- Phase 20, V2, extraction, retrieval, project/session ownership and stable
  replacement identity remain outside this package.

## Acceptance criteria

- A trusted-root path whose file is absent at enqueue returns a queued receipt
  and creates exactly one durable job.
- The file appearing before retry allows the same job to process successfully.
- A never-appearing file reaches visible dead-letter after the existing bound.
- Duplicate enqueue while pending remains idempotent.
- Missing locator remains degraded with no queue side effect.
- Existing capture queue/worker/evidence suites pass unchanged except for the
  explicitly updated early-loss expectation.
- Focused fault/race tests, full regression, critical flake8, compile/import
  sanity and `git diff --check` pass.
- Independent read-only review returns exactly `SHIP`, `FIX-FIRST` or
  `RETHINK`.

**Package verdict:** REVIEW PENDING until implementation and independent review.
