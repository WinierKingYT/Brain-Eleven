# IG-07 Slice 2C Step C3 Independent Review

**REVIEWED REPOSITORY:** `WinierKingYT/Brain-Eleven`
**REVIEWED BRANCH:** `master`
**REVIEWED HEAD:** `2ae9aec` (implementation `1cc8846`, tests `c69ed46`,
identity fix `0bde793`, combined report `2ae9aec`)
**REVIEW DATE:** 2026-09-12
**REVIEWER:** Claude session `brain-eleven-66`
**REVIEWER ROLE:** Independent read-only reviewer
**IMPLEMENTATION PARTICIPATION:** None — implemented by Codex; this review
neither wrote nor edited `brain_eleven/memory/migrations.py`,
`brain_eleven/memory/__init__.py`, `scripts/migrate-memory-scope.py`, or
their tests.

## Method

C3 is the second canonical-write migration in IG-07 (after C1) and carries
the same higher evidence bar as C1 per `IG07-SLICE2C-PLAN.md` §4, §6.3 —
plus C3-specific requirements (§4.4) that rollback be proven to actually
protect against concurrent writers, not merely exist.

- Read `migrations.py` in full and compared it against the pre-migration
  script to separate the intentional behavior change (rollback CAS) from
  incidental refactoring.
- Read the adapter, including the intermediate `0bde793` fix, to understand
  why `MemoryStore` identity needed a direct import rather than routing
  through `_migration.MemoryStore`.
- Read every new test in `tests/test_memory_migrations_package.py` before
  running them, particularly the concurrent-writer CAS test, to judge
  whether it actually forces the race condition it claims to test.
- Independently re-ran the focused suite, full suite, critical flake8,
  `compileall`, and a clean-interpreter identity check.
- Diffed the commit range against `migrate-legacy-memory.py`,
  `brain_eleven/lifecycle/dedupe.py`, `scripts/dedupe-validated-memory.py`,
  and `scripts/memory_store.py`/`brain_eleven/memory/store.py` to confirm
  C1 and canonical store internals were not reopened.

## The rollback CAS fix — verified real, not just claimed

The pre-migration `rollback()` called `store.replace(deepcopy(normalized_backup))`
with no `expected_revision` (confirmed by reading the prior version, and
this was flagged as a required fix in the C3 instructions). The new
`rollback_scope()`:

1. reads the current canonical revision immediately before acting;
2. short-circuits to a guarded `"already_rolled_back"` no-op if the current
   payload already equals the backup payload (handles replaying the same
   rollback without churning the revision — a cleaner solution than a bare
   CAS retry loop, and satisfies the plan's "idempotent or explicitly
   guarded" requirement directly);
3. otherwise calls `store.replace(..., expected_revision=<the revision just
   read>)`.

`test_rollback_uses_cas_and_rejects_concurrent_writer` proves this
correctly: it monkeypatches `MemoryStore.replace` itself so that on the
first call it injects a real concurrent write (`store.append(...)`, which
independently bumps the canonical revision) *before* delegating to the
original `replace` with the *stale* `expected_revision` captured earlier —
correctly forcing the exact race the fix is supposed to catch, not just
calling `replace` with a wrong revision by hand. Re-ran it independently:
`MemoryStoreConflict` is raised, and the store afterward contains both the
original and the concurrent record — no silent overwrite, no data loss.

`test_rollback_restores_payload_and_is_guarded_on_replay` independently
confirms monotonic revision (`rollback["revision"] > migrated_document["revision"]`)
and that a second rollback of the same backup returns `"already_rolled_back"`
with the revision unchanged, rather than writing again.

## Adapter and identity — one real bug caught and fixed by the implementer's own tests

The adapter follows the established `_load_canonical` pattern. One detail
worth recording: an intermediate commit (`0bde793`) changed
`MemoryStore = _migration.MemoryStore` to `MemoryStore = _PackageMemoryStore`
(imported directly from `brain_eleven.memory` at the top of the adapter).
Both should be the same object in ordinary import order, but the direct
import is more robust against load-order edge cases — the kind of thing
the `anomaly.py` P2 finding (sys.modules load-order fragility, fixed
2026-09-11) was about. This was caught and fixed by the implementer's own
identity test before it reached this review, which is exactly the point of
having that test. Re-verified independently in a clean interpreter:
`adapter.MemoryStore is brain_eleven.memory.MemoryStore` holds.

Legacy `migrate`/`rollback` names are preserved as aliases to
`migrate_scope`/`rollback_scope` per the plan's explicit-namespace
requirement (§3.1) — no generic `migrate`/`rollback` export exists at the
package level, only on the adapter for backward compatibility.

## Regression

- C3 focused suite (`test_memory_migrations_package.py`,
  `test_memory_scope_migration.py`, `test_phase14_scope.py`'s idempotence
  test, `test_pre12_memory_state_caller_migration.py`): reproduced, **47
  passed**.
- Full suite: reproduced, **927 passed, 2 warnings** — matches the report
  exactly.
- `flake8 --select=E9,F63,F7,F82` over CI's scope plus `brain_eleven/`: 0.
- `compileall` on `brain_eleven/memory` and the adapter: clean.
- Working tree clean after sync.

## Safety / scope

- `migrate-legacy-memory.py`, `brain_eleven/lifecycle/dedupe.py`,
  `scripts/dedupe-validated-memory.py` (C1), and
  `scripts/memory_store.py`/`brain_eleven/memory/store.py` (canonical
  `MemoryStore` internals) are all untouched — confirmed by diff. C1's
  closed work was not reopened.
- `migrate_scope`'s apply path is unchanged from the pre-migration script
  (already used `no_change(...)` correctly, unlike the archived
  `migrate-legacy-memory.py`'s bug) — confirmed by reading the moved code
  side by side with the original.
- No new canonical write authority was introduced; both entry points
  continue to go through `MemoryStore.transact`/`replace`.

## P0 / P1 Findings

None.

## P2 Findings

- **Documentation accuracy, non-blocking:** `IG07-SLICE2C-COMBINED-REPORT.md`'s
  "COMMIT CHAIN" section cites `433b98e`, `b7c1327`, `34d4eac` as the C3
  commits — none of these exist in the repository (`git cat-file -t` fails
  on all three). The actual pushed commits are `1cc8846`, `c69ed46`,
  `0bde793`. This looks like local commits were rewritten (amended/rebased)
  before pushing without updating the already-drafted report text. The code
  itself was independently verified against the real pushed history, so
  this doesn't affect the SHIP verdict — corrected in the report below.

## Final Verdict

**SHIP** — IG-07 Slice 2C Step C3 (`migrate-memory-scope.py` →
`brain_eleven/memory/migrations.py`) is accepted, closing Slice 2C as a
whole (C1 + C3; C2 remains archived per the C0 decision). This is the
second canonical-write migration in IG-07 and, like C1, meets a
meaningfully higher bar than the read-only slices: the rollback CAS gap
identified in the plan is genuinely fixed and proven under an actually
forced race condition, not merely asserted. `migrate-legacy-memory.py`
remains excluded and untouched. IG-07's remaining scope
(`entity_extractor.py`/`knowledge_graph.py` bridges already closed in
Slice 2B; `install-cross-project-memory.py`, `remember.py`, `task_model.py`,
and `task_state_context.py` per `IG07-SLICE2-PLAN.md`) requires its own new
bounded plan before any further implementation.
