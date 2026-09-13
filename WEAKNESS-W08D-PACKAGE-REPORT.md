# W-08D Typed API Lifecycle Package Report

PACKAGE: W-08D
REVISION: `805f081` (implementation `947d221`, privacy test `805f081`)
OBJECTIVE: Close the typed, fail-closed lifecycle boundary for the existing
`PUT /memories/{memory_id}` and `DELETE /memories/{memory_id}` API mutations
without adding a canonical authority or changing the lifecycle manager.

## FILES CHANGED

- `scripts/search-api.py`
- `tests/test_w08d_search_api_lifecycle.py`
- this report

No `MemoryStore`, `MemoryLifecycleManager`, `ProjectRegistry`, StateStore,
retrieval, capture, V2, Phase 20, or frozen evaluation file was changed.

## ROOT CAUSES ADDRESSED

- API updates previously accepted arbitrary status strings and bypassed typed
  lifecycle field requirements.
- API delete previously created a lifecycle state without the bounded API
  transition checks or terminal idempotence.
- Project-scoped API mutations had no request-boundary project identity check.
- Graph rebuild failures after a canonical commit were not exposed as a
  bounded degraded response.
- Error responses could expose raw implementation exception text.
- FastAPI's default request-validation payload could echo submitted project
  roots and oversized field values.

The implementation uses a narrow adapter for the existing lifecycle field
vocabulary and timestamps, while every accepted write still goes through the
existing `MemoryStore.transact` lock/atomic/CAS boundary. The adapter does not
write files or create another authority.

## TESTS ADDED

`tests/test_w08d_search_api_lifecycle.py` adds 13 focused tests covering:

- unknown/illegal status rejection without revision or graph effects;
- resolve metadata and terminal no-op behavior;
- supersession target existence and same-scope checks;
- typed delete and repeated-delete no-op;
- project scope required/mismatch/accepted/global-ignore behavior;
- stale expected-revision rejection;
- post-commit graph degradation visibility;
- capture-safety ordering and bounded missing-memory errors;
- request-validation privacy for extra path fields and oversized values.

## TESTS EXECUTED

- W-08D focused tests: **13 passed, 2 dependency warnings**.
- Existing API/lifecycle suites (`test_search_api.py`,
  `test_memory_lifecycle.py`, `test_lifecycle_dedupe.py`,
  `test_authority_resolver.py`): **74 passed, 2 dependency warnings**.
- Combined focused verification including
  `test_pre12_memory_state_caller_migration.py`: **119 passed, 2 dependency
  warnings**.
- Full `pytest tests -q`: an initial run exposed one transient cold native
  SessionStart failure (`test_ig00_bootstrap.py::test_cold_native_session_start_delivers_v1_within_hook_budget`);
  its isolated rerun passed, and the clean full-suite rerun at the final
  evidence revision completed with **1050 passed, 2 dependency warnings**.
- Critical flake8 (`E9,F63,F7,F82`) on all touched Python files: **PASS**.
- `compileall` on all touched Python files: **PASS**.
- `git diff --check`: **PASS**.

## QUALITY METRICS BEFORE / AFTER

| Metric | Before | After |
|---|---:|---:|
| Unknown lifecycle status | accepted | fixed 422 rejection |
| Legal typed transitions | partial/untyped | active→resolved, active→superseded, active→deleted |
| Terminal repeat writes | revision/write possible | no revision, cache, or graph write |
| Project scope request check | absent | required/exact for project records; global request ignored |
| Graph failure visibility | raw 500 path | bounded 503 `GRAPH_PROJECTION_DEGRADED` after commit |
| Mutation error privacy | raw exception detail possible | fixed content-free codes |

## SAFETY METRICS

- Direct API file writes: **0**.
- New canonical authorities: **0**.
- Stale CAS silent overwrite: **0 in focused evidence**.
- Invalid transition revision effect: **0 in focused evidence**.
- Cross-project supersession target: rejected.
- Project scope leakage in mutation requests: rejected or ignored only for
  global records, as contracted.
- Graph write before canonical commit: **0 in tested paths**.

## KNOWN LIMITATIONS

- The API remains a legacy script surface; migrating `scripts/search-api.py`
  into a package is explicitly deferred to a later architecture slice.
- The first full-suite attempt showed a transient native cold-start failure;
  the clean rerun passed and the isolated test was also green.
- The implementation report does not claim independent review or SHIP.

## OPEN FAILURES

- Independent read-only implementation review is pending.
- Reviewer verification of the complete transition matrix, concurrent writer
  behavior, and frozen-file diff is still required.

## INDEPENDENT REVIEW

**REVIEW PENDING.** The implementer has not self-approved this package.

## SCORE BEFORE / AFTER

- Persistence/concurrency: **7.5 → pending independent review**
- Scope/fail-closed mutation safety: **7.0 → pending independent review**
- API lifecycle reliability: **new bounded evidence; no graduation score
  assigned before review**

VERDICT: **REVIEW PENDING — implementation complete, independent acceptance not performed**
