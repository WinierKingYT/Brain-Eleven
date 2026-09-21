# TSC-02 — Independent Implementation Re-review

**PACKAGE:** TSC-02  
**REVIEW TYPE:** independent, read-only implementation re-review  
**REVIEWED CODE HEAD:** `709a9c2fe39fad78c6c4a1ae075a412c8e18db6b`  
**REVIEWED CORRECTION RANGE:** `b107a05`, `c8d71ed`, `4297a91`, `709a9c2`  
**PREVIOUS FIX-FIRST HEAD:** `56ddd43`  
**VERDICT:** `SHIP`

## Scope

This re-review covers the TSC-02 identity and registry-lineage implementation
and the cache access-refresh correction. No production code or package status
document was changed during review.

## Findings

### Cache race correction — PASS

`RouterCache.load()` and `AuthorityCache.load()` retain their public
two-argument signatures and default access-refresh behavior. The new
`load_read_only()` path disables the refresh with a context-local guard, while
Router and Authority call `touch()` only after the post-load lineage check
passes. The focused forced races mutate the registry inside each cache load;
both return `STALE_INPUT` with zero candidates and leave cache bytes
byte-for-byte unchanged (`tests/test_tsc02_identity.py:168-210`). The normal
cache-hit test verifies result parity and refreshed `last_access_ns` for both
Router and Authority (`tests/test_tsc02_identity.py:213-242`).

### Identity and lineage — PASS

`brain_eleven/projects/identity.py` is the sole root hashing authority. It
normalizes the registry root and emits the fixed-format,
domain-separated `project-root-v1:<64 lowercase hex>` digest. The validator
requires lineage, matches task/state project IDs, compares the current
registry revision and root identity, and maps stale or scope failures to
bounded results without returning a raw path. Composer re-reads the registry
around task/state resolution and refuses to publish a mixed context
(`scripts/task_state_context.py:140-184`).

### Serialization and route boundaries — PASS

The strict decoder requires the declared schema, the lineage member, exact
outer/state shapes, matching project IDs, and explicit project-free
`unresolved`/`global` forms (`authority/serialization.py:106-168`). Router
validates lineage before cache lookup, after a cache hit, before delivery and
before cache store. Authority performs its own lineage validation before
evidence/cache use and repeats it before cache store. Current-project stale,
reused-root, archived and unknown cases therefore fail closed with no project
candidates; global-only scope remains project-free.

### Scope, privacy and side effects — PASS

The correction diff is limited to the two cache modules, the two cache
callers, focused tests and this review artifact. Cache schema, revision
matching, LRU bound, canonical stores, registry persistence, retrieval,
evaluation inputs and native runtime are unchanged. New lineage fields and
lineage errors contain no raw root, registry document, memory content or
traceback text; the historical task raw request field remains governed by its
existing contract. The cache race paths do not write cache bytes, and no
MemoryStore, StateStore, ProjectRegistry or graph write is introduced.

## Verification

- `.venv\\Scripts\\python.exe -m pytest tests/test_tsc02_identity.py tests/test_context_router.py tests/test_authority_resolver.py tests/test_context_engine_operational_surfaces.py tests/test_w12a_authority_cache.py -q` — **64 passed**.
- `.venv\\Scripts\\python.exe -m pytest tests -q` — **1366 passed, 4 skipped, 2 warnings**.
- Critical flake8 (`E9,F63,F7,F82`) on all cumulative TSC-02 changed Python
  files — **passed**.
- `compileall -q` on all cumulative TSC-02 changed Python files — **passed**.
- `git diff --check` — **passed**.
- `evals.task_state_eval` suites `smoke`, `public`, `holdout`, and `all` —
  **all gates passed**.
- `git diff --quiet 56ddd43..709a9c2 -- evals/task_state_eval.py evals tests/evals tests/test_evaluation_schema.py` — **unchanged**.
- Direct cache compatibility probe — `load_read_only()` leaves bytes and
  access metadata unchanged; direct `load()` refreshes `last_access_ns` for
  both cache classes.

## Limitations

The package retains its documented conservative revision policy: any registry
revision change invalidates an older project context. This review accepts the
contract's two-phase revalidation and makes no broader registry/cache
atomicity claim beyond the tested load/validation race window.

## Decision

`SHIP` — the corrected cache ordering closes the prior FIX-FIRST finding, all
focused and full verification gates are green, and the bounded TSC-02
identity, lineage, serialization, privacy, authority and holdout requirements
remain satisfied at the exact reviewed code HEAD.
