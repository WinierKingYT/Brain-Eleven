# W-15 Runtime Configuration Lost-Update Contract

**Status:** REVIEW PENDING — implementation is not authorized by this document  
**Finding:** `RuntimeConfig.set_mode()` and `set_human_approval()` load a full
configuration, modify one field, and atomically replace the file without a
shared lock or revision guard.  Concurrent operator changes can therefore be
silently lost.  
**Priority:** P1 runtime safety / rollout control  
**Contract revision:** `a1b753e` (W-14 close baseline)

## Evidence

`brain_eleven/runtime/storage.py::RuntimeConfig.set_mode()` (currently lines
69–88) and `set_human_approval()` (lines 90–97) both call `load()`, mutate a
copy of the complete JSON object, and call `write_json(self.path, value)`.
`write_json()` is atomic for a single writer (temporary file, flush, fsync,
replace), but there is no lock or compare-and-swap between the read and the
replace.

A read-only fault-injected probe used two `RuntimeConfig` instances in an
isolated temporary vault.  In the first run, `set_human_approval(True)` was
paused immediately after its stale load; a second instance committed
`set_mode("SHADOW")`; releasing the first writer left the file with
`mode="OFF"` and `b1_human_approval=true`.  In the reverse run, a paused
`set_mode("SHADOW")` overwrote a later approval update and left
`b1_human_approval=false`.  Both calls returned successfully and no conflict
was reported.  The existing atomic write therefore prevents torn JSON but not
lost operator intent.

## Bounded objective

Make each runtime-config mutation linearizable with respect to other config
mutations while preserving the schema, CLI behavior, rollout gates, and
atomic-file durability.  A delayed writer must never silently overwrite a
newer operator update.  The installer’s config update is included because it
currently writes `config.json` directly and otherwise bypasses the same
boundary.

The preferred design is an optimistic compare-and-swap using the existing
sidecar lock primitive:

1. Read and validate a canonical snapshot (including a deterministic
   fingerprint of the loaded config).
2. Perform expensive CANARY holdout or ACTIVE graduation validation outside
   the commit lock.
3. Acquire the config sidecar lock, reload and validate the current config,
   and compare its fingerprint with the snapshot.  If it changed, raise a
   typed `RuntimeConfigConflict` (a `ValueError` subclass so the existing CLI
   failure contract remains intact) and do not write.
4. Apply only the requested field to the freshly reloaded value and call the
   existing atomic `write_json()` while the lock is held.

The implementation may use a private fingerprint helper; adding a persisted
revision field or changing the schema is not allowed unless a later bounded
contract explicitly authorizes it.  The lock must be the existing
`brain_eleven.infrastructure.locking.file_lock` surface on a sidecar next to
`config.json`.

## Allowed scope

- `brain_eleven/runtime/storage.py`: `RuntimeConfig` mutation helpers, a
  private fingerprint/commit helper, and the typed conflict exception.
- `brain_eleven/runtime/install.py`: only the existing config update that adds
  the canary project and changes `OFF` to `SHADOW` may call the shared config
  mutation primitive.  Hook merge, client-file locking, manifest journaling,
  and project/state setup remain unchanged.
- Focused W-15 tests and evidence/package documents.
- A small package export only if required for stable exception identity.

`read_json()`, `write_json()` atomic persistence, runtime schema, rollout
quality gates, `MemoryStore`, `StateStore`, `ProjectRegistry`, worker/service
behavior, retrieval, V2, Phase 20, hook/client configuration, manifest
journaling, and unrelated runtime files are out of scope.

## Required semantics

1. **No lost update:** delayed mode and approval writers either commit against
   an unchanged snapshot or fail with `RuntimeConfigConflict`; neither may
   erase a later field update.
2. **Mode safety:** a delayed CANARY/ACTIVE operation cannot overwrite a later
   operator `OFF`, `SHADOW`, or approval change.  Expensive validation may run
   before the lock, but the final snapshot check is mandatory.
3. **Field preservation:** successful `set_mode()` preserves unrelated current
   keys (including `b1_human_approval`, project scope, retrieval metadata and
   local model); successful `set_human_approval()` preserves mode and all
   other keys.  Installer updates preserve concurrent operator changes while
   adding its project ID and requested `SHADOW` transition.
4. **Schema/parity:** defaults, validation, invalid retrieval telemetry,
   CANARY holdout evidence, ACTIVE graduation checks, returned JSON shape and
   CLI exit/error behavior remain compatible.
5. **Atomic durability:** the existing temp-file, flush, fsync and replace
   sequence remains the only config write path.  No direct `open().write()` or
   second config authority may be added.
6. **Lock failure:** existing lock timeout/error behavior stays visible and
   fail-closed; a failed acquisition produces no config mutation.
7. **Same-field contention:** two concurrent writes to the same field cannot
   both report success against one snapshot; one must conflict (or both may
   serialize only when the second observes the first's fresh value).
8. **Mode boundary:** this package does not promote V2 or unlock Phase 20;
   current `SHADOW` behavior is preserved.

## Test and evidence plan

### Baseline and reproduction

- Record exact `git rev-parse HEAD`.
- Re-run the two event-controlled lost-update probes above and retain the
  pre-fix result as a visible red baseline.
- Capture current config schema/CLI behavior on an isolated temporary vault.

### Focused tests

Add tests without changing existing runtime/B1 coverage:

- delayed approval writer versus mode writer: no field is lost;
- delayed mode writer versus approval writer: no field is lost;
- delayed CANARY/ACTIVE final commit versus an intervening `OFF`: conflict and
  final `OFF` remain visible (expensive validation is stubbed, not skipped);
- same-field contention reports a typed conflict and leaves the winner intact;
- installer config update versus approval/mode writer: no field is lost and
  the installer’s project ID addition remains present;
- lock timeout maps to the documented failure and causes no write;
- successful updates preserve unrelated config keys and return the same shape;
- atomic JSON remains parseable, and no temporary artifact is left behind;
- existing `test_ig00_bootstrap.py`, `test_ig04_b1_human_approval.py`,
  `test_pre13_runtime.py`, `test_w06b_task_aware.py`, `test_ig02_capture_closure.py`
  `test_w10_v2_delivery_gate.py` and installer/runtime tests pass unchanged.

### Verification gates

1. **Boundary proof:** AST/source review shows both mutation paths use the
   existing config sidecar lock and atomic `write_json`; no second authority or
   direct file-write path exists.
2. **Race proof:** deterministic event-controlled tests demonstrate both
   cross-field races and stale mode-versus-OFF protection.
3. **Parity/safety:** focused runtime, B1, rollout, privacy and CLI tests pass
   unchanged; conflict paths have zero config effects.
4. **Full verification:** full `pytest tests -q`, critical flake8
   (`E9,F63,F7,F82`), compileall, and `git diff --check` at one exact
   revision.
5. **Independent review:** a read-only reviewer checks the lock/CAS design,
   expensive-validation window, CLI compatibility, exact revision and scope,
   then returns only `SHIP`, `FIX-FIRST`, or `RETHINK`.

## Explicit non-goals

- No persisted config schema/revision migration.
- No changes to `MemoryStore`, `StateStore`, `ProjectRegistry`, capture,
  retrieval, task/context, reminder, V2 rollout policy or Phase 20.
- No repair or retroactive inference of historical lost updates.
- No weakening of CANARY holdout or ACTIVE graduation gates.

## Package report template

```text
PACKAGE: W-15
REVISION: <exact implementation SHA>
OBJECTIVE: Prevent lost concurrent RuntimeConfig updates with lock/CAS.
FILES CHANGED: ...
ROOT CAUSE ADDRESSED: ...
TESTS ADDED: ...
TESTS EXECUTED: ...
QUALITY METRICS BEFORE: lost-update probes / baseline ...
QUALITY METRICS AFTER: ...
SAFETY METRICS: conflicts, final mode/approval, zero failed-write effects
KNOWN LIMITATIONS: ...
OPEN FAILURES: ...
INDEPENDENT REVIEW: SHIP / FIX-FIRST / RETHINK
SCORE BEFORE: ...
SCORE AFTER: ...
VERDICT: REVIEW PENDING
```

**Implementation authorization:** not granted until independent contract
review.  Phase 20 remains `FROZEN / LOCKED`; V2 remains `SHADOW`.
