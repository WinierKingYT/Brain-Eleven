# W-08C Independent Acceptance Review

PACKAGE: W-08C  
REVIEW REVISION: `ecee32bfb00a1900f0bb79219df65be23e05745b`  
IMPLEMENTATION REVISION: `02548c503275217854a60a08be999fcbbadff21f`  
CONTRACT: `7f175b3`  
REVIEWER: independent read-only review  
PHASE 20: FROZEN / LOCKED  
V2: SHADOW

## Review scope

This review independently checked the accepted W-08C contract, the complete
implementation diff from the contract review revision, the focused evidence,
the package report, the state and CLI compatibility surfaces, lock ordering,
TOCTOU behavior, scope/lifecycle policy, privacy boundaries, and the frozen
task-state evaluation inputs. The review did not modify production code or
evaluation cases.

## Evidence

- Focused W-08C and required state/authority suite: **90 passed**.
- Full suite: **1037 passed**, with the two existing dependency deprecation
  warnings.
- `tests/test_evaluation_baseline_snapshot.py`: **5 passed**.
- Critical flake8 selection `E9,F63,F7,F82`: **0**.
- `compileall`: **0**.
- `git diff --check`: **0**.
- The implementation diff does not modify `MemoryStore`, `ProjectRegistry`,
  state schema, audit-event shape, evaluator code, corpus/holdout labels, or
  Phase 20 files.
- The task-state smoke/public/holdout report hashes recorded in the package
  report remain byte-identical to their frozen before reports.

## Contract checks

### Authority and lock order

`StateService.add_memory_reference()` and
`add_blocker(..., memory_ref=...)` acquire the canonical
`memory_store_lock` before entering the existing StateStore transaction.
The memory lock remains held through state validation and commit, and the
state lock is acquired only inside that scope. No reverse-order lock path,
new persistence authority, direct canonical file write, or hidden retry was
introduced.

### Snapshot and TOCTOU behavior

The guard reads the canonical document through `_read_unlocked()` while the
canonical memory lock is held, validates scope and lifecycle, and retains only
bounded revision/id/scope/project/status metadata. The defensive in-lock
comparison rejects a changed or deleted snapshot with the closed typed conflict
reason. The focused writer-serialization test independently demonstrated that
a normal MemoryStore writer waits until the state reference transaction
finishes.

### CAS, replay, and failure behavior

The existing StateStore project revision CAS remains the commit authority.
Stale state revisions, duplicate references, memory lock timeouts, corrupt
memory reads, and state lock timeouts were independently exercised without
partial state or audit effects. The new `StateReferenceConflict` has a closed
reason set and the CLI maps it to `MEMORY_REFERENCE_CONFLICT`; the package
surface re-exports the same exception identity.

### Scope and lifecycle

Global references remain valid for active projects; project references require
the exact opaque project ID. Missing, deleted, unknown-status, and rejected
bucket records are rejected. Legacy missing status, resolved status, and
superseded historical references retain their specified behavior. Resolver
classification preserves the existing result shape while reporting deleted
and unknown-status targets as dangling.

### Privacy and schema

The ephemeral guard snapshot is not persisted in state or audit events. The
focused privacy test confirms memory content, prompt/root sentinels, and the
guard revision metadata do not enter the state document. Existing state JSON
and event fields remain unchanged.

### Compatibility and evaluation boundary

`StateService`, `StateStore`, existing exceptions, and the new conflict are
identity-preserving through `brain_eleven.state` and the legacy surfaces.
The frozen task-state evaluator and its reports are unchanged. No retrieval,
capture, lifecycle API, V2, or Phase 20 work was mixed into this package.

## Findings

No P0, P1, or P2 blocker was found. The remaining lifecycle/API coordination
work is explicitly W-08D and is outside this bounded package; it does not
invalidate the W-08C state-reference guard.

## Verdict

**SHIP**

