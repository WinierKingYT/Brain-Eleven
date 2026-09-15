# W-15 Runtime Configuration CAS Package Report

**PACKAGE:** W-15  
**REVISION:** `7fd9d5a72d3995723c4f13f6fd07b541959ba30a`  
**STATUS:** CLOSED / SHIP — independently reviewed

## OBJECTIVE

Prevent concurrent runtime-config writers from silently losing operator
changes.  `RuntimeConfig.set_mode()`, `set_human_approval()`, and the
installer's canary-config update now share a sidecar lock and a snapshot
fingerprint guard while retaining the existing atomic JSON write path.

## FILES CHANGED

- `brain_eleven/runtime/storage.py`
- `brain_eleven/runtime/install.py` (config mutation call only)
- `tests/test_w15_runtime_config_race.py`
- `WEAKNESS-W15-RUNTIME-CONFIG-CAS-CONTRACT.md`

Hook/client configuration, manifests, canonical memory/state authorities,
retrieval, V2, and Phase 20 were not changed.

## ROOT CAUSE ADDRESSED

The old setters loaded a full document, changed one field, and replaced the
file without a shared lock or compare-and-swap.  A fault-injected baseline
allowed a delayed approval write to erase a newer mode update and a delayed
mode write to erase a newer approval update.  `runtime/install.py` also had a
direct config write outside the setter boundary.

## IMPLEMENTATION

- Added `RuntimeConfigConflict` as a `ValueError` subclass for CLI-compatible
  stale-snapshot failures.
- Added a deterministic in-memory config fingerprint (no schema/revision
  field) and `_commit()` that reloads under `config.json.lock`, rejects a
  changed snapshot, then uses existing `write_json()`.
- Kept CANARY holdout and ACTIVE graduation validation outside the commit lock;
  the final fingerprint check prevents a stale result from overriding a newer
  `OFF` or approval decision.
- Added `_mutate_current()` for the installer’s existing project-ID/mode
  update so it reloads and writes under the same config sidecar lock.

## TESTS ADDED

`tests/test_w15_runtime_config_race.py` covers:

- cross-field approval/mode stale writers in both directions;
- same-field stale contention;
- stale CANARY versus intervening `OFF`;
- installer config update versus concurrent approval;
- lock failure with zero config effect;
- unrelated-field preservation.

The initial red baseline failed at collection because
`RuntimeConfigConflict` did not exist; after implementation all focused cases
passed.

## TESTS EXECUTED

- Focused W-15 plus existing runtime/B1/rollout surfaces: **124 passed** before
  the final installer-race test was added; the added test passed separately.
- Full suite at exact revision `7fd9d5a`: **1200 passed, 2 warnings**.
- Critical flake8 (`E9,F63,F7,F82`) on touched Python files: **PASS**.
- `compileall` on touched Python files: **PASS**.
- `git diff --check`: **PASS**.

## QUALITY METRICS BEFORE / AFTER

Before (read-only race probe): both delayed setters returned success and the
last writer silently removed the other operator field.  After: deterministic
stale snapshots raise `RuntimeConfigConflict`; the winning file retains the
newer decision and unrelated fields.

## SAFETY METRICS

- Cross-field lost updates: prevented by fingerprint/CAS guard in focused tests.
- Stale CANARY over `OFF`: rejected; final mode remains `OFF`.
- Installer/approval field loss: not observed; project ID and approval remain.
- Atomic JSON path: existing temp-file + flush + fsync + replace retained.
- Phase 20: `FROZEN / LOCKED`; V2: `SHADOW`.

## KNOWN LIMITATIONS

- A same-value repeated write has no persisted revision and may be treated as
  idempotent because the validated document fingerprint is unchanged.
- Direct external `write_json(config.json, ...)` callers outside the bounded
  runtime mutation surfaces remain outside this package.
- Existing FastAPI/Starlette deprecation warnings remain unchanged.

## OPEN FAILURES

No W-15 focused or full-suite failures.  Independent review is still open.
Existing audit follow-ups W-07B (`FIX-FIRST / NOT ACCEPTED`) and W-12A remain
open; W-16–W-18 remain unaddressed.  No Phase 20 work is authorized.

## INDEPENDENT REVIEW

[`WEAKNESS-W15-RUNTIME-CONFIG-CAS-INDEPENDENT-REVIEW.md`](WEAKNESS-W15-RUNTIME-CONFIG-CAS-INDEPENDENT-REVIEW.md)
returned **SHIP** at exact package head `7fd9d5a`.  The reviewer independently
ran 119 focused tests, critical flake8, compileall and diff checks.  No P0/P1/P2
blocking findings remain.

## SCORE BEFORE / AFTER

Persistence/concurrency: **7.5 → 8.0**  
Scope/fail-closed safety: **8.0 → 8.0**  
Runtime config safety: **lost-update defect → bounded CAS/lock protection**

## VERDICT

**SHIP** — implementation and evidence are pushed, and independent review
accepted the package at the exact revision above.
