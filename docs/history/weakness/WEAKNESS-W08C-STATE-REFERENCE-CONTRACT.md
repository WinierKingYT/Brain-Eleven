# W-08C State Reference Commit Guard Contract

**Status:** BOUNDED CONTRACT / PLAN ONLY — REVIEW PENDING  
**Revision audited:** `8932018c9d72d0609cf3f4d2316574cef8243066`  
**Program:** Engineering Weak-Point Improvement Goal  
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW  
**Implementation authorization:** Not granted by this document.

This document defines the bounded W-08C package. It records the current
state/memory reference race and the smallest guard that can make the reference
commit linearizable without creating a new persistence authority. It does not
authorize production or test implementation. W-08C must receive an independent
read-only review before implementation begins, and the implementer must leave
the package `REVIEW PENDING`.

## 1. Objective and exact scope

`StateService.add_memory_reference()` currently validates a memory record before
the state transaction obtains the project-state lock. A memory lifecycle or
scope writer can therefore change the validated record after validation and
before the state reference is committed. The resulting state can contain a
dangling or wrong-project reference even though both individual operations used
their normal authority boundaries.

W-08C will make the following two existing write paths use one bounded memory
reference guard:

1. `StateService.add_memory_reference()` and its CLI command
   `add-memory-reference`;
2. `StateService.add_blocker(..., memory_ref=...)`, because it calls the same
   validation helper and otherwise would retain the same race.

The package may change the existing implementation in `scripts/state_store.py`
and the narrow read-side classification in `scripts/state_resolver.py`. It may
add focused W-08C tests and package evidence. The stable package bridge
`brain_eleven/state/store.py` remains an identity-preserving export of the
legacy implementation; no second StateStore authority is introduced.

The package must not change the StateStore schema version, the project-state
JSON shape, the existing audit-event shape, or the public argument names. In
particular, `projects.<id>.references` remains exactly
`{"memory_ids": [...]}` and a blocker continues to carry only its existing
`memory_ref` string. The memory revision used by the guard is an in-process
concurrency token; it is not added to old state records or audit events.

W-08C does not include:

- a replacement `MemoryStore`, `StateStore` or `ProjectRegistry`;
- a new multi-file persistence authority or a vault-wide lock;
- API lifecycle typing (`W-08D`), search ranking, graph rebuild policy or
  capture behavior;
- automatic registration, project relocation, or registry status changes;
- Phase 20 unlock, V2 promotion, retrieval, extraction or context work;
- a migration of `scripts/state_store.py` into `brain_eleven/state/store.py`.

## 2. Read-only reality audit

### 2.1 Current validation-to-commit sequence

The current call sequence is:

```text
StateService.add_memory_reference()
  -> _validate_memory_reference()                 [state_store.py:993-1007]
       -> MemoryStore.load()                     [996]
       -> find memory_id, check scope/project     [999-1007]
  -> StateService._mutate()                      [1027-1035]
       -> _require_active_project()               [713-733, 724]
       -> StateStore._transact_project()          [725-732]
            -> file_lock(project-state.json)     [614]
            -> read latest state                  [615]
            -> check expected state revision      [619-632]
            -> mutate references and write        [634-657]
```

The validation read and the state commit are separate operations. There is no
memory revision captured at `scripts/state_store.py:993-1007`, and no second
memory read or lock at `scripts/state_store.py:1009-1036`. The existing state
CAS protects only the project-state revision; it cannot detect a memory change.

The same helper is called before the blocker mutation at
`scripts/state_store.py:1047-1079`, specifically `:1050-1051`. This path must
not be left unguarded while `add_memory_reference` is fixed.

### 2.2 Canonical authority and persistence boundaries

`MemoryStore` has the required lock/reload/revision boundary:

- `scripts/memory_store.py:63-129` defines the canonical path, normalization
  and read/revision surface;
- `scripts/memory_store.py:158-177` acquires `memory_store_lock`, reloads the
  latest document, optionally checks `expected_revision`, increments revision
  and atomically persists it;
- `scripts/memory_store.py:131-156` performs backup, flush, fsync and replace.

`StateStore` has a separate lock and revision boundary:

- `scripts/state_store.py:463-520` defines the state path and durable write;
- `scripts/state_store.py:598-657` acquires `file_lock(self.path)`, reloads
  the latest project, checks its expected revision at `:631-632`, appends one
  audit event at `:641-649`, and persists at `:654`;
- `scripts/state_store.py:79-88` defines the existing typed
  `StateStoreConflict`.

The lock files are distinct. `scripts/memory_store_lock.py:15-61` locks the
`validated-memory.json.lock` sidecar and `:64-73` derives that path from the
vault. `StateStore` passes `project-state.json` to the same `file_lock`, so its
sidecar is `project-state.json.lock`.

The repository already has one cross-authority path with an explicit order:
`brain_eleven/runtime/migration.py:12-27` acquires memory first and state
second. This is evidence for the order selected in Section 3. It is not a
permission to broaden W-08C into a general migration lock.

### 2.3 Exact write callers and compatibility surface

The current direct and indirect callers found in the exact revision are:

| Surface | Evidence | Behavior |
|---|---|---|
| State CLI | `scripts/state.py:134-137` defines the command; `:243-249` calls `add_memory_reference` | Existing arguments and JSON/error behavior must remain compatible. |
| Evaluation harness | `evals/task_state_eval.py:278-287` creates a global memory and calls the method | Public/holdout state cases must remain unchanged; the evaluator file and labels are frozen. |
| Fault test | `tests/test_state_failure_injection.py:200-228` covers AI provenance and wrong-project rejection | Existing assertions stay unchanged. |
| CLI test | `tests/test_state_cli.py:79-99` covers a valid global reference; `:102-112` covers stale state CAS | Existing CLI result and conflict behavior stay unchanged. |
| Blocker CLI | `scripts/state.py:108-114` defines `--memory-ref`; `:209-218` passes it to `add_blocker` | The shared guard must protect this path too. |
| Historical blocker callers | `evals/authority_evaluation.py:101-105`, `evals/compiler_v2_evaluation.py:68-70`, and `tests/test_authority_resolver.py:160-169` pass a superseded memory | Superseded historical references remain allowed and continue to support authority/context tests. |
| Resolver | `scripts/state_resolver.py:100-135` reads references and classifies valid/dangling/wrong-project | It performs no write and must preserve the result shape. |
| Package compatibility | `brain_eleven/state/store.py:10-40` re-exports `StateService`, `StateStore` and errors | Identity and import compatibility must remain intact. |

There are only two direct `add_memory_reference` calls outside the
implementation (`scripts/state.py:244` and `evals/task_state_eval.py:285`),
plus the focused test call at `tests/test_state_failure_injection.py:221`.
The broader `memory_ref` surface includes the blocker callers listed above.
No caller may be forced to provide a memory revision or a new snapshot field.

### 2.4 Current scope and lifecycle semantics

The current validator at `scripts/state_store.py:993-1007` accepts a record
when:

- the `memory_id` exists in `validated_memory`;
- raw `scope == "global"`; or
- raw `scope == "project"` and raw `project_id == project_id`.

It rejects missing records as `DANGLING_MEMORY_REFERENCE` and a mismatched
project as `WRONG_PROJECT_MEMORY_REFERENCE`. It currently does not inspect
`status` or `is_approved`. The `validated_memory` bucket is already the
canonical approved-memory bucket produced by the validator
(`scripts/memory-validator.py:757-777`), and W-08C must not add a second
approval authority.

The lifecycle data proves that `active`, `resolved` and `superseded` records
are real canonical states: the fixtures contain them at
`evals/fixtures/phase15-contract.json:26-32`, and historical superseded
references are exercised at `tests/test_authority_resolver.py:160-175`.
The API can soft-delete a record through a normal MemoryStore transaction at
`scripts/search-api.py:673-699`; status updates and scope recomputation are at
`:615-650` and are part of the later W-08D/API surface.

The state schema intentionally stores only IDs. `scripts/state_store.py:315-360`
requires the exact project-state keys, requires `references` to contain only
`memory_ids` at `:345-360`, and `_event` requires its exact audit fields at
`:364-370`. Adding a memory revision or content digest to those objects in this
package would be a schema migration and is therefore prohibited.

## 3. Bounded design decision

### 3.1 Linearization guard: memory lock, then state transaction

W-08C selects a **held canonical memory lock** as the concurrency guard. The
reference operation must:

1. acquire `memory_store_lock(vault)`;
2. read the latest memory document with the already-held-lock read path;
3. validate the target and capture an ephemeral snapshot token;
4. while still holding the memory lock, call the existing StateStore project
   transaction, which acquires `project-state.json.lock`, checks
   `expected_revision`, appends the existing event, and writes the state;
5. release the state lock and then the memory lock.

This creates a linearization point: a normal MemoryStore writer cannot mutate
the target between validation and state commit. A writer that acquired the
memory lock first is observed by validation; a writer that arrives second waits
until the state reference commit is complete. No state reference is published
while a concurrent normal memory writer can change the validated snapshot.

The implementation must not call `MemoryStore.load()` outside the guard and
then rely on a revision comparison later. A check followed by an unlocked
commit is still a TOCTOU race. The already-held-lock read must not reacquire
the same sidecar lock.

### 3.2 Ephemeral reference snapshot

The validator must capture only bounded, non-content metadata:

```text
memory_revision : non-negative integer from the canonical document
memory_id       : validated opaque ID
scope           : "global" or "project"
project_id      : empty for global, exact canonical ID for project scope
status          : normalized lifecycle status
```

The snapshot is used to prove that the state operation was validated against a
specific memory revision and scope. It is not persisted in the state document,
not placed in an audit event, and not returned as a new public field. Content,
project roots, prompts, secrets and full memory records must never enter the
snapshot or a new error/log field. The memory revision is a guard token, not a
cross-authority revision that can be compared numerically to the state revision.

The implementation may perform one final in-lock comparison of the snapshot
against the same canonical document before invoking the state mutator. If that
comparison fails, it must raise a typed reference conflict and perform no state
write. Under the required lock this is defensive evidence, not a substitute for
the lock.

### 3.3 Lock ordering and deadlock rule

The only permitted nested order for W-08C is:

```text
memory_store_lock(vault)
    -> StateStore._transact_project()
         -> file_lock(StateStore.path)
```

The state lock must never be held while acquiring the memory lock. No new
reverse-order path may be added to `MemoryStore`, `StateStore`,
`ProjectRegistry`, the installer, W-08B backup reader or runtime migration.
State-only writers remain state-only, and memory-only writers remain
memory-only. The implementation must use the existing lock implementations;
it must not create a second lock name or a process-local lock that native
clients would not honor.

The memory lock is held only for validation plus the one state transaction. It
must not cover graph rebuilds, retrieval, network calls, CLI printing or other
unbounded work. A bounded lock timeout must be visible as a typed state
failure, with no partial state write.

### 3.4 Reference status policy

The following policy is frozen for this package:

| Memory condition at commit | Result |
|---|---|
| Missing ID / absent from `validated_memory` | reject: `DANGLING_MEMORY_REFERENCE` |
| `scope=global` | allow for any active project |
| `scope=project` with exact target project ID | allow |
| `scope=project` with another project ID | reject: `WRONG_PROJECT_MEMORY_REFERENCE` |
| `status` missing | treat as legacy `active` for compatibility |
| `status=active` | allow |
| `status=resolved` or `status=superseded` | allow as historical evidence |
| `status=deleted` | reject as deleted/dangling |
| any other explicit status | reject closed-world as invalid reference |
| `is_approved` absent or present in `validated_memory` | do not add a second approval gate |

The validator must check the current record under the held memory lock. The
read-side `StateResolver._reference_health` must preserve its existing output
shape (`valid`, `dangling`, `wrong_project`) while classifying a later deleted
or unknown-status target as `dangling`; resolved/superseded historical targets
remain `valid` when their scope still matches. A later scope change is reported
as `wrong_project` by the existing scope rule. W-08C does not roll back or
rewrite a state reference when a later W-08D lifecycle operation changes the
memory; it makes that condition visible to the resolver.

This policy deliberately separates reference existence from retrieval
eligibility. A superseded memory may remain a valid historical blocker
reference while still being excluded by ordinary active-memory retrieval.

## 4. Conflicts, retry, and typed failures

### 4.1 State revision conflict

`expected_revision` retains its current meaning. The existing
`StateStore._transact_project` check at `scripts/state_store.py:631-632` remains
the authoritative state CAS. If another state writer wins first, the operation
raises the existing `StateStoreConflict` with no memory mutation, no state
mutation and no audit event. The CLI continues to surface `STATE_CONFLICT` via
`scripts/state.py:32-43`.

There is no automatic state retry. Retrying with a newly loaded state revision
could apply a user operation to changed state without fresh caller intent. A
caller may explicitly reload state and retry the complete operation.

### 4.2 Memory guard conflict and lock timeout

The implementation must introduce one typed state-boundary error for a guard
failure, for example `StateReferenceConflict(StateReferenceError)`, with a
fixed reason from this closed set:

```text
MEMORY_REFERENCE_LOCK_TIMEOUT
MEMORY_REFERENCE_SNAPSHOT_CHANGED
```

The exception must not contain memory content, project root, prompt text or an
unbounded underlying exception. The public CLI maps it to a stable
`MEMORY_REFERENCE_CONFLICT` error code. Existing dangling and wrong-project
`StateReferenceError` behavior remains recognizable and backward compatible.

There is no hidden retry inside the same call. A lock timeout or defensive
snapshot mismatch returns before `_transact_project` can publish state. The
caller may retry the whole operation after reloading both the current state
revision and the memory reference. If the implementation chooses a bounded
single lock acquisition retry, it must have a fixed attempt/time budget and
must still return the typed error when exhausted; an unbounded retry is
forbidden.

### 4.3 Source/storage failures

`MemoryStoreCorrupt`/`MemoryStoreError` during the guarded read remain visible
as `StateReferenceError("MemoryStore is unavailable for state reference validation")`
or the existing typed corruption equivalent. `StateStoreLockTimeout`,
`StateStorePersistenceError` and `StateStoreConflict` retain their existing
types. No failure may be converted into an empty reference set or a successful
state write.

## 5. Idempotence, audit lineage and compatibility

W-08C preserves the current non-duplicating behavior rather than inventing a
new success response for replay:

- the first successful `add_memory_reference` appends one ID, increments the
  project revision once, and appends exactly one `memory_reference_added`
  event with the existing fields and `record_ids=[memory_id]`;
- a second call with a stale expected state revision raises
  `StateStoreConflict` before the mutator;
- a second call with the current revision reaches the existing duplicate-ID
  guard at `scripts/state_store.py:1020-1025`, raises `StateError`, increments
  no revision and appends no event;
- a failed memory validation, guard timeout, or memory conflict leaves both
  canonical documents and their audit/event counts unchanged;
- `add_blocker(memory_ref=...)` has the analogous one-event/one-revision
  behavior and retains its existing blocker record shape.

This is idempotence of effects: replay cannot create a second reference or a
second event. It intentionally does not turn the existing duplicate request
into a successful no-op, because that would change public error behavior and
would require a new operation-id contract. Existing operation receipts in
`StateStore._transact_project` remain untouched.

The following compatibility invariants are mandatory:

1. `StateService`, `StateStore`, `StateReferenceError` and existing exception
   identities remain identical through `brain_eleven.state` and legacy imports.
2. `StateStore` schema version and exact-key validation remain unchanged.
3. State CLI arguments, output fields, error exit code and stale-CAS behavior
   remain compatible.
4. `StateResolver` result fields and historical superseded-reference behavior
   remain compatible, except for the explicitly frozen deleted/unknown status
   classification in Section 3.4.
5. `evals/task_state_eval.py`, all corpus files, holdout labels, thresholds and
   baseline metrics remain byte-for-byte/semantically unchanged.

## 6. Authority, scope and privacy invariants

1. `MemoryStore` and `StateStore` remain the only canonical authorities for
   their respective documents. W-08C performs one canonical memory read and
   one existing state transaction; it adds no direct JSON/file write.
2. The state project must still pass the existing active-project check in
   `_mutate`; unknown or archived projects cannot gain a reference.
3. A global memory carries no project identity. A project memory must match the
   exact opaque project ID. Absolute project roots, labels used only for
   resolution, prompts and content never enter state reference metadata.
4. The guard cannot make a reference to `rejected_memory`, a missing ID, a
   deleted target or a different project. It cannot turn AI-proposed provenance
   into canonical state; existing `_source` validation remains authoritative.
5. Error strings, audit events and test evidence contain bounded codes, status,
   revisions and opaque IDs only. They must not contain raw memory content,
   project roots, secrets, transcript text or prompts. Existing opaque ID error
   fields may remain where compatibility requires them.
6. A failed guard has no StateStore backup/revision/event effect and no
   MemoryStore revision effect. A successful reference does not rebuild a graph
   or mutate MemoryStore.

## 7. Required focused evidence

New tests should be bounded in `tests/test_w08c_state_reference_guard.py` and
must use temporary vaults only. Existing assertions must not be weakened or
rewritten. The focused suite must prove:

### Reference validity and policy

- global reference succeeds and preserves existing state JSON/result shape;
- matching project reference succeeds;
- missing/dangling reference fails with no state revision/event change;
- wrong-project reference fails with no state revision/event change;
- deleted target is rejected at commit;
- resolved and superseded historical targets remain valid;
- an unknown explicit status fails closed;
- rejected-memory-only IDs cannot be referenced;
- the later resolver classifies deleted/unknown targets as dangling and scope
  drift as wrong-project.

### TOCTOU and lock ordering

- inject a memory writer between the initial reference decision and the state
  transaction using normal `MemoryStore.transact`; prove the guard serializes
  it, so the state commit is never based on a stale unlocked snapshot;
- force a bounded memory-lock timeout and prove the typed reference conflict,
  unchanged state bytes/revision/events, and no swallowed failure;
- exercise a target deletion and project/scope mutation under contention;
  prove either the reference linearizes before the later mutation or the
  operation rejects, never a wrong-project/dangling commit;
- static inspection or a deterministic hook proves the only nested order is
  memory lock before state lock and no reverse-order acquisition was added;
- exercise the `add_blocker(memory_ref=...)` path under the same race guard.

### State CAS, replay and audit

- stale `expected_revision` still raises `StateStoreConflict` and does not
  consume or hide the valid memory reference;
- duplicate same-project reference creates no second ID, revision or event;
- first success produces exactly one `memory_reference_added` event;
- a failed memory guard produces no state audit event;
- concurrent state writers retain the existing no-lost-update behavior;
- operation-receipt and package/legacy identity tests remain green.

### Privacy and regression

- sentinel content, project root, secret and prompt strings do not occur in
  new guard errors, result metadata or audit additions;
- `tests/test_state_failure_injection.py`, `tests/test_state_cli.py`,
  `tests/test_state_store.py`, `tests/test_state_resolver.py`,
  `tests/test_state_boundary.py`, `tests/test_state_transitions.py`,
  `tests/test_authority_resolver.py`, `tests/test_pre12_memory_state_caller_migration.py`
  pass without changing existing assertions;
- `evals/task_state_eval.py` and all `evals/` diffs are empty; smoke/public/
  holdout task-state reports have identical cases, metrics, invariants and
  thresholds before and after implementation.

## 8. Full verification and baseline discipline

At the exact implementation revision, run at minimum:

```text
\.venv\Scripts\python.exe -m pytest tests/test_w08c_state_reference_guard.py tests/test_state_failure_injection.py tests/test_state_cli.py tests/test_state_store.py tests/test_state_resolver.py tests/test_state_boundary.py tests/test_state_transitions.py tests/test_authority_resolver.py tests/test_pre12_memory_state_caller_migration.py -q
\.venv\Scripts\python.exe -m pytest tests -q
flake8 --select=E9,F63,F7,F82 scripts/state_store.py scripts/state_resolver.py tests/test_w08c_state_reference_guard.py
\.venv\Scripts\python.exe -m compileall -q scripts/state_store.py scripts/state_resolver.py tests/test_w08c_state_reference_guard.py
git diff --check
```

The implementation must record `git rev-parse HEAD` and every command's exit
status. Existing warnings remain visible. If the source fingerprint in
`evals/reports/baseline-v3.json` changes solely because the implementation
files changed, the official W-08 source-fingerprint-only refresh rule in
`WEAKNESS-W08-PERSISTENCE-CONSISTENCY-CONTRACT.md:311-318` applies. No metric,
case, label, threshold or state fixture may be edited to make W-08C green.

## 9. Expected change boundary and size

Expected production diff: approximately **70–150 lines** in
`scripts/state_store.py`, plus **10–35 lines** in `scripts/state_resolver.py`
if the deleted/unknown read-side policy needs an explicit branch. A focused
test file is expected to be approximately **180–300 lines**, depending on the
thread/lock fault harness. No change is expected in `MemoryStore`,
`ProjectRegistry`, `brain_eleven/state/store.py`, `evals/`, capture, retrieval,
or Phase 20 files.

If implementation requires a StateStore schema bump, persisted per-reference
metadata, a new authority, a reverse lock order, a direct JSON write, or a
change to evaluator labels/holdout data, it has exceeded this contract and must
stop with `RETHINK`; it must not be solved by widening W-08C silently.

## 10. Exit gate and independent review

W-08C remains `REVIEW PENDING` until every gate passes:

- exact-head focused policy, TOCTOU, lock, stale-CAS, replay and privacy tests;
- no dangling/wrong-project/deleted reference can be committed by the guarded
  paths;
- historical resolved/superseded references and existing CLI behavior remain;
- full regression, critical flake8, compile/import sanity and diff check pass;
- no StateStore schema/event compatibility break and no evaluator/holdout diff;
- no raw content, root path, secret or prompt leakage in new errors/evidence;
- independent reviewer examines the diff, lock order, caller scope, policy,
  failure evidence and baseline discipline;
- reviewer verdict is exactly `SHIP`, `FIX-FIRST` or `RETHINK`.

The implementer may not mark W-08C `SHIP`. Any failed lock, race, policy,
compatibility, privacy or baseline gate blocks W-08D and leaves this package
open.

## 11. Package report template

```text
PACKAGE: W-08C
REVISION: <exact SHA>
OBJECTIVE: Linearizable StateStore memory-reference commit
FILES CHANGED: <implementation/tests/docs>
ROOT CAUSES ADDRESSED: <validation-to-commit TOCTOU, lifecycle/scope race>
TESTS ADDED: <focused race/CAS/status/replay/privacy tests>
TESTS EXECUTED: <focused/full/static commands and exact results>
QUALITY METRICS BEFORE: <state/reference baseline>
QUALITY METRICS AFTER: <state/reference evidence>
SAFETY METRICS: <dangling/deleted/wrong-project/leakage results>
KNOWN LIMITATIONS: <later lifecycle mutation visibility, deferred W-08D>
OPEN FAILURES: <none or exact bounded failures>
INDEPENDENT REVIEW: <SHIP / FIX-FIRST / RETHINK and evidence revision>
SCORE BEFORE: <0-10>
SCORE AFTER: <0-10 or pending independent review>
VERDICT: REVIEW PENDING
```

## 12. Deferred work

W-08D remains responsible for API lifecycle transitions that currently assign
arbitrary status strings in `scripts/search-api.py:615-713`. It may need to
coordinate deletion/scope changes with existing state references, but it must
use a separate reviewed contract. W-08C does not silently solve that API
problem or promote Phase 20.

**Plan status: REVIEW PENDING — implementation başlamadı.**
