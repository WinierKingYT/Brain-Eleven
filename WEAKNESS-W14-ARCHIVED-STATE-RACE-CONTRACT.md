# W-14 Archived Project State-Mutation Race Contract

**Status:** REVIEW PENDING — implementation is not authorized by this document  
**Finding:** an archived project can pass the activity check and then receive a
state mutation after the registry status changes.  
**Priority:** P1 lifecycle/scope safety  
**Contract revision:** \`8ef69d7\` (W-13 close baseline)

## Evidence

\`scripts/state_store.py::StateService._mutate()\` currently calls
\`_require_active_project(project_id)\` before entering
\`StateStore._transact_project()\`. The registry check and the state write use
different locks. A fault-injected run paused immediately after the active check,
archived the project through \`ProjectRegistry.set_status()\`, and then released
the mutation. The mutation succeeded, leaving an archived project at state
revision 2 with a new requirement. Existing tests cover sequential archived
rejection but not this linearization window.

This violates the invariant that an archived project is read-only.

## Bounded objective

Make the active-status check and the subsequent state transaction share one
lifecycle serialization boundary with registry status changes. The linearization
rule is:

- a state mutation that acquires the boundary before archive may complete before
  the archive;
- an archive that acquires it first makes the later state mutation fail closed;
- no mutation may pass an unlocked pre-check and then write after archive.

## Allowed scope

- \`scripts/state_store.py\`: StateService initialization and typed mutation
  entry points (\`init_project\` and \`_mutate\`) may acquire the existing
  \`file_lock\` primitive on the ProjectRegistry path around the active check and
  state transaction.
- Focused race tests and package evidence/report documents.
- A small shared-lock helper is allowed only if it uses the existing
  \`brain_eleven.infrastructure.locking.file_lock\` surface and does not create
  a new authority or persistence format.

\`ProjectRegistry\`, \`StateStore\`, \`MemoryStore\`, StateBoundary routing,
retrieval, V2, Phase 20, and unrelated registry operations are out of scope.
No canonical record schema changes are authorized.

## Required semantics

1. **Active mutation:** an active project's existing typed state operations keep
   their current results, revisions, CAS checks, receipts, and audit events.
2. **Archive first:** if archive commits before a state mutation enters the
   lifecycle boundary, \`StateProjectArchived\` is raised and the state
   revision/data remain unchanged.
3. **Mutation first:** if the state mutation owns the boundary first, it may
   commit exactly once; the subsequent archive then commits normally. The final
   state is archived with the prior mutation retained.
4. **No partial effects:** a rejected archived mutation must not increment the
   state revision, append an event, alter operation receipts, or write MemoryStore.
5. **Lock failure:** existing lock timeout/error mapping remains visible; no
   fail-open state write is permitted.
6. **All typed writes:** \`init_project\` and every StateService mutation using
   \`_mutate\` share the boundary. Read-only StateStore calls need no new lock.
7. **Lock ordering:** the implementation must document one order and avoid a
   registry→state / state→registry cycle. The preferred order is the existing
   registry sidecar lock, then the state-store lock.
8. **Compatibility:** project ID, expected-revision, operation receipt and
   idempotent replay behavior remain byte/field compatible.

## Test and evidence plan

### Baseline and reproduction

- Record exact \`git rev-parse HEAD\`.
- Re-run the fault injection that pauses after the active check, archives the
  project, and releases the writer. Capture the pre-fix successful mutation as
  the red baseline.
- Capture sequential archived rejection and normal active mutation results.

### Focused tests

Add tests without weakening existing coverage:

- archive-vs-mutation race: archive-first produces
  \`PROJECT_ARCHIVED\`/equivalent typed failure, no state revision or event
  change;
- mutation-first serializes and commits once, then archive succeeds;
- injected lock timeout is surfaced and causes no write;
- \`init_project\` and representative milestone/objective/requirement operations
  use the same lifecycle boundary;
- operation receipt replay remains idempotent and does not bypass the archive
  check;
- wrong project, stale revision, dry-run and sequential archived tests remain
  unchanged.

### Verification gates

1. **Boundary proof:** AST/source review shows the active check and state
   transaction are inside the same existing lock; no direct file-write path was
   added.
2. **Race proof:** deterministic event-controlled test demonstrates both
   archive-first and mutation-first outcomes.
3. **Parity/safety:** existing state-boundary, state-store, registry, migration,
   and runtime tests pass unchanged; rejected mutations have zero canonical
   effects.
4. **Full verification:** full \`pytest tests -q\`, critical flake8
   (\`E9,F63,F7,F82\`), compileall, and \`git diff --check\` at one exact
   revision.
5. **Independent review:** a read-only reviewer checks lock ordering,
   concurrency evidence, scope, and exact revision, then returns only
   \`SHIP\`, \`FIX-FIRST\`, or \`RETHINK\`.

## Explicit non-goals

- No redesign of ProjectRegistry or StateStore schema.
- No new global lifecycle manager.
- No automatic repair of state already written after archive.
- No capture/retrieval, task/context, reminder, V2 or Phase 20 work.

## Package report template

\`\`\`text
PACKAGE: W-14
REVISION: <exact implementation SHA>
OBJECTIVE: Serialize active-status validation with registry archive mutations.
FILES CHANGED: ...
ROOT CAUSE ADDRESSED: ...
TESTS ADDED: ...
TESTS EXECUTED: ...
QUALITY METRICS BEFORE: ...
QUALITY METRICS AFTER: ...
SAFETY METRICS: archive-first rejection, mutation-first commit, zero rejected effects
KNOWN LIMITATIONS: ...
OPEN FAILURES: ...
INDEPENDENT REVIEW: SHIP / FIX-FIRST / RETHINK
SCORE BEFORE: ...
SCORE AFTER: ...
VERDICT: REVIEW PENDING
\`\`\`

**Implementation authorization:** not granted until independent contract review.
Phase 20 remains \`FROZEN / LOCKED\`; V2 remains \`SHADOW\`.

