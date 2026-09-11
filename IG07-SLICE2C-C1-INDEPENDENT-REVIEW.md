# IG-07 Slice 2C Step C1 Independent Review

**REVIEWED REPOSITORY:** `WinierKingYT/Brain-Eleven`
**REVIEWED BRANCH:** `master`
**REVIEWED HEAD:** `1905a78` (implementation `5a3338a`, tests `de58837`, report `1905a78`)
**REVIEW DATE:** 2026-09-12
**REVIEWER:** Claude session `brain-eleven-66`
**REVIEWER ROLE:** Independent read-only reviewer
**IMPLEMENTATION PARTICIPATION:** None — implemented by Codex; this review
neither wrote nor edited `brain_eleven/lifecycle/dedupe.py`,
`brain_eleven/lifecycle/__init__.py`, `scripts/dedupe-validated-memory.py`,
or their tests.

## Method

Unlike Slice 1/2A/2B, this migration touches a real canonical-write path, so
"byte-identical move" is not the applicable bar — the plan
(`IG07-SLICE2C-PLAN.md` §4, §6.3) required idempotence, CAS/stale-snapshot,
dry-run, backup, and integrity evidence. Verified:

- Read the full diff against the pre-migration script line by line (not just
  the stat) to confirm every behavioral difference was an intentional,
  requested change (the `(timestamp, memory_id)` tie-break) and not an
  accidental rewrite.
- Read the new adapter and confirmed the `_load_canonical` pattern matches
  prior slices.
- Read all new tests in `tests/test_lifecycle_dedupe.py` before running them,
  to judge whether they actually exercise the claimed safety properties
  rather than just asserting trivial outcomes.
- Independently re-ran the focused suite, the full suite, critical flake8,
  `compileall`, and a clean-interpreter identity check.
- Diffed the commit range against `migrate-legacy-memory.py`,
  `migrate-memory-scope.py`, `scripts/memory_store.py`,
  `scripts/memory-lifecycle.py` to confirm the C0-scoped exclusions held.

## Implementation: intentional behavior change, correctly scoped

This is not a pure move (Slice 2B's standard doesn't apply here) — variable
names were clarified (`mem`→`memory`, `fp`→`fingerprint`), type hints added,
and one real behavior change was made: `plan_dedupe`'s sort key became
`(timestamp, memory_id)` instead of just `timestamp`. This is exactly the
tie-break fix specified in the C1 instructions (the original script's
implicit reliance on list order for equal-timestamp records was silently
non-deterministic). Confirmed via `test_equal_timestamp_winner_is_deterministic_and_superseded_is_ignored`,
which asserts the same winner is chosen whether input order is forward or
reversed — a real test of the property, not a restatement of the code.

`main()` gained an optional `argv: Sequence[str] | None` parameter
(defaulting to `sys.argv[1:]`), consistent with the additive CLI-testability
pattern already used in `maintenance.py` and `entities.py` from earlier
slices. No other behavior changed.

## Safety-contract evidence — verified real, not just present

Each test was read for what it actually proves, not just that it exists:

- **Idempotence** (`test_apply_is_idempotent_and_second_run_does_not_save`):
  a spy `MemoryLifecycleManager` proves `save()` is called exactly once
  across two `--apply` runs — the second run's `plan_dedupe` correctly
  produces an empty action list because superseded records are excluded,
  so no write is attempted at all. This is a stronger proof than "output
  unchanged" — it shows the canonical store is never touched a second time.
- **CAS/stale-snapshot** (`test_save_rejects_stale_snapshot_without_silent_overwrite`):
  a concurrent `MemoryStore.append` between manager construction and `save()`
  is shown to raise `MemoryStoreConflict`, and — critically — the test then
  re-reads the store and confirms the loser record is still `"active"` and
  the concurrent record survived. This proves no silent partial write
  happened, not just that an exception was raised.
- **Dry-run** (`test_dry_run_has_no_canonical_effect_and_apply_creates_backup`):
  proves `save()` is never called without `--apply` (via the same spy
  pattern) and that the store is byte-identical before/after, then proves
  the backup file is created on the following `--apply` run.
- **Integrity** (`test_dedupe_preserves_record_count_and_id_set`): record
  count and ID set are compared before/after across three records including
  one with an unrelated `status="resolved"`, confirming dedupe doesn't
  touch records outside its own fingerprint clusters.
- **Already-superseded protection** is folded into the tie-break test (a
  pre-superseded record with an earlier timestamp is correctly excluded from
  becoming canonical or being re-superseded).

All five of these were independently re-run, not just read: **55 passed**
across the focused suite (`test_lifecycle_dedupe.py`,
`test_pre12_memory_state_caller_migration.py`, `test_memory_lifecycle.py`,
`test_memory_store.py`).

## Regression

- Full suite: reproduced, **920 passed, 2 warnings** — matches the report
  (913 baseline + 7 new dedupe tests* verified via file count, not just the
  headline number).
- `flake8 --select=E9,F63,F7,F82` over CI's scope plus `brain_eleven/`: 0.
- `compileall` on `brain_eleven/lifecycle` and the adapter: clean.
- Clean-interpreter identity check (package, adapter loaded via
  `spec_from_file_location`, matching the test's own loading method):
  `plan_dedupe` and `main` resolve to the same objects across both surfaces.
- Working tree clean after sync; no stray files.

## Safety / scope

- `migrate-legacy-memory.py` and `migrate-memory-scope.py` are untouched —
  confirmed by diff, consistent with the C0 decision recorded in
  `IG07-SLICE2C-PLAN.md` §11 (legacy migration archived, not touched; scope
  migration gated on this review).
- `scripts/memory_store.py` and `scripts/memory-lifecycle.py` (the
  `MemoryStore`/`MemoryLifecycleManager` implementations) are untouched —
  confirmed by diff. The dedupe migration correctly builds entirely on the
  existing CAS-guarded `save()` path rather than introducing any new write
  mechanism.
- No new canonical write authority was introduced.

## P0 / P1 Findings

None.

## P2 Findings

None new. Slice 1's hook-timing stabilization P2 was independently
investigated and closed as "no reproducible issue" this session
(2026-09-11, ~90 reproduction attempts, no code change warranted). The
`anomaly.py` `sys.modules` P2 was fixed the same session (`9712d39`). No P2s
remain open from prior slices.

## Final Verdict

**SHIP** — IG-07 Slice 2C Step C1 (`dedupe-validated-memory.py` →
`brain_eleven/lifecycle/dedupe.py`) is accepted. This is the first
canonical-memory-writing migration in the IG-07 series, and it meets a
meaningfully higher evidence bar than the read-only/derived-projection
slices before it: idempotence, CAS-conflict, dry-run, backup, and integrity
properties are all proven by tests that would fail if the property didn't
actually hold, not merely asserted. Step C3 (`migrate-memory-scope.py` +
rollback) may now begin under its own bounded contract, per
`IG07-SLICE2C-PLAN.md` §5's sequencing. `migrate-legacy-memory.py` remains
archived per the C0 decision and out of scope unless that decision is
revisited.
