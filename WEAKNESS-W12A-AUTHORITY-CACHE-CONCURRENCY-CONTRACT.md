# W-12A Authority Cache Concurrency Contract

**Status:** BOUNDED CONTRACT / REVIEW PENDING

**Revision audited:** `10c8de10fe8fb438d3c9b1fe9870d691fdbb38a7`

**Program:** Engineering Weak-Point Improvement Goal

**Phase 20:** FROZEN / LOCKED

**V2 runtime:** SHADOW

**Implementation authorization:** This document defines the bounded package;
implementation remains subject to independent contract review.

## 1. Problem statement

`authority/cache.py::AuthorityCache` is a derived, content-free cache used by
`authority/resolver.py`. Its `store()` method reads the current JSON document,
modifies the entry set and replaces the file without a shared lock around the
whole read-modify-write operation. Its `load()` method also updates
`last_access_ns` with direct `write_text()` while serving a hit. Concurrent
authority resolutions can therefore lose entries, expose truncated JSON, or
race an access refresh. The cache is not canonical truth, but these failures
cause authority cache misses, avoidable recomputation and unstable latency.

## 2. Exact current evidence

At `authority/cache.py:16-40`, `load()` reads and validates the cache, updates
`entry["last_access_ns"]`, then writes the complete document with
`Path.write_text()`; no lock or atomic temporary file is used. At
`:42-70`, `store()` creates the parent, reads the old document, updates the
entry/LRU set and writes a temporary file with file fsync before
`Path.replace()`, but no lock surrounds the read-modify-write sequence.

`authority/resolver.py:24-30` constructs one cache per vault and
`:178-232` uses it only when the authority config enables caching. A cache hit
is converted through `resolution_result_from_dict`; a cache store failure is
already treated as derived-state degradation and must remain non-blocking.
`tests/test_context_engine_operational_surfaces.py:182-217` covers authority
cache revision/content/corruption/LRU behavior, but its concurrent stress at
`:219-275` intentionally exercises only RouterCache and CompilerCache. No
authority-cache concurrency proof exists.

The closed W-12 package established the compatible reference pattern in
`context_router/cache.py` and `context_compiler_v2/cache.py`: the existing
package-owned `brain_eleven.infrastructure.locking.file_lock` guards the full
operation and a temp-file flush/fsync/replace writer is used. W-12A applies
that pattern only to `authority/cache.py`.

## 3. Bounded scope

In scope:

- `authority/cache.py::AuthorityCache.load()` and `store()`;
- a private unlocked reader/writer helper if needed to avoid recursive locking;
- focused authority-cache concurrency, atomicity and failure tests;
- W-12A evidence and package report.

Out of scope:

- `authority/resolver.py` policy, candidate selection, lifecycle or scope
  behavior;
- canonical `MemoryStore`, `StateStore`, `ProjectRegistry` or any authority
  truth write;
- Router/Compiler caches already closed by W-12;
- V1/V2 ranking, retrieval, HOLDOUT data, Phase 20 and unrelated refactors.

## 4. Required invariants

1. `AuthorityCache` remains derived content-free state. No prompt, memory text,
   transcript, secret or canonical payload may be written.
2. One per-cache-path `file_lock` guards the entire read-modify-write for both
   `store()` and hit access refresh in `load()`. No second locking primitive is
   introduced.
3. Every access refresh and store uses temp-file write, flush, file fsync and
   atomic replace. Temporary files are removed after success and all failures.
4. Cache schema version `1`, `entries` shape, input-revision matching,
   `ResolutionResult` serialization, corruption-as-miss behavior and the
   32-entry LRU tie-break remain unchanged.
5. Cache lock, read, JSON or validation failures remain misses. A valid hit is
   still returned when only its `last_access_ns` refresh write fails, matching
   the existing fail-open behavior. `store()` lock/write failures are no-ops
   with no authority effect. The public cache methods absorb `TimeoutError`
   from `file_lock` (miss/no-op); `AuthorityResolver`'s existing `OSError`
   degraded mapping remains compatible for store failures.
6. Concurrent unique stores preserve every entry within the 32-entry bound;
   no writer may silently discard another writer's completed entry.
7. Authority cache changes do not alter canonical revisions, lifecycle,
   project isolation, policy results, V2 mode or Phase 20 state.

## 5. Required focused evidence

- A deterministic 16-independent-process writer stress against `AuthorityCache`
  preserves all 16 unique entries and produces parseable JSON.
- Concurrent authority-cache `load()` access refreshes never exposes malformed
  JSON to a raw reader and does not lose entries.
- Existing revision mismatch, corruption, content-free serialization and LRU
  tests pass without weakening assertions.
- Injected `load()` lock/read/JSON/validation failures return a cache miss;
  injected refresh-only `fsync`/replace failures after a validated hit preserve
  the hit result; injected `store()` lock/write failures are no-ops. None of
  these paths may change canonical MemoryStore/StateStore/ProjectRegistry
  bytes or revisions.
- An `authority.cache.AuthorityCache` and `authority.resolver.AuthorityResolver`
  parity check confirms the existing public objects and result behavior remain
  in use; no legacy `scripts` authority-cache surface exists or is introduced.
- Scope/privacy probes prove cache files contain only bounded authority metadata
  and no raw content or cross-project canonical effect.

## 6. Test and verification plan

Existing authority/resolver tests remain unchanged, especially
`tests/test_authority_resolver.py` and the cache surfaces in
`tests/test_context_engine_operational_surfaces.py`. Add a bounded W-12A test
module for process stress, concurrent access refresh, failure injection,
cleanup, identity and canonical-byte invariants.

Run the focused authority/cache/context suites, then full `pytest tests -q`,
critical flake8 (`E9,F63,F7,F82`) on touched Python files, `compileall` and
`git diff --check`. Every result must bind to the exact implementation/test
revision.

## 7. Exit gate

W-12A is eligible for independent `SHIP` only when all five gates pass:

1. **Identity:** the existing authority cache and resolver surfaces remain the
   same public objects.
2. **Concurrency/atomicity:** lock scope, unique-writer preservation, access
   refresh and temp-file durability are directly evidenced.
3. **Parity/safety:** revision, corruption, LRU, privacy, scope and fail-open
   semantics remain unchanged; canonical authorities are untouched.
4. **Full verification:** focused tests, full regression, critical flake8,
   compileall and diff-check pass.
5. **Independent review:** a separate read-only reviewer returns exactly
   `SHIP`, `FIX-FIRST` or `RETHINK`; self-review is not acceptance.

Until gate five returns `SHIP`, W-12A remains open and no retrieval/context or
V2 score increase is claimed. Phase 20 remains `FROZEN / LOCKED` and V2 remains
`SHADOW`.

## 8. Estimate and rollback

Expected implementation size is approximately 35–70 production lines and
100–180 focused test lines. Rollback is a code/test revert; no canonical data
or on-disk schema migration is introduced.

**Plan status: REVIEW PENDING — implementation başlamadı.**
