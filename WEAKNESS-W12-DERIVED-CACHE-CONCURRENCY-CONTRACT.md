# W-12 — Derived Cache Concurrency Contract

**Status:** CONTRACT / IMPLEMENTATION NOT AUTHORIZED

**Program boundary:** Engineering Weak-Point Improvement Goal

**Phase 20:** FROZEN / LOCKED

**V2 runtime:** SHADOW

## Problem

`context_router/cache.py::RouterCache` and
`context_compiler_v2/cache.py::CompilerCache` perform read-modify-write
updates without a shared file lock. Router cache reads also rewrite
`last_access_ns` with direct `write_text`; compiler cache reads do the same.
Concurrent writers can overwrite each other's derived entries, and a process
interruption during an access update can leave a partial cache. A bounded
16-writer probe reproduced both classes' loss of almost all entries (one entry
survived from sixteen writes). These caches are derived, content-free
projections; canonical memory/state/authority is not affected.

## Objective

Make router and compiler derived-cache updates safe across concurrent
processes while preserving cache semantics:

- one per-cache sidecar lock guards the complete read-modify-write operation;
- every write path, including `last_access_ns` refresh, uses temp-file,
  flush/fsync, and atomic replace;
- corrupt, missing, stale, or unsafe cache data continues to fail closed;
- LRU bounds and revision/key validation remain unchanged.

## Bounded implementation

Only these production files may change:

- `context_router/cache.py`
- `context_compiler_v2/cache.py`

Focused tests may change or be added under `tests/`. Use the existing
package-owned `brain_eleven.infrastructure.locking.file_lock` surface (also
re-exported by `brain_eleven.infrastructure`); do not create a second locking
primitive or change canonical store locking. Refactor internal unlocked
readers/helpers as needed so `CompilerCache.store()` does not recursively
acquire its own lock. `authority/cache.py` is out of scope and must not be
changed in this package. It has the same pre-existing race and is recorded as
an explicit follow-up (`W-12A`); closing W-12 does not claim that authority
caching is fixed.

## Invariants

1. A cache operation never writes canonical memory, state, authority, or
   user-facing context.
2. `load(key, revisions)` still returns only a matching, content-safe entry;
   a mismatch, malformed JSON, unsafe manifest, or lock/write failure remains
   a cache miss/failure as before.
3. `store()` retains the complete set of concurrently committed entries up to
   the existing 32-entry bound; deterministic LRU eviction remains unchanged.
4. `last_access_ns` refresh is atomic and cannot truncate a valid cache file.
5. Temporary files are cleaned after success and exceptions.
6. Existing schema version, key/revision validation, corruption tolerance,
   privacy keys, and cache-disabled caller behavior do not change.
7. Lock timeout/failure must not affect canonical runtime truth; callers may
   observe a cache miss or existing cache-write warning only.

## Required evidence

- A deterministic multithread/process-style stress test writes 16 unique keys
  concurrently to each cache and proves all 16 survive (under the 32-entry
  bound) with no malformed JSON.
- Concurrent `load()` access refreshes do not lose entries and the final file
  remains atomically parseable.
- Existing corruption, revision mismatch, content-safety, and LRU tests pass
  unchanged.
- No changes occur in `authority/cache.py`, canonical stores, V1/V2 ranking,
  HOLDOUT data, or Phase 20.
- Focused suite, full `pytest tests -q`, critical flake8, compileall, and
  `git diff --check` pass at the exact revision.
- Independent read-only review checks lock scope, atomicity, bounded cache
  semantics, privacy, and canonical-authority boundaries.

## Exit gate

The package is `SHIP` only after all evidence passes and an independent
reviewer returns exactly `SHIP`. Until then it is `REVIEW PENDING` and no
retrieval quality or V2 promotion claim may be made.

## Package report template

`WEAKNESS-W12-DERIVED-CACHE-CONCURRENCY-PACKAGE-REPORT.md` must record:

`PACKAGE`, `REVISION`, `OBJECTIVE`, `FILES CHANGED`, `ROOT CAUSES ADDRESSED`,
`TESTS ADDED`, `TESTS EXECUTED`, `QUALITY METRICS BEFORE`,
`QUALITY METRICS AFTER`, `SAFETY METRICS`, `KNOWN LIMITATIONS`,
`OPEN FAILURES`, `INDEPENDENT REVIEW`, `SCORE BEFORE`, `SCORE AFTER`, and
`VERDICT`.

**Contract status:** REVIEW PENDING — implementation not authorized by this
document alone.
