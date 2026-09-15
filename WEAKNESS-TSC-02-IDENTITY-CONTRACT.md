# TSC-02 — Project Identity and Registry-Lineage Contract

**Status:** CONTRACT REVISION / IMPLEMENTATION NOT AUTHORIZED  
**Program:** Engineering Weak-Point Improvement Goal  
**Baseline revision:** `5b1d1c7`  
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW

## 1. Problem and objective

The read-only Phase 16 hand-off carries a project ID and state revision, but
does not carry enough registry lineage to prove that the context was composed
for the project currently occupying the caller's root. `TaskStateContext` is a
two-field dataclass (`scripts/task_state_context.py:24-29`), and
`TaskStateComposer.compose` resolves the task and state in separate calls
(`scripts/task_state_context.py:69-72`). Router validation currently checks
project ID and state status/revision only (`context_router/router.py:43-71`),
while Authority validation has the same project/status check without registry
lineage (`authority/resolver.py:60-70`).

The weakness is reproducible and is a scope-safety failure, not merely stale
metadata. A context composed for `project-p` at an old root was retained; the
registry then relocated `project-p` and registered the old root as `project-q`.
The old context still routed as `DEGRADED` and carried a `project-p` state
candidate while the current root resolved to `project-q`. Native
`brain_eleven/runtime/context.py:230` has a later root-aware guard, but Router,
Authority and serialized/direct consumers remain exposed.

The objective of TSC-02 is to make a TaskStateContext self-describing enough
to reject stale root/project lineage before any project-scoped candidate is
delivered, while preserving stable project IDs across legitimate relocation.
The fix must fail closed on root reuse and registry races without writing
canonical memory, state or registry data.

## 2. Bounded implementation surface

The implementation package may change only the following production surfaces
and their focused tests:

- `scripts/task_state_context.py` — add the content-free lineage envelope and
  compose-time registry snapshot/revalidation. This is an identity fix, not
  the separate IG-07 Slice 2F package inversion; the legacy module remains the
  runtime implementation authority for this package.
- `brain_eleven/projects/identity.py` (new, read-only utility) — one shared,
  domain-separated digest function for a normalized registry root. The digest
  is opaque and must never expose or persist the raw path. It must not mutate
  `ProjectRegistry` or change registry persistence.
- `context_router/router.py` — validate context lineage against the current
  registry record before routing; stale or reused roots return a bounded
  `STALE_INPUT`/`SCOPE_ERROR` result and deliver no project candidates.
- `authority/resolver.py` — repeat the lineage check independently before
  authority evidence is accepted. Authority must not trust Router metadata
  alone.
- `authority/serialization.py` — decode/encode the versioned lineage fields
  with strict shape checks. Raw roots, prompts, memory content and exception
  text are forbidden.
- `tests/` focused identity/lineage, router, authority and serialization
  tests, plus a package evidence report and independent-review document.

`brain_eleven/runtime/context.py` may be changed only if a focused test proves
that the existing native root guard cannot consume the bounded lineage result
without a compatibility correction. Such a change must be separately listed
and remain a translation/guard change; no native retrieval or compiler redesign
is permitted. If the package needs broader native behavior, stop with
`RETHINK` and open a new contract.

The following are explicitly out of scope: `MemoryStore`, `StateStore`,
`ProjectRegistry` write/persistence implementation, capture/remember,
retrieval/ranking, V2 promotion, `task_state_context.py` package inversion,
`authority/serialization.py`'s unrelated nested-state strictness (TSC-03),
W-07B native trust/latency/dogfood, and Phase 20.

## 3. Identity and lineage contract

### 3.1 Opaque root identity

The context must carry a `root_identity` value for a resolved project-scoped
context. It is absent only for an explicitly unresolved or global-only context,
whose route contract forbids project candidates. Such a context must carry an
explicit `lineage.status` (`unresolved` or `global`) so absence cannot be
mistaken for an old, unverified project context. A resolved project-scoped
context's `root_identity` value is:

- computed from `normalize_registry_root(project_root)` using a documented,
  deterministic, domain-separated digest;
- opaque, fixed-format and content-free (for example a lowercase SHA-256
  digest with a `project-root-v1:` domain prefix);
- never the raw absolute/relative root, a memory field or a traceback. The
  existing `TaskEnvelope.request.raw` field remains part of the historical
  task contract and is not rewritten by TSC-02.
- recomputed from the current registry record for validation, never accepted
  from an untrusted caller without comparison.

Relocating a project preserves its opaque `project_id` but changes its root
identity. A newly composed context after relocation is valid; a context from
before relocation is stale until recomposed. Registering a different project
at the old root must never make the old context valid for that root.

### 3.2 Registry snapshot

The context must carry a non-negative `registry_revision` observed while
resolving the project. The existing `ProjectRegistry.load()` API is the
permitted snapshot source; no new registry persistence API is required. The
composer may resolve the root and read the revision in two calls, but it must
re-read both before publishing and compare project ID, normalized root and
revision. If any value changes between those reads, it returns an explicit
stale/error result rather than publishing a mixed task/state context. This
two-phase revalidation is the accepted race policy for TSC-02.

Router and Authority must verify both the project record's current root
identity and the registry revision policy before accepting a non-global
project context. A registry revision change for an unrelated project may be
treated as stale conservatively; it must never be treated as proof that an old
context is current. These checks happen before RouterCache/AuthorityCache
lookups, so a stale context cannot receive a cached project result; cache
modules need not change unless an implementation cannot enforce this ordering.

### 3.3 Serialization and compatibility

The lineage envelope requires an explicit schema/version policy. The preferred
shape is a new `TaskStateContext` schema version with required `lineage` fields:

```json
{
  "schema_version": 2,
  "task": {},
  "state": {},
  "lineage": {
    "project_id": "opaque-stable-id",
    "registry_revision": 0,
    "root_identity": "project-root-v1:<digest>"
  }
}
```

For an unresolved context, `lineage` is `{"status": "unresolved"}` and the
task project/state remain the existing unknown forms. For a global-only route,
`lineage` is `{"status": "global"}` and the route must contain no project IDs.
Those two forms are not eligible for a current-project route merely because a
caller supplies a project ID later.

The exact field names may change only with a documented contract update. A
schema-1 context without lineage must not silently enter a current-project
Router or Authority path. It must be rejected as `STALE_INPUT`/
`IDENTITY_REQUIRED`, or be accepted only by an explicit historical/evaluation
mode that cannot deliver current project candidates. Holdout/evaluation
fixtures must not be rewritten to hide a missing lineage field; if they need a
new schema they receive a versioned fixture update outside tuning.

Lineage `project_id` must match both `task.project.project_id` and
`state.project_id` for project-scoped contexts. Global-only contexts may omit a
project identity only when their route contract already forbids project
candidates.

## 4. Safety invariants

- Root reuse (`project-p` old root → `project-q`) returns a bounded stale/scope
  result and delivers zero `project-p` or `project-q` candidates from the old
  context.
- Valid relocation preserves the same stable `project_id`; a freshly composed
  context for the new root can route after lineage revalidation.
- A registry race between compose, Router and Authority is detected; no stale
  context is cached or passed as successful/degraded current-project output.
- Existing state revision/CAS checks, memory scope filtering, archived/unknown/
  disabled fail-closed behavior and global-only semantics remain unchanged.
- No package function writes `MemoryStore`, `StateStore`, `ProjectRegistry`,
  graph or cache as a repair side effect. Cache entries containing lineage are
  derived and must be invalidated on a mismatch.
- New lineage fields, lineage errors and lineage telemetry contain no raw
  roots, path fragments, registry documents, memory content or
  exception/traceback text. Existing `TaskEnvelope.request.raw` remains part
  of the historical task contract and is governed by its existing tests; TSC-02
  does not claim to remove or sanitize that field.
- `TaskStateContext.to_dict()` field order and all non-lineage task/state JSON
  fields remain byte/parity compatible within the declared schema policy; the
  added lineage envelope is the only intentional shape change.
- `task_state_context.py`'s existing task/state behavior, TaskEnvelope
  identity, and current state freshness semantics remain unchanged except for
  the explicit lineage envelope and bounded stale outcome.

## 5. Required evidence and tests

Focused tests must be added without deleting or weakening existing tests:

1. **Root reuse:** compose `project-p`, relocate it, register `project-q` at
   the former root, then prove Router and Authority reject the old context and
   expose no project candidates.
2. **Valid relocation:** relocate a project while preserving its stable ID;
   prove old context is stale, new context has the same ID and new opaque root
   identity, and a fresh route succeeds.
3. **Registry revision race:** mutate registry between task/state resolution
   (and independently between Router/Authority validation) and assert bounded
   `STALE_INPUT`/`SCOPE_ERROR`, with no cache or canonical write.
4. **Serialization:** round-trip the new schema; reject missing, malformed,
   mismatched, or raw-path lineage. Schema-1 current-project input must follow
   the explicit compatibility policy and never bypass identity validation.
5. **Isolation:** project A's context cannot deliver project B state/memory;
   global-only behavior remains explicit; archived/unknown/disabled projects
   remain fail-closed.
6. **Native regression:** exercise existing root-aware native context guard;
   change `brain_eleven/runtime/context.py` only if the bounded result cannot
   otherwise be represented, and record that separately.
7. **No-side-effect/privacy:** stale/invalid contexts leave bytes, revisions,
   cache files and registry unchanged and return path/content-free lineage
   errors. Existing non-lineage registry/state error text is not redesigned by
   TSC-02; if it must be changed, open a separate privacy contract.

Required existing surfaces include:

- `tests/test_task_state_context.py`
- `tests/test_context_router.py`
- `tests/test_authority_resolver.py`
- `tests/test_context_compiler.py`
- `tests/test_phase14_scope.py`
- `tests/test_task_model.py`
- `tests/test_pre12_memory_state_caller_migration.py`
- new focused lineage/serialization tests (the current tree has no dedicated
  `test_authority_serialization.py` file)

Exact caller inventories and any additional dynamic/evaluation callers must
be recorded before implementation. `evals/task_state_eval.py` and all frozen
holdout labels/cases remain read-only for this package; any required fixture
schema update is versioned, reviewable and never used to tune behavior.

## 6. Verification gates

The five gates used by prior IG-07 slices apply, with identity-specific
additions:

1. **Identity proof:** package/legacy/serialized surfaces agree on the same
   lineage field names, digest algorithm, project ID and exception/result
   identities.
2. **Adapter/authority proof:** no duplicate root hashing, no direct file
   writes, no second registry authority, no raw path persistence, and no
   bypass of existing state/memory checks.
3. **Parity and safety:** all focused tests above pass; root reuse, relocation,
   race, schema compatibility, isolation, privacy and no-side-effect tests
   pass with deterministic results.
4. **Full verification:** exact `git rev-parse HEAD`, full `pytest tests -q`,
   critical flake8 (`E9,F63,F7,F82`) on changed Python, `compileall`,
   `git diff --check`, and before/after holdout/evaluation input equality. No
   eval labels, thresholds or retrieval weights may be changed.
5. **Independent review:** a separate read-only reviewer checks contract,
   diff, caller inventory, identity algorithm, schema compatibility, race
   evidence, scope/privacy and rollback/cache behavior. Self-review is not
   acceptance.

## 7. Acceptance and failure policy

TSC-02 is `SHIP` only when every gate passes and independent review returns
exactly `SHIP`. Any old context delivering a project candidate after root
reuse, any raw path leakage in the new lineage surfaces, any silent acceptance
of schema-1 current context, any race not detected, or any canonical write
side effect is `FIX-FIRST`.

If satisfying the contract requires changing `ProjectRegistry` persistence,
MemoryStore/StateStore, retrieval, broad native compiler behavior or the
task-state package inversion, stop and return `RETHINK`; do not widen the
package informally.

## 8. Package report template

```text
PACKAGE: TSC-02
REVISION: <exact implementation/review SHA>
OBJECTIVE: <project identity and registry-lineage safety>
FILES CHANGED: <exact paths>
ROOT CAUSES ADDRESSED: <stale context/root reuse/lineage gap>
TESTS ADDED: <identity, race, serialization and isolation tests>
TESTS EXECUTED: <commands and exact results>
QUALITY METRICS BEFORE: <audit score and reproduced leakage>
QUALITY METRICS AFTER: <evidence-backed result>
SAFETY METRICS: <scope/privacy/no-write/race results>
KNOWN LIMITATIONS: <explicit compatibility/native boundaries>
OPEN FAILURES: <none or exact failures>
INDEPENDENT REVIEW: <SHIP / FIX-FIRST / RETHINK, exact review SHA>
SCORE BEFORE: <task-state/context score>
SCORE AFTER: <evidence-backed score, no unsupported increase>
VERDICT: <SHIP / FIX-FIRST / RETHINK>
```

**Plan status: REVIEW PENDING — implementation has not started.**
