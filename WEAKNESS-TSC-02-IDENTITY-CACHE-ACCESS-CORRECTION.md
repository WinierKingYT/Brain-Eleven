# TSC-02 — Cache Access Refresh Correction Follow-up

**PACKAGE:** TSC-02  
**STATUS:** IMPLEMENTED CORRECTION / INDEPENDENT REVIEW PENDING  
**BASELINE REVIEW HEAD:** `56ddd43`  
**IMPLEMENTATION REVISIONS:** `b107a05`, `4297a91`  
**TEST REVISION:** `c8d71ed`  
**PROGRAM:** Engineering Weak-Point Improvement Goal  
**PHASE 20:** FROZEN / LOCKED  
**V2 RUNTIME:** SHADOW

## Trigger

The independent implementation review at exact HEAD `56ddd43` found that
`RouterCache.load()` and `AuthorityCache.load()` refreshed
`last_access_ns` and rewrote cache bytes before the Router/Authority
post-load lineage check. When a registry mutation was injected during the
load, the caller correctly returned `STALE_INPUT`, but the stale request had
already changed its derived cache file.

## Bounded correction

- Both cache loaders now parse and validate a matching entry under the
  existing file lock, while preserving their public two-argument signatures
  and default access-refresh behavior.
- `load_read_only()` uses a context-local refresh guard and delegates through
  `load()`, so existing load injection and caller compatibility remain intact.
- Router and Authority use `load_read_only()` for lineage-sensitive lookups.
  They call the explicit `touch()` access refresh only after the post-load
  lineage comparison succeeds.
- The cache writer, schema, revision matching, LRU bound, canonical stores,
  registry persistence, retrieval, evaluation inputs and native runtime were
  not changed.

## Files changed

- `context_router/cache.py`
- `authority/cache.py`
- `context_router/router.py`
- `authority/resolver.py`
- `tests/test_tsc02_identity.py`
- this correction note

## Focused evidence

`tests/test_tsc02_identity.py` now records cache bytes after a valid warm hit,
mutates the registry inside each cache loader, and proves for both paths:

- result status is `STALE_INPUT`;
- candidate tuple is empty;
- cache bytes are byte-for-byte unchanged.

The same focused module sets a known old access timestamp and proves Router
and Authority current cache hits preserve result parity while refreshing
`last_access_ns` after validation.

Focused command:

```text
\.venv\Scripts\python.exe -m pytest tests/test_tsc02_identity.py tests/test_context_router.py tests/test_authority_resolver.py tests/test_context_engine_operational_surfaces.py tests/test_w12a_authority_cache.py -q
64 passed in 7.37s
```

## Verification

- Full regression: `\.venv\Scripts\python.exe -m pytest tests -q` — **1366
  passed, 4 skipped, 2 warnings** in `295.96s`.
- Critical flake8 on all changed Python files with
  `--select E9,F63,F7,F82` — **passed**.
- `\.venv\Scripts\python.exe -m compileall -q` on all changed Python files —
  **passed**.
- `git diff --check` — **passed**.

## Safety and scope

The reviewed stale-load path performs no cache write before the lineage
decision, and no canonical MemoryStore, StateStore or ProjectRegistry write
was introduced. Existing direct cache callers retain the prior access-refresh
semantics. The correction is limited to the load/validation ordering defect;
no broader registry/cache atomicity claim is made.

## Open status

No focused or full-regression failure remains for this correction. An
independent read-only implementation review of the final exact revision is
still required. This note does not self-accept the package.

**INDEPENDENT REVIEW:** REVIEW PENDING  
**VERDICT:** REVIEW PENDING
