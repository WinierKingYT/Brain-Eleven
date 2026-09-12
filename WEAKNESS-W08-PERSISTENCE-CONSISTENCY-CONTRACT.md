# W-08 Persistence Consistency Contract

**Status:** BOUNDED CONTRACT / PLAN ONLY  
**Revision audited:** `ad8c544697616243c688e47db3adf1922d25cf5e`  
**Program:** Engineering Weak-Point Improvement Goal  
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW  
**Implementation authorization:** Not granted by this document.

This contract records the persistence-consistency findings from the W-08 audit and
defines the smallest first implementation slice. The first slice is limited to
`ProjectRegistry` durability and optimistic revision checks. Backup coordination,
state/memory reference races, and API lifecycle typing are documented as separate
follow-up slices; they must not be mixed into the first change.

## 1. Problem statement

The repository has three canonical authorities with different persistence
guarantees:

| Authority | Current guarantee | Gap found |
|---|---|---|
| `MemoryStore` | Sidecar lock, revision/CAS, backup, flush/fsync and atomic replace | Used as a consistency reference by other authorities, but no shared multi-file snapshot exists. |
| `StateStore` | Per-project CAS, file lock, backup, flush/fsync, atomic replace and audit events | Memory reference validation happens before the state transaction and is not bound to a memory revision. |
| `ProjectRegistry` | Sidecar file lock and atomic temp-file replace | No revision/CAS, no flush/fsync, no registry backup, and no stale-writer evidence. |

These are four related but independently bounded problems:

1. A backup can read canonical memory, registry, settings and state at different
   moments.
2. Registry mutations can overwrite a stale logical snapshot and have weaker
   crash-durability guarantees than the other authorities.
3. A state memory reference can be validated against one memory snapshot and
   committed after the memory lifecycle has changed.
4. The API update/delete endpoints write status strings directly instead of
   using a typed lifecycle/truth operation.

The first implementation package is **W-08A — ProjectRegistry durability and
CAS parity**. It establishes source metadata needed by later backup work while
keeping all memory, state, API, retrieval and Phase 20 behavior unchanged.

## 2. Exact current evidence

### 2.1 ProjectRegistry — W-08A target

`brain_eleven/projects/registry.py:12-20` is an identity-preserving package
surface which imports the implementation from `scripts/project_registry.py`.
The implementation remains in the legacy module; this contract does not move it.

`scripts/project_registry.py:26-28` defines `REGISTRY_SCHEMA_VERSION = 1`, the
registry filename and the valid statuses. `scripts/project_registry.py:50-64`
implements `_atomic_write`: it writes JSON to a temporary file and calls
`Path.replace`, but the handle is not explicitly flushed/fsynced and the parent
directory is not synced.

`scripts/project_registry.py:66-71` creates a registry with `schema_version`,
`updated_at` and `projects`, but no monotonic `revision`.

`scripts/project_registry.py:81-90` loads the file and treats a missing file as
an empty registry. `scripts/project_registry.py:92-115` validates schema,
identity uniqueness, status and `proactive_capture`, but has no revision field to
validate.

`scripts/project_registry.py:116-123` is the write boundary. It acquires
`file_lock(self.path)`, loads the latest data, invokes a callback, validates and
writes. It has no `expected_revision`, so a caller cannot reject a stale logical
operation. The mutators at `161-207` (`register`), `209-225` (`relocate`),
`227-241` (`rename`), `243-257` (`set_status`), `259-270`
(`set_proactive_capture`) and `272-305` (legacy opt-in migration) all route
through this boundary.

For comparison, `scripts/memory_store.py:158-177` checks
`expected_revision` while holding `memory_store_lock`, increments the revision,
and persists through `_write_unlocked`. Its durability path at `131-150` copies
the prior file to a backup, flushes and fsyncs the temporary file, then replaces
the canonical path. `scripts/state_store.py:500-526` has the corresponding
backup/flush/fsync path, while `scripts/state_store.py:598-657` performs a
per-project revision check inside its file lock.

### 2.2 Backup reads — deferred W-08B evidence

`scripts/memory_backup.py:207-224` reads canonical memory, registry, settings and
state sequentially, then validates the combination. The function does not hold a
coordinated lock or retry against a source revision while collecting the bytes.
`scripts/memory_backup.py:227-250` records canonical revision and state metadata,
but no registry revision or source snapshot token. `create_backup` at
`365-382` therefore verifies a valid combination, not that all bytes came from one
instant.

Existing backup callers/tests include `tests/test_memory_backup.py:105-249` and
`tests/test_pre13_runtime.py:143-152`. W-08B must preserve old archive reads and
the existing refusal to overwrite an archive.

### 2.3 State reference TOCTOU — deferred W-08C evidence

`scripts/state_store.py:993-1007` loads `MemoryStore` and validates a memory id,
scope and project id. `add_memory_reference` at `1009-1036` then calls
`StateService._mutate`. The state transaction acquires the state file lock and
checks the state revision at `598-657`, but the earlier memory read is not bound
to that transaction. A memory lifecycle/scope mutation can occur between the
validation and state commit.

The current cross-project rejection is covered by
`tests/test_state_failure_injection.py:200-228`; it does not inject a memory
mutation between validation and commit. W-08C must define whether status changes
remain valid historical references and must reject dangling, deleted or
wrong-project targets according to that explicit policy.

### 2.4 API lifecycle bypass — deferred W-08D evidence

`scripts/search-api.py:109-113` accepts `MemoryUpdate.status` as an arbitrary
string. `update_memory` at `615-671` validates content safety, then directly
assigns the supplied status at `631-636` and calls `MemoryStore.transact` at
`647-650`. `delete_memory` at `673-713` directly assigns `status = "deleted"`
inside another raw transaction at `679-688`.

The typed truth surface defines actions at `scripts/memory_truth.py:40-48`,
statuses at `51-63`, and validates expected revision before commit at
`303-344`; its mutation/effect handling is at `345-428`. The API currently does
not require that typed lifecycle path. Existing API behavior is exercised at
`tests/test_search_api.py:335-401`, including content safety, stale revision,
soft-delete and not-found behavior. W-08D must preserve response compatibility
while making lifecycle transitions typed and CAS-bound.

## 3. Caller and authority inventory

The following are real imports/calls found in the current tree; comments and
inventory prose were excluded.

| Surface | Production callers | Test/evaluation callers | Authority path |
|---|---|---|---|
| `ProjectRegistry` | `brain_eleven/runtime/install.py:129-138`, `brain_eleven/runtime/worker.py:96,145`, `brain_eleven/memory/capture.py:64-75`, `scripts/state_store.py:684`, `scripts/state_resolver.py:95`, `context_router/adapters.py:161`, `scripts/memory_scope.py:58,83`, `brain_eleven/runtime/task.py:176`, `evals/*` harnesses | `tests/test_capture_event.py:35,163-165`, `tests/test_phase14_scope.py:70-209`, `tests/test_remember.py:108-213`, `tests/test_state_*`, `tests/test_task_model.py:132-198`, `tests/test_pre12_package_boundaries.py:20-21`, plus context/runtime tests | `brain_eleven.projects.registry` and historical `scripts.project_registry` identity must remain equal. |
| `create_backup` / `restore_backup` | operational backup CLI path in `scripts/memory_backup.py` | `tests/test_memory_backup.py:105-249`, `tests/test_pre13_runtime.py:143-152` | Reads all authority files; no coordinated snapshot today. |
| `add_memory_reference` | `scripts/state.py:244`, `scripts/state_boundary.py:135`, `scripts/state_resolver.py` through `StateService` | `evals/task_state_eval.py:285`, `tests/test_state_failure_injection.py:200-228`, state boundary/transition suites | StateStore CAS plus an unbound MemoryStore pre-read. |
| API memory update/delete | `scripts/search-api.py:615-713` | `tests/test_search_api.py:335-401` | Direct MemoryStore transaction; typed lifecycle bypass remains open. |

The first W-08A implementation must not alter any caller signature or add a new
canonical authority. All callers must continue to resolve the same package and
legacy objects.

## 4. W-08A bounded contract — ProjectRegistry durability/CAS parity

### Objective

Give the vault-local project registry the minimum revisioned, durable write
contract needed to reject stale logical updates and survive the same write-path
failure modes already covered for memory and state.

### In scope

- `scripts/project_registry.py` implementation and its
  `brain_eleven.projects.registry` identity-preserving surface.
- A backward-compatible, versioned registry representation or explicit read
  normalization for existing schema-1 files.
- Monotonic registry revision, stale-write rejection, backup creation and
  flush/fsync-before-replace behavior.
- Focused registry tests and package evidence.

### Required invariants

1. Existing project ids, normalized roots, labels, status and
   `proactive_capture` values survive load/write/migration byte-for-byte in
   meaning. Relocation keeps the opaque project id.
2. A successful registry mutation increases the registry revision exactly once.
   A rejected stale mutation does not change bytes, revision or `updated_at`.
3. The revision comparison occurs inside the existing `file_lock` after loading
   the latest registry. No caller can silently overwrite a newer registry.
4. The temporary file is flushed and fsynced before replace. The previous
   registry is copied to the fixed backup path before replacement, with failure
   surfaced rather than reported as success.
5. Corrupt, unsupported, incomplete or negative-revision registries remain
   explicit `ProjectRegistryError` failures; corruption is never treated as an
   empty registry.
6. Legacy schema-1 registries remain readable through an explicit compatibility
   path. No project root is inserted into memory records, and no registry write
   becomes a MemoryStore or StateStore write.
7. `brain_eleven.projects.registry.ProjectRegistry`,
   `scripts.project_registry.ProjectRegistry` and any historical bare-module alias
   remain the same class object.
8. Existing callers that do not supply an expected revision retain a documented
   compatibility behavior. New callers may opt into CAS; the implementation must
   not guess a stale caller's intent.

### Required focused evidence

- Fresh empty registry receives a revision and passes validation.
- Legacy schema-1 load preserves all project records and an explicit upgrade
  write produces the chosen current representation.
- Two writers from one starting revision: exactly one succeeds, one receives a
  typed stale/CAS error, and the final project set contains both no lost update
  and no silent overwrite according to the chosen API contract.
- `register`, `relocate`, `rename`, status and proactive-capture mutations each
  increment revision once and preserve existing fail-closed rules.
- `os.fsync`/replace fault injection proves a failed durability step does not
  return success and leaves the prior readable state or a visible recovery error.
- Backup is created before replacement, is valid JSON, and restores the prior
  registry identity/status/opt-in data.
- Corrupt main file and corrupt backup produce explicit errors.
- Package/legacy/bare import identity and direct CLI parity remain intact.

### Compatibility and rollback

The first write must be staged behind an explicit schema/revision compatibility
decision. Old schema-1 files are read-only compatible until a normal mutation
performs a validated upgrade. A backup is retained before every replacement.
Rollback is a registry-only restore of the verified backup while holding the same
lock; it must use expected revision and refuse a stale rollback. No bulk vault
restore, memory rewrite or state rewrite is part of W-08A.

## 5. Deferred bounded slices

These are contracts to be written and reviewed separately after W-08A. Their
presence here does not authorize their implementation.

### W-08B — Coordinated backup snapshot (P1)

Acquire a deterministic cross-authority snapshot boundary for the four files read
by `memory_backup._read_source_payloads`, or use a bounded read/validate/retry
protocol that proves the same source revisions/hashes. Add registry revision and
source snapshot metadata to new manifests while retaining old archive reads.
Fault tests must mutate each authority between reads and prove the archive either
contains one coherent snapshot or fails visibly; it must never publish a
cross-revision archive as verified.

### W-08C — State reference commit guard (P1)

Bind `add_memory_reference` to a memory identity/scope snapshot and a deterministic
concurrency guard. A memory mutation between validation and commit must abort or
retry without publishing a dangling/wrong-project reference. Preserve StateStore
per-project CAS and audit events. Tests must inject lifecycle/scope changes,
cross-project targets, deleted targets and stale state revisions.

### W-08D — Typed API lifecycle updates (P1)

Replace arbitrary status assignment in `PUT /memories/{id}` and raw soft-delete
mutation with a typed lifecycle/truth operation that preserves content safety,
project scope, expected-revision 409 behavior, response compatibility and graph
effect visibility. Invalid transitions must fail before canonical mutation.

## 6. Recommended order and risk

| Order | Package | Risk | Reason |
|---:|---|---|---|
| 1 | W-08A registry durability/CAS | P1, medium | Smallest authority-local change; establishes revision/backup semantics needed by backup manifests. |
| 2 | W-08B coordinated backup | P1, high | Cross-authority locking/snapshot behavior depends on stable source revisions. |
| 3 | W-08C state reference guard | P1, high | Cross-authority TOCTOU and lock-order risk; requires explicit reference lifecycle policy. |
| 4 | W-08D API typed lifecycle | P1, medium-high | Public behavior and status compatibility must be preserved after truth/lifecycle contract is fixed. |

Each package follows: read-only audit, bounded contract, implementation, focused
fault tests, full regression, independent read-only review, then SHIP/FIX-FIRST/
RETHINK. A package cannot be marked SHIP by its implementer.

## 7. Shared verification and safety gates

Every W-08 package must bind evidence to its exact commit and run:

- focused authority/fault-injection tests;
- relevant existing suites without changing their assertions;
- `pytest tests -q`;
- critical `flake8` (`E9,F63,F7,F82`) on changed files;
- `python -m compileall` on changed Python surfaces;
- `git diff --check`;
- independent review of diff, caller scope, rollback and failure evidence.

Hard gates are: no silent overwrite, no lost successful mutation, no wrong-project
identity, no corruption-as-empty behavior, no direct file writes outside the
authority boundary, and no change to Phase 20/V2 state. A failing holdout or
existing intelligence-quality metric remains visible and is not tuned in W-08.

## 8. Explicit out of scope

- Phase 20 unlock or any Knowledge Engine work.
- V2 promotion, retrieval ranking, embeddings, context compilation or task-aware
  retrieval.
- Capture hooks, queue/worker extraction and transcript provenance.
- Graph projection/rebuild behavior except preserving existing visible errors.
- `MemoryStore`, `StateStore` or `ProjectRegistry` replacement with a new
  authority; W-08A hardens the existing registry boundary only.
- Automatic markdown reminders, Daily/Threads/Last Session maintenance.
- API authentication/authorization; that is a separate security package.
- Changing evaluation labels, holdout data, thresholds or baseline snapshots.

## 9. Package report template

```text
PACKAGE: W-08A
REVISION: <exact SHA>
OBJECTIVE: ProjectRegistry durability and CAS parity
FILES CHANGED: <implementation/tests/docs>
ROOT CAUSES ADDRESSED: <revision, fsync, backup, stale writer>
TESTS ADDED: <focused/fault tests>
TESTS EXECUTED: <exact commands and results>
QUALITY METRICS BEFORE: <evidence>
QUALITY METRICS AFTER: <evidence>
SAFETY METRICS: <silent overwrite, corruption, identity>
KNOWN LIMITATIONS: <compatibility and deferred slices>
OPEN FAILURES: <none or exact failures>
INDEPENDENT REVIEW: REVIEW PENDING / SHIP / FIX-FIRST / RETHINK
SCORE BEFORE: <x/10>
SCORE AFTER: <x/10>
VERDICT: REVIEW PENDING
```

**Plan status: REVIEW PENDING — implementation başlamadı.**
