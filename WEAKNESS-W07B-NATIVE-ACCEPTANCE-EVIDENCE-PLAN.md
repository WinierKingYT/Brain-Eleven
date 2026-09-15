# W-07B Native Acceptance Evidence Plan

**Status:** APPROVED EVIDENCE PLAN / EXECUTION NOT STARTED

**Program:** Engineering Weak-Point Improvement Goal

**Evidence baseline head:** `9f8ecc2` (current repository HEAD when this
plan was written). The W-07B implementation ancestor is `f322d2c`; the
evidence harness must pin the complete current dependency graph to the exact
baseline head, not mix files from a moving working tree.

**Phase 20:** `FROZEN / LOCKED` — **V2:** `SHADOW`

## Purpose

Close only the evidence gaps that kept the already implemented W-07B native
maintenance package at `FIX-FIRST / NOT ACCEPTED`. This plan changes no
production code, no hook configuration and no canonical data. It does not
promote W-07B, V2 or Phase 20 until the evidence and a separate review pass.

## Current evidence and remaining gaps

The existing package report and independent review prove the queue/worker
intent protocol, report privacy and revision freshness through focused tests.
`IG-02-NATIVE-SMOKE-EVIDENCE.md` proves that the real Claude and Codex hook
definitions were loaded and invoked from an isolated configuration, but both
executables stopped before producing a client-owned transcript: Claude lacked
API authentication and Codex lacked network authentication. Therefore these
claims remain open:

1. authenticated Claude and Codex executable → hook → queue → terminal receipt
   → canonical-effect verification;
2. worker/service process restart and kill recovery around each durable
   intent phase;
3. native hook latency samples (p50/p95) against the existing three-second
   client timeout and SessionStart budget;
4. repeated, content-free dogfood across multiple sessions and projects.

## Evidence harness

### Isolated native smoke

- Create a temporary vault and separate Claude/Codex configuration directory;
  never point a test at the live vault or live client config.
- Install the existing hook definitions only into that temporary config.
- Invoke each installed executable with a minimal test session under the
  explicit isolated environment. Use the real executable, not a launcher
  fixture, and keep stdout/stderr capture content-free.
- Record only `client`, `event`, exit code, hashed session identity, queue
  event ID, terminal state, canonical verification, config mutation count and
  trust verdict. Do not persist prompts, transcripts, tokens, paths or raw
  exceptions.
- Verify the queue receipt reaches a terminal state and then verify the
  expected canonical effect by opaque ID/revision only. A `COMPLETED` queue
  row without canonical verification is insufficient.
- Delete the temporary vault/config after evidence capture and confirm the
  live config and live vault bytes are unchanged.

Both clients must complete authenticated capture for native trust to be
`VERIFIED`. If either client cannot complete it, record
`BOUNDED_UNVERIFIED_*` with the exact failure code and leave W-07B
`FIX-FIRST / NOT ACCEPTED`; an environment exception is not a substitute for
native trust and cannot produce a `SHIP` verdict. If the runtime dependency
graph changes before evidence execution, create a new exact baseline and
repeat all measurements.

### Restart/kill matrix

Use the existing worker and service entry points and an isolated vault. The
harness must use a test-only deterministic barrier/seam that emits a named
boundary signal before the parent terminates the child; wall-clock sleeps are
not accepted as proof. Exercise worker and service processes separately. For
each phase below, terminate the signalled process, restart it and record only
receipt/status/revision metadata:

| Boundary | Required result |
| --- | --- |
| worker after intent write | intent remains retryable; one eventual report |
| worker after claim/lease | live lease fences duplicate worker; expiry permits recovery |
| worker after maintenance staging | retry is bounded; no canonical mutation |
| worker after atomic report publication | receipt reconciliation prevents duplicate work |
| service after final intent receipt | restart is a no-op for that intent |

The harness must run at least three repetitions per boundary and assert one
report/receipt per intent, unchanged canonical revisions on failure, no stale
worker publication and no temporary report residue.

### Latency

Collect at least five cold and five warm samples for every cell in this
matrix on the isolated vault:

`Claude/Codex × SessionStart/UserPromptSubmit/Stop/SessionEnd × cold/warm`.

Report p50 (median) and p95 (nearest-rank percentile) for each cell, using
only elapsed milliseconds and status codes. The existing hook timeout and
bounded startup budget are fixed contracts; evidence may expose a failure but
may not loosen them.

### Dogfood

Run at least five sessions and twenty turns across two or more explicitly
registered projects, including one project switch, one SessionEnd/next-
SessionStart handoff and one failed/retried maintenance intent. Store only
sanitized event/status/revision metadata and opaque IDs/hashes. Add any real
failure to the existing taxonomy (`CAPTURE_MISS`, `STALE_CONTEXT`,
`TOKEN_WASTE`, etc.) without retaining raw user content.

## Acceptance gates

W-07B may move from `FIX-FIRST / NOT ACCEPTED` only if all are true:

- both real executable paths are `VERIFIED`; unavailable authentication or an
  environment exception leaves W-07B `FIX-FIRST / NOT ACCEPTED` and cannot
  satisfy the native-trust gate;
- restart/kill matrix passes with one durable report per intent;
- p50/p95 latency evidence is present and within the existing timeout/budget;
- dogfood sample is complete, privacy-safe and has no unexplained P0/P1
  failure;
- canonical MemoryStore/StateStore/ProjectRegistry bytes and revisions are
  unchanged by maintenance failures;
- evidence is bound to exact implementation and harness revisions;
- a separate read-only reviewer returns exactly `SHIP`, `FIX-FIRST` or
  `RETHINK`.

Until then, W-07B remains open, automatic Markdown continuity writes remain
out of scope, and Phase 20/V2 state is unchanged.

## Canonical-effect and verification binding

The native smoke must use a controlled deterministic capture input whose
expected terminal result is known. A successful run must verify the canonical
effect by opaque ID and revision. Where a real client cannot produce a valid
capture locator, the only accepted alternative is an explicit terminal
`zero_effect` receipt with an unchanged canonical revision; a generic queue
`COMPLETED` row is insufficient. Every result records the exact baseline
revision, harness revision, client version and workflow/local command used.

Run the focused W-07B/native suites and full regression locally against the
pinned exact head. If the repository's remote workflow exposes a matching
runtime job, record workflow name, run ID, head SHA and conclusion. If it does
not exercise the native/restart/latency harness, record `NOT APPLICABLE` and
keep those gates dependent on the bounded local evidence rather than treating
an unrelated green workflow as proof.

## Package report fields

The eventual evidence report must include `PACKAGE`, `REVISION`, `OBJECTIVE`,
`FILES CHANGED`, `ROOT CAUSES ADDRESSED`, `TESTS ADDED`, `TESTS EXECUTED`,
`QUALITY METRICS BEFORE/AFTER`, `SAFETY METRICS`, `KNOWN LIMITATIONS`,
`OPEN FAILURES`, `INDEPENDENT REVIEW`, `SCORE BEFORE/AFTER` and `VERDICT`.

**Plan status: APPROVED — independent plan review returned `SHIP`; production
implementation başlamadı.**
