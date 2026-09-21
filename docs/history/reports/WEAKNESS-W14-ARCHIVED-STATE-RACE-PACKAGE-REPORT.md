# W-14 Archived Project State-Mutation Race Package Report

PACKAGE: W-14  
REVISION: `aef19b8f3d5d3de93b63e6c94c80231f848233af`

## Objective

Serialize the registry active-status check with typed StateService mutations so a
project cannot be archived between validation and the state write.

## Files changed

- `scripts/state_store.py`: StateService `init_project()` and `_mutate()`
  now hold the existing registry sidecar lock across the active check and
  state-store transaction. A bound wrapper maps lifecycle lock timeouts to the
  existing `StateStoreLockTimeout` type while preserving existing state-lock
  fault injection.
- `tests/test_w14_archived_state_race.py`: archive-first, mutation-first
  serialization, and lifecycle-lock timeout coverage.
- `WEAKNESS-W14-ARCHIVED-STATE-RACE-CONTRACT.md`: bounded contract.

No ProjectRegistry/StateStore schema, MemoryStore, retrieval, V2, or Phase 20
implementation changed.

## Root cause addressed

The old StateService performed `_require_active_project()` before entering the
state lock. ProjectRegistry archive and StateStore mutation therefore had no
common linearization boundary. An event-controlled probe archived the project
after the check and observed a successful requirement write.

The fix uses the existing registry sidecar lock first, then the existing state
store lock. ProjectRegistry mutations use the same registry lock, so archive and
check/write serialize without a new authority.

## Tests added

- archive-first rejects with `StateProjectArchived` and leaves state byte/data
  unchanged;
- mutation-first holds the registry lock through the state commit while a
  concurrent archive waits, then both complete in order;
- registry lifecycle lock timeout maps to `StateStoreLockTimeout` with no
  revision change.

## Tests executed

- Pre-fix W-14 race test: **1 passed, 1 failed** as expected; archive bypassed
  the unlocked boundary.
- W-14 focused after fix: **3 passed**.
- State/registry/runtime focused set: **72 passed** before the final timeout
  coverage; final W-14 test set: **3 passed**.
- Full suite at exact revision: **1193 passed, 2 warnings**.
- Critical flake8 (`E9,F63,F7,F82`): PASS.
- compileall: PASS.
- `git diff --check`: PASS.

## Safety metrics

- Archive-first rejected mutation: zero state revision/event/receipt effects.
- Mutation-first serializes and commits exactly once.
- Lifecycle lock timeout: surfaced as the existing StateService error type.
- Existing stale revision, operation receipt, state lock, wrong-project and
  sequential archive tests remain green.
- Phase 20: `FROZEN / LOCKED`.
- V2: `SHADOW`.

## Known limitations

- The shared registry sidecar is held while the state transaction runs; this is
  deliberate for correctness and adds bounded contention to typed state writes.
- The fix covers StateService typed writes. Direct low-level StateStore writes
  remain outside the public lifecycle policy by design.
- The full suite retains two pre-existing dependency deprecation warnings.

## Open failures

- Independent implementation review is pending.
- W-07B remains `FIX-FIRST / NOT ACCEPTED`.
- W-12A (AuthorityCache concurrency) remains open.
- W-15 through W-18 remain audit findings; no work on them is implied here.

## Independent review

Contract review: **SHIP** at contract revision `0fed4bd`. Implementation
review: **SHIP** at exact implementation/test revision `aef19b8`, with current
evidence/docs head `439a62c`. The independent reviewer reran the W-14/state/
registry/runtime focused set (**110 passed**, 2 inherited dependency warnings),
repeated the race test 10 times (**30/30 passed**), and verified critical
flake8, compileall and diff checks. The lock ordering, archive-first rejection,
mutation-first serialization, timeout mapping and scope boundaries were all
accepted. A 250 ms scheduling window in the mutation-first test was noted as a
non-blocking test-quality improvement; source-level lock proof is independent
of that timing window.

SCORE BEFORE: persistence/concurrency 7.0/10; scope/fail-closed 7.5/10  
SCORE AFTER: persistence/concurrency 7.5/10; scope/fail-closed 8.0/10

VERDICT: **SHIP**

