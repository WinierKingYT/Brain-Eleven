# W-08A Independent Read-Only Review

**PACKAGE:** W-08A — ProjectRegistry durability and CAS parity
**AUDITED HEAD:** `05fd7f6532b50af038f44b5422083eee721747b8`
**IMPLEMENTATION:** `7fc2860c373a8b39dbc42be58763dd8af2ac3254`
**FOCUSED TESTS:** `05fd7f6` (integrity evidence), `a2b065d` (initial W-08A tests)
**REVIEW TYPE:** Independent read-only package re-review
**PHASE 20:** FROZEN / LOCKED
**V2:** SHADOW

## Review boundary

This review inspected the frozen W-08 contract, the exact W-08A diff, the
package report, callers, tests and the deferred W-08B/W-08C/W-08D boundaries.
No production file or existing untracked evidence artifact was modified.

## Evidence independently reproduced

- W-08A focused tests: **10 passed**.
- Related registry, scope, package-boundary, caller, backup, capture and
  remember surfaces: **99 passed**.
- Baseline snapshot guard: **5 passed**.
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

## Prior FIX-FIRST finding and closure

The first independent review required explicit backup/rollback comparison of
the prior `project_id`, label, root, `status` and `proactive_capture` values.
Commit `05fd7f6` adds that complete projection before rollback and compares it
with the restored projection afterward. It also preserves the envelope
revision assertions and repeated-rollback check. The change is test-only and
does not alter production behavior or package scope.

## Score and open state

- Persistence/concurrency: **7.0 → 7.5 provisional**. Registry-local
  durability, revision/CAS and rollback evidence now pass; coordinated backup,
  state-reference TOCTOU and typed API lifecycle remain open W-08 packages.
- No other score is changed by this review.
- Open P0: **0**.
- Open W-08A package blocker: **0**.

## Verdict

**SHIP**

The bounded W-08A contract is satisfied at exact HEAD `05fd7f6`. The broader
W-08 persistence weakness remains open through the separately bounded W-08B,
W-08C and W-08D packages.
