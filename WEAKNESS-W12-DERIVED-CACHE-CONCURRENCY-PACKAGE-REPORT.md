# W-12 — Derived Cache Concurrency Package Report

**PACKAGE:** W-12  
**REVISION:** `4cde804c39ee0f6f316308d10a14034f153bef9f` (code/test head)  
**CONTRACT:** `051ca12ba80d4777c99cb4af856d247103082e7c`  
**OBJECTIVE:** Preserve derived router/compiler cache entries under concurrent
read-modify-write and make access-time refresh atomic.

**PROGRAM STATE:** Phase 20 `FROZEN / LOCKED`; V2 `SHADOW`.

## Files changed

- `context_router/cache.py`
- `context_compiler_v2/cache.py`
- `tests/test_context_engine_operational_surfaces.py`

The implementation uses the existing package-owned
`brain_eleven.infrastructure.locking.file_lock` sidecar surface. It does not
change canonical stores, authority resolution, ranking, HOLDOUT, V2, or Phase
20 behavior.

## Root causes addressed

- Router and compiler `store()` paths previously performed unlocked
  read-modify-write operations.
- Both `load()` paths refreshed `last_access_ns` with direct `write_text`,
  exposing truncated JSON to concurrent readers.
- The router cache could propagate derived-cache lock/write errors into route
  execution; lock/write failures now fail open as a cache no-op.

## Tests added

- 16-thread unique-key preservation for RouterCache and CompilerCache.
- Concurrent access-time refresh with a raw reader proving no partial JSON.
- Nonfatal lock-failure behavior for both derived caches.

## Tests executed

- Pre-fix 16-writer probe: both caches repeatedly retained one entry and
  produced `PermissionError` failures.
- Focused cache/router/compiler suite: **48 passed**.
- Separate 10-round × 16-process stress probe: **0 failures** for each cache.
- `pytest tests -q`: **1182 passed, 2 dependency warnings** at exact final
  code/test head `4cde804`.
- Critical flake8 (`E9,F63,F7,F82`) on touched files: **passed**.
- `compileall` on touched files: **passed**.
- `git diff --check`: **passed**.

## Quality metrics before / after

| Measure | Before W-12 | After W-12 |
| --- | --- | --- |
| 16 concurrent unique stores preserved | 1 entry with errors | 16 entries, 0 errors |
| Concurrent raw-reader JSON decode failures | Repeated failures | 0 observed |
| Cache bound | 32 entries | 32 entries, unchanged |
| Revision/key/content-safety semantics | Baseline | Unchanged |

## Safety metrics

- Canonical MemoryStore/StateStore/ProjectRegistry writes introduced: **0**.
- User-facing context or raw prompt stored in these caches: **0**.
- Cache lock/write failure affecting canonical route truth: **0** (cache no-op).
- HOLDOUT corpus, labels, thresholds, ranking weights: **0 changes**.
- V2 promotion or Phase 20 unlock: **0**.

## Known limitations and follow-up

- `authority/cache.py` has the same pre-existing race and remains outside this
  package by contract. It is tracked explicitly as **W-12A OPEN**; W-12 does
  not claim authority-cache concurrency is fixed.
- The sidecar lock uses the existing default timeout; a contended cache call
  may wait for that bounded lock timeout before failing open. Canonical route
  and compiler results remain independent of cache availability.

## Open failures

- No W-12 focused or full-suite failure remains.
- W-12A authority-cache follow-up remains open.
- Independent read-only review is still required before package closure.

## Independent review

**REVIEW PENDING.** The implementer does not self-declare `SHIP`.

## Score before / after

- Persistence/concurrency: **7.0 / 10 before**; no score increase is claimed
  before independent review.
- Architecture/derived-cache reliability: **7.0 / 10 before**; W-12A remains
  open.

## Verdict

**REVIEW PENDING**
