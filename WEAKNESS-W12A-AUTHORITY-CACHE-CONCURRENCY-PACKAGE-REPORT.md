# W-12A AuthorityCache Concurrency Package Report

**PACKAGE:** W-12A

**REVISION:** `d33b38d19374b88c02b2bd213755522e955b57f4`

**TEST REVISION:** `a76fd7dc20c52b91acb6f08d892fc06f5521917a`

**CONTRACT:** `aab3da1d7ccaaf89a298f608aac704da8889ca9b`

**STATUS:** CLOSED / SHIP

**PROGRAM STATE:** Phase 20 `FROZEN / LOCKED`; V2 `SHADOW`.

## OBJECTIVE

Serialize AuthorityCache read-modify-write operations so concurrent authority
resolution cannot lose derived entries or expose partially written JSON, while
preserving the cache's content-free, revision-bound and fail-open behavior.

## FILES CHANGED

- `authority/cache.py` — package-owned file locking, unlocked read/write
  helpers, atomic access refresh and store publication.
- `tests/test_w12a_authority_cache.py` — bounded process/thread concurrency,
  identity and failure-path evidence.

No resolver policy, canonical MemoryStore/StateStore/ProjectRegistry, cache
schema, V1/V2 path, HOLDOUT corpus or Phase 20 state changed.

## ROOT CAUSES ADDRESSED

`AuthorityCache.store()` previously read and replaced the cache without a
shared lock, allowing concurrent writers to overwrite one another. `load()`
refreshed `last_access_ns` with direct `write_text()`, which could expose
truncated JSON to readers. Both paths now use the existing package-owned
`brain_eleven.infrastructure.locking.file_lock` and a temp-file,
flush/fsync/atomic-replace writer.

## IMPLEMENTATION NOTES

- The lock covers the complete read-modify-write sequence for `store()` and
  the validated-hit refresh in `load()`.
- Missing, corrupt, invalid, stale-revision and lock-timeout loads remain
  cache misses.
- A validated hit is returned when only its access-refresh write fails,
  preserving the previous fail-open behavior.
- `TimeoutError` from cache locking is absorbed as miss/no-op. Other `OSError`
  write failures remain visible to the existing resolver degradation mapping.
- The 32-entry LRU order, schema version, revision matching and content-free
  result shape are unchanged.

## TESTS ADDED

- 16 independent spawned processes writing unique entries to one cache path;
- concurrent access refresh with a raw JSON reader;
- package/resolver identity;
- lock-timeout miss/no-op;
- refresh-write failure preserving a valid hit;
- fsync/replace failure visibility, canonical no-effect and temporary cleanup.

## TESTS EXECUTED

- Pre-fix focused baseline (test revision before implementation): expected
  failures in process preservation, atomic refresh, lock injection and
  refresh-failure hooks; 3 unrelated tests passed.
- W-12A focused module: **7 passed** on Windows.
- Existing authority/context regression plus W-12A: **28 passed**.
- Full Windows suite: **1273 passed, 4 skipped, 2 warnings**. Warnings are
  pre-existing FastAPI/Starlette deprecations.
- Critical flake8 (`E9,F63,F7,F82`) on touched Python files: **PASS**.
- `compileall` on touched Python files: **PASS**.
- `git diff --check`: **PASS**.

## QUALITY METRICS BEFORE / AFTER

| Measure | Before W-12A | After W-12A |
| --- | --- | --- |
| 16 concurrent unique stores | Lost entries and write races observed | 16/16 entries retained, 0 process errors |
| Concurrent refresh JSON integrity | Raw readers observed malformed JSON | 0 malformed JSON observations |
| Cache schema/LRU/revision behavior | Existing behavior | Preserved by existing and focused tests |

## SAFETY METRICS

- Canonical MemoryStore/StateStore/ProjectRegistry writes introduced: **0**.
- Raw prompt, transcript, secret or memory content stored: **0**.
- Cross-project canonical effect: **0**.
- Lock timeout and cache-write failures cannot mutate canonical authority.
- V1/V2, HOLDOUT labels/thresholds and Phase 20: **0 changes**.

## KNOWN LIMITATIONS

- The cache remains derived state; it has no durability contract beyond the
  existing temp-file flush/fsync/replace sequence.
- Parent-directory fsync is outside W-12A and was handled separately for
  MemoryStore in W-18.
- The Windows process stress exercises the existing cross-platform lock; the
  lock implementation itself is outside this package.

## OPEN FAILURES

No focused or full-suite failure remains. W-07B remains `FIX-FIRST /
NOT ACCEPTED`; Phase 20 remains `FROZEN / LOCKED` and V2 remains `SHADOW`.

## INDEPENDENT REVIEW

`/root/w10_exact_review` independently inspected the exact implementation and
test revisions, process stress, failure semantics, privacy boundary and
resolver compatibility. The review returned **SHIP**; self-review was not
used as acceptance. See
`WEAKNESS-W12A-AUTHORITY-CACHE-CONCURRENCY-INDEPENDENT-REVIEW.md`.

## SCORE BEFORE / AFTER

Persistence/concurrency: **8.5 → 8.5**. The package closes a concrete cache
race without claiming an unrelated score increase.

## VERDICT

**SHIP** — implementation, tests and independent evidence are pushed at their
exact revisions.
