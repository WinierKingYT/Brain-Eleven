# W-08D Typed API Lifecycle Contract

PACKAGE: W-08D
STATUS: REVIEW PENDING — implementation not authorized
PROGRAM: Engineering Weak-Point Improvement Goal
PHASE 20: FROZEN / LOCKED
V2: SHADOW

## Objective

Make API lifecycle mutations use the same typed, fail-closed lifecycle rules as
the existing `MemoryLifecycleManager`, while preserving the canonical
`MemoryStore` transaction/CAS boundary. This contract covers the two existing
API mutation endpoints only; it does not promote V2, redesign retrieval, or
change the lifecycle model itself.

## Evidence-backed current state

The API implementation is `scripts/search-api.py`:

- `MemoryUpdate` at lines 109-115 accepts arbitrary `status: Optional[str]` and
  optional `expected_revision`.
- `update_memory()` at lines 616-671 reads the target from
  `validated_memory`, assigns `content`, `confidence`, and any truthy status,
  recomputes scope and fingerprint, then calls
  `MemoryStore.transact(..., expected_revision=update.expected_revision)` at
  lines 647-650. It rebuilds the graph after the transaction at lines 653-655.
- `delete_memory()` at lines 674-713 marks a record `deleted` and calls the
  same transaction boundary at lines 688-690, then rebuilds the graph at
  lines 692-694.
- Both endpoints catch `MemoryStoreConflict` and expose a 409 payload with the
  expected and actual revisions. Other exceptions are currently converted to a
  500 response containing the exception string.

The existing lifecycle implementation is `scripts/memory-lifecycle.py`:

- `MemoryLifecycleManager` is defined at lines 28-184 and is exposed through
  `brain_eleven.lifecycle`.
- `resolve_memory()` at lines 60-91 and `supersede_memory()` at lines 94-127
  assign typed status, lifecycle timestamps/actors/notes, and use
  `save()` at lines 174-184.
- `save()` calls `MemoryStore.replace(data,
  expected_revision=self.store_revision)`, so its snapshot is stale-safe.
- The manager's active filtering and lifecycle-chain behavior at lines 49-58
  and 130-171 are part of the existing contract and must remain unchanged.

The graph is derived, not an authority: API writes must continue to rebuild or
invalidate it only after a successful canonical transaction. `MemoryStore`,
`ProjectRegistry`, StateStore, capture, retrieval, V2, and Phase 20 are outside
this package.

## Root cause and bounded risk

The API currently has a second lifecycle mutation surface. A client can submit
an arbitrary status string, mark a record deleted without lifecycle metadata,
or move between lifecycle states without the manager's transition semantics.
This can create records that the lifecycle CLI, resolver, graph projection, and
retrieval classify differently. It also makes error/privacy behavior depend on
raw implementation exceptions.

Risk is HIGH because these endpoints mutate canonical memory and trigger a
derived graph rebuild. This is a typed-authority consolidation package, not a
script-to-package migration.

## Contracted behavior

1. **One canonical write boundary.** Every accepted API mutation must execute
   through the existing `MemoryStore.transact` or an explicitly shared
   lifecycle operation that preserves its lock, atomic replace, backup, and
   `expected_revision` CAS semantics. No endpoint may write JSON directly or
   call `MemoryStore.replace` with an unverified revision.
2. **Closed lifecycle vocabulary and transition matrix.** The bounded API
   surface uses these exact operations and statuses:

   | Operation | Allowed source → target | Required fields |
   |---|---|---|
   | ordinary PUT update | `active` (or missing legacy status) → `active` | content/confidence only; no lifecycle fields |
   | PUT resolve | `active`/missing → `resolved` | bounded `resolved_by` and optional `reason` |
   | PUT supersede | `active`/missing → `superseded` | non-empty `superseded_by` and optional `reason` |
   | DELETE | `active`/missing → `deleted` | no lifecycle target in the body |
   | repeated terminal operation | terminal → same terminal status | no-op response; no revision/graph write |

   `resolved`, `superseded`, and `deleted` are terminal for this package;
   terminal → another status, `deleted` through PUT, empty/unknown statuses,
   and missing supersession targets fail with fixed 422 codes. The
   implementation must preserve existing manager field names and timestamps;
   it may add a narrow typed adapter, but must not invent a second authority.
3. **Legal transitions only.** Existing active/resolved/superseded/deleted
   semantics, timestamps, actor/source fields, supersession links, and
   resolution notes must remain compatible with manager behavior. Illegal
   transitions fail without changing the memory revision, graph projection,
   or audit/derived files.
4. **Delete is typed.** DELETE remains soft-delete if that is the established
   API behavior, but it must use a typed lifecycle operation and preserve the
   existing response/status code and CAS behavior. It must not silently erase
   lifecycle lineage or create a status shape the manager cannot read.
5. **Target and scope validation.** Missing IDs remain 404. `MemoryUpdate`
   gains optional `project_id` only as a request-boundary check; DELETE gains
   the same optional query value. For a global record the value is ignored.
   For a project-scoped record it is required and must equal the stored opaque
   `project_id`; absent or mismatched values fail with `PROJECT_SCOPE_REQUIRED`
   or `PROJECT_SCOPE_MISMATCH` before any write. `project_root` is never
   accepted by these mutations and absolute roots never enter canonical data.
   Fingerprint recomputation must not turn a project record global.
6. **Graph consistency.** A graph rebuild/invalidation occurs only after a
   successful canonical commit. If rebuild fails, the API returns the existing
   bounded degraded/error behavior and must not claim a successful canonical
   update while hiding the projection failure. No graph write may precede the
   canonical commit.
7. **CAS and concurrency.** A stale `expected_revision` returns the existing
   409 conflict shape. Concurrent writers cannot be silently overwritten, and
   failed validation or lifecycle rejection must not increment the revision.
   No hidden retry is allowed.
8. **Bounded errors and privacy.** API errors must not expose prompt content,
   project roots, filesystem paths, secrets, or raw tracebacks. The fixed
   response table is: 404 `MEMORY_NOT_FOUND`; 409
   `MEMORY_STORE_REVISION_CONFLICT`; 422 `LIFECYCLE_TRANSITION_INVALID`,
   `PROJECT_SCOPE_REQUIRED`, `PROJECT_SCOPE_MISMATCH`, or
   `CAPTURE_SAFETY_REJECTED`; 503 `GRAPH_PROJECTION_DEGRADED` when canonical
   commit succeeded but the derived rebuild failed. A 503 payload must include
   only `canonical_status: committed`, the bounded memory ID, and the fixed
   projection code; it must never roll back or claim the graph is current.

## Explicit non-goals

- No change to `MemoryStore`, `ProjectRegistry`, StateStore, backup/restore, or
  lock implementations.
- No change to lifecycle concepts beyond sharing/validating their existing
  typed rules; no new autonomous planner, graph reasoner, or authority.
- No retrieval ranking, embedding/provider, task-aware context, V2 promotion,
  capture worker, native hook, Phase 20, or documentation beautification work.
- No migration of `scripts/search-api.py` into a package in this package. A
  later architecture slice may address that separately.
- No changes to frozen evaluation/holdout cases or thresholds.

## Required implementation evidence

### Caller inventory at source revision `ecee32b`

- API mutation definitions/callers: `scripts/search-api.py:615-671` and
  `:673-713`; the existing endpoint tests are
  `tests/test_search_api.py:335-401`.
- Lifecycle authority: `scripts/memory-lifecycle.py:28-184`, CLI dispatch at
  `:191-239`, and package bridge `brain_eleven/lifecycle/__init__.py:1-20`.
- Dedupe lifecycle caller: `brain_eleven/lifecycle/dedupe.py:17,69-91`, with
  legacy adapter `scripts/dedupe-validated-memory.py:31-35` and tests in
  `tests/test_lifecycle_dedupe.py:14-187`.
- Existing lifecycle compatibility tests:
  `tests/test_memory_lifecycle.py:94-305` and
  `tests/test_pre12_memory_state_caller_migration.py:247`.

The API endpoint is the only current HTTP lifecycle mutation surface. The
manager, dedupe tool, and their tests must remain behaviorally unchanged;
their caller inventory is included to prevent a new API adapter from silently
forking lifecycle semantics.

### Focused behavior tests

Add tests without weakening existing assertions in `tests/test_search_api.py`
and lifecycle tests. The new evidence must cover:

- unknown status rejection with no revision/graph effect;
- the complete matrix above, including required `project_id` behavior,
  terminal no-op/rejection, and fixed error codes;
- each legal manager-supported transition and illegal transition rejection;
- delete parity, lifecycle metadata/lineage preservation, and repeat delete;
- stale expected revision and concurrent writer conflict;
- missing target, wrong scope/project, malformed update, and safety rejection;
- graph rebuild runs only after commit, and rebuild failure is visible without
  rolling back or falsely claiming a projection success;
- canonical record/fingerprint/scope identity before and after accepted update;
- bounded error responses contain no raw content, root path, secret, or
  traceback;
- package/legacy identity for any shared lifecycle helper.

### Regression and static gates

- Existing `tests/test_search_api.py` and lifecycle/authority/state suites pass
  unchanged.
- Full `pytest tests -q` passes with no new warnings or failures.
- Critical flake8 selection `E9,F63,F7,F82` on every touched file passes.
- `compileall -q` and `git diff --check` pass.
- Frozen evaluator files, holdout labels, and Phase 20 documents have an empty
  diff.
- A before/after canonical fixture comparison proves IDs, fingerprints,
  scopes, statuses, lifecycle fields, and revisions obey this contract.

## Exit gate

W-08D is complete only when all five gates pass:

1. **Authority gate:** one canonical typed lifecycle path; no direct API file
   write or duplicate lifecycle authority.
2. **Parity/safety gate:** existing endpoint behavior and lifecycle semantics
   remain compatible; invalid transitions, scope errors, conflicts, and
   privacy boundaries are tested.
3. **Concurrency gate:** stale CAS and concurrent writer tests prove no silent
   overwrite or partial graph effect.
4. **Verification gate:** focused tests, full suite, critical static gates,
   compile/import sanity, diff check, and frozen evaluation comparison pass.
5. **Independent review gate:** a separate read-only reviewer examines the
   contract, diff, tests, failure evidence, authority boundaries, and rollback
   behavior and returns exactly `SHIP`, `FIX-FIRST`, or `RETHINK`. The
   implementer may not self-SHIP.

## Package report template

```text
PACKAGE: W-08D
REVISION: <exact reviewed SHA>
OBJECTIVE:
FILES CHANGED:
ROOT CAUSES ADDRESSED:
TESTS ADDED:
TESTS EXECUTED:
QUALITY METRICS BEFORE:
QUALITY METRICS AFTER:
SAFETY METRICS:
KNOWN LIMITATIONS:
OPEN FAILURES:
INDEPENDENT REVIEW:
SCORE BEFORE:
SCORE AFTER:
VERDICT: SHIP / FIX-FIRST / RETHINK
```

Plan status: **REVIEW PENDING — implementation not authorized.**
