# W-08A Independent Read-Only Review

**PACKAGE:** W-08A — ProjectRegistry durability and CAS parity  
**AUDITED HEAD:** `c8c39aadd38b4676b24c0082abf72e12ef841a12`  
**IMPLEMENTATION:** `7fc2860c373a8b39dbc42be58763dd8af2ac3254`  
**FOCUSED TESTS:** `a2b065d`  
**REVIEW TYPE:** Independent read-only package review  
**PHASE 20:** FROZEN / LOCKED  
**V2:** SHADOW

## Review boundary

This review inspected the frozen W-08 contract, the exact W-08A diff, the
package report, callers, tests and the deferred W-08B/W-08C/W-08D boundaries.
No production file or existing untracked evidence artifact was modified.

## Evidence independently reproduced

- W-08A focused tests plus registry, scope, package-boundary, caller, backup,
  capture and remember surfaces: **52 passed**.
- Full `pytest tests -q`: a first run had one transient cold SessionStart
  failure outside the W-08A diff; the same test passed alone immediately and a
  second complete run passed **992 tests, 2 warnings**. The warnings are the
  existing FastAPI/Starlette dependency deprecations.
- Critical flake8 (`E9,F63,F7,F82`) on changed Python files: **PASS**.
- `compileall` on changed Python files: **PASS**.
- `git diff --check`: **PASS**.
- Independent temporary-vault checks confirmed monotonic revision increments
  for register, rename, status, proactive-capture and relocate, plus legacy
  opt-in migration revision behavior.
- Baseline diff from the W-08 contract revision changes only
  `source_fingerprint`; corpus, task cases, metrics and invariants remain
  unchanged.

## Contract checks

The implementation correctly preserves the existing registry authority and
lock boundary. Schema version remains `1`; missing legacy revisions normalize
to `0`, and successful mutations persist a monotonic additive revision. The
optional `expected_revision` comparison happens after the latest load while
holding `file_lock`; stale writes raise the typed `ProjectRegistryConflict`
without changing canonical bytes. Callers that omit the argument retain the
documented compatibility behavior.

The atomic path flushes and fsyncs the temporary file, replaces the canonical
path and syncs the parent directory where supported. Existing registries are
backed up first in the fixed validated envelope. Backup, JSON, fsync and main
persistence failures remain visible as typed errors. Rollback validates the
backup envelope, rejects a stale expected revision, never decreases the
revision and explicitly returns `already_restored` on a repeated restore.

Package, legacy and bare-module class/error identity is preserved. Existing
callers continue using the same object and no MemoryStore, StateStore, graph,
capture or new authority write path was introduced. W-08B coordinated backup,
W-08C state-reference TOCTOU and W-08D typed API lifecycle remain deferred.

## FIX-FIRST finding

The W-08A contract's required backup evidence says the restored prior registry
must preserve **identity, status and proactive-capture data**. The implementation
uses a validated deep copy and therefore appears to preserve these fields, but
the focused test only asserts the prior label and project lookup after rollback;
it does not explicitly seed and compare the prior `status` and
`proactive_capture` values before and after rollback. The package report's
backup claim is therefore not fully evidence-backed at the required field
level.

Add a focused test that records the complete prior project identity/status/
opt-in projection, performs a mutation and rollback, and compares that
projection exactly. Keep the test-only change bounded; no production behavior
change is authorized by this finding. Re-run the focused and full suites and
request a fresh independent review afterward.

## Score and open state

- Persistence/concurrency baseline: **7.0/10**.
- W-08A sub-surface evidence: implementation behavior is materially improved,
  but the package score remains **pending** until the missing integrity evidence
  is closed.
- No other score is changed by this review.
- Open P0: **0**.
- Open W-08A review blocker: **1 focused evidence gap** described above.

## Verdict

**FIX-FIRST**

