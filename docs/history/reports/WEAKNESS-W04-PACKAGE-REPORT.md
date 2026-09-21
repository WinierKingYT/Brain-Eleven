# W-04 Package Report — Late Transcript Durability

**PACKAGE:** W-04 / late transcript queue durability
**REVISION:** 64e2591
**OBJECTIVE:** Keep a trusted SessionEnd locator durable when the transcript
file is not visible yet, so the existing retry/dead-letter policy can handle
the race.

## Files changed

- `scripts/capture_provenance.py` — explicit enqueue-only `allow_missing`
  resolution mode.
- `brain_eleven/runtime/worker.py` — queue a root-confined pending locator;
  retain strict resolution before evidence read.
- `tests/test_capture_provenance.py` — duplicate pending delivery, late-file
  arrival and replay-effect coverage.
- `tests/test_ig02_capture_closure.py` — explicit early-loss expectation and
  missing-locator degraded case.

## Root cause addressed

`worker.enqueue` called `stat()` before queue creation. A normal SessionEnd
write race returned `TRANSCRIPT_NOT_FOUND` with no durable job, so no retry or
dead-letter evidence existed. The queue now retains a safe, root-confined
locator even when the file is temporarily absent.

## Behavior and safety

- Enqueue uses the W-03A resolver with `allow_missing=True`; it never guesses a
  locator and never bypasses client-root confinement.
- A missing file gets a stable pending idempotency marker, so duplicate hook
  delivery remains one queue job.
- Worker processing keeps strict resolution and maps an absent source to the
  existing `TRANSCRIPT_NOT_FOUND` retry code.
- A file appearing before terminal retry is processed by the same job and
  receipt/effect verification remains unchanged.
- A SessionEnd with no locator remains degraded without queue side effects.

## Tests executed

- W-04 + affected capture/runtime suite: **101 passed, 2 warnings**.
- Full suite: **971 passed, 2 warnings**.
- Critical flake8 (`E9,F63,F7,F82`): **PASS**.
- `compileall`: **PASS**.
- `git diff --check`: **PASS**.

## Quality metrics

**BEFORE:** Known locator absent at SessionEnd was dropped before durable
queueing; full suite baseline was 969 passed after W-03A.
**AFTER:** Known late locators survive enqueue, retry and late-file arrival;
missing locators remain explicit degraded results.
**Capture score:** 8.0 → 8.5 provisional.

## Known limitations / deferred work

This package does not infer a missing locator, alter retry limits, solve
project/session ownership, detect same-size source replacement, or address
prompt-event semantics (W-05). W-03A and W-04 must not be described as full
transcript provenance or autonomous late-source discovery.

## Independent review

Required and pending. The reviewer must inspect exact revision, contract,
queue identity, retry/dead-letter behavior, regression evidence and deferred
boundaries, then return exactly `SHIP`, `FIX-FIRST` or `RETHINK`.

**VERDICT:** REVIEW PENDING
