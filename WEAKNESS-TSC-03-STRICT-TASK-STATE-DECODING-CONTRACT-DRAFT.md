# TSC-03 — Strict Serialized Task-State Decoding Contract (Draft)

**Status:** DRAFT / IMPLEMENTATION NOT AUTHORIZED

**Baseline evidence:** working-tree revision '48d40f64c38e9b10afdfb4615fc5099d9e707d50'; the worktree already contains unrelated audit edits and generated evidence. This file is the only file added for this draft.

**Scope:** define the smallest safe contract for rejecting malformed nested values at the serialized 'TaskStateContext' boundary. This document proposes a reviewable implementation and verification package; it does not authorize production changes, schema migration, evaluator changes, or a commit.

## Decision requested

'authority.serialization.task_state_from_dict()' should become a strict decoder for the *derived* 'CurrentProjectState' representation that is already emitted by 'CurrentProjectState.to_dict()' and 'StateResolver.resolve()'. The decoder should reject malformed nested types, keys, identifiers, records, timestamps, statuses, and cross-field combinations before constructing a 'TaskStateContext'.

The implementation should remain bounded to the serialization boundary and focused tests. It should preserve the existing schema-1-with-lineage envelope, 'TaskEnvelope' behavior, 'TaskStateContext' composition, router and authority policies, canonical stores, and evaluation inputs. A request to change any of those surfaces is a separate contract and is a **RETHINK** outcome for TSC-03.

## Evidence: current behavior

The current decoder already validates the outer envelope:

* 'authority/serialization.py:116–121' requires an object, schema version 'TASK_STATE_CONTEXT_SCHEMA_VERSION', and a 'lineage' member.
* 'authority/serialization.py:122–126' requires exactly 'schema_version', 'task', 'state', and 'lineage'.
* 'authority/serialization.py:127' delegates the task object to 'TaskEnvelope.from_dict()', which is already strict.
* 'authority/serialization.py:128–145' requires the exact fourteen state keys, validates 'project_id', and validates that 'state_revision' is a non-negative integer with booleans excluded.
* 'authority/serialization.py:147–168' validates each collection as a list of objects and validates 'freshness', 'current', and 'references' only as objects. 'status', 'updated_at', 'error', 'archived', and all values inside those objects are passed through without nested type or enum validation.
* 'authority/serialization.py:150–155' delegates lineage to 'TaskStateLineage.from_dict()' and preserves the existing task/state/lineage project-identity checks.

'CurrentProjectState' is a plain dataclass. 'scripts/state_resolver.py:42–59' declares its fields, and 'scripts/state_resolver.py:61–77' serializes them, but there is no '__post_init__' or equivalent validation. Consequently, constructing it does not repair or reject malformed nested values.

The valid derived shapes are visible in the resolver:

* 'scripts/state_resolver.py:80–96' produces empty resolutions with 'unknown' freshness, null revision/timestamp, an empty current projection, empty collections, and 'not_checked' references.
* 'scripts/state_resolver.py:194–228' produces available or archived resolutions with explicit freshness, current milestone/objective projections, active filtered collections, reference health, and the canonical revision/timestamp.
* 'scripts/state_store.py:195–243' defines the established primitive rules for non-empty strings, namespaced IDs, non-negative integers, duplicate-free string lists, and timezone-aware ISO-8601 timestamps.
* 'scripts/state_store.py:246–348' defines the canonical record rules, including exact keys, provenance, timestamp and ID checks, record-specific status sets, severity, optional blocker 'memory_ref', and duplicate IDs.

For example, beginning with any valid 'TaskStateContext.to_dict()' payload, the following changes are currently accepted by 'task_state_from_dict()' when the outer keys and lineage remain valid:

    {
      "state": {
        "status": "not-a-resolver-status",
        "updated_at": {"unexpected": ["value"]},
        "freshness": {"status": ["wrong-type"], "age_days": "not-an-integer"},
        "current": {"phase_id": 7, "milestone": {"id": 1}, "objective": []},
        "active_requirements": [{"id": "wrong-namespace", "content": "sentinel"}],
        "references": {"valid": "wrong-type"},
        "error": 123,
        "archived": "yes"
      }
    }

The example is illustrative: the other required state keys are retained from the valid payload. The current decoder accepts these values because it only checks that 'freshness', 'current', and 'references' are mappings and that collection elements are mappings. It then stores the values in 'CurrentProjectState' unchanged. Missing or extra top-level state keys, wrong collection container types, invalid project identity, and invalid revision are already rejected; TSC-03 closes the nested gap without weakening those checks.

'authority/serialization._contains_content()' at 'authority/serialization.py:29–34' does not solve this gap. It is used by 'resolution_result_from_dict()' at 'authority/serialization.py:37–43', while 'task_state_from_dict()' does not call it. A global content ban would also be incorrect: state records legitimately contain current fact text in their 'text' or 'title' fields, and task envelopes preserve 'request.raw' as a historical contract.

The serialized decoder has two direct CLI/package boundaries:

| Caller | Current mapping | TSC-03 consequence |
| --- | --- | --- |
| 'authority/__main__.py:70–87' | 'ValueError' becomes JSON 'INVALID_INPUT', exit code 2 | Preserve the mapping; nested rejection must be bounded and deterministic. |
| 'context_compiler_v2/serialization.py:7,44–45' and 'context_compiler_v2/__main__.py:58–70' | Decoder 'ValueError' becomes compiler 'INVALID_INPUT', exit code 2 | Preserve successful valid payloads and the existing invalid-input mapping. |

The router and authority resolver also accept already-constructed objects. 'context_router/router.py:43–71' and 'authority/resolver.py:68–78' currently validate scope and identity fields, not arbitrary nested dataclass values. TSC-03 is a serialized-boundary contract; it must not silently widen into a new validation policy for hand-built 'TaskStateContext' objects.

## Contract surface and non-goals

The proposed production surface is 'authority/serialization.py' plus a new focused test module. No change is proposed to 'scripts/state_store.py', 'scripts/state_resolver.py', 'scripts/task_state_context.py', 'brain_eleven/runtime/task.py', the router, the authority resolver, the native compiler, or any evaluator.

The decoder remains an in-memory, read-only adapter. It may call pure validation helpers and dataclass constructors. It must not resolve a project, reload a registry, inspect a canonical store, load memory, read a cache, write a cache, update a graph, normalize a canonical document, or change the returned schema. Canonical-state validation and repair remain the responsibility of 'StateStore'; TSC-03 validates the already-derived serialized view.

The contract does not:

* bump 'TASK_STATE_CONTEXT_SCHEMA_VERSION' (it remains '1' with mandatory lineage);
* change 'TaskEnvelope.from_dict()', 'TaskStateLineage.from_dict()', or raw task request parity;
* add a new router or authority status;
* alter canonical state or memory schemas;
* change the 'task_state_context' package-inversion/migration boundary;
* modify 'evals/', holdout/public fixtures, labels, thresholds, or reports;
* make the native 'scripts/context-compiler.py' decode this envelope; or
* validate arbitrary in-memory dataclass instances that did not cross the serialized boundary.

## Normative schema invariants

The following rules apply to a payload accepted by 'task_state_from_dict()'. “Must” and “must not” are intentional contract terms.

### Envelope, task, and lineage

1. The input must be a mapping with exactly 'schema_version', 'task', 'state', and 'lineage'.
2. 'schema_version' must remain the current 'TASK_STATE_CONTEXT_SCHEMA_VERSION' ('1'). A schema bump is outside this task.
3. 'task' must continue to be decoded solely through the existing strict 'TaskEnvelope.from_dict()' path. Its exact nested request, project, constraints, domains, risk, evidence, IDs, and raw-request behavior remain unchanged.
4. 'lineage' must continue to be decoded through 'TaskStateLineage.from_dict()'. Its exact field set, allowed statuses, opaque root identity format, revision rules, and resolved/unresolved/global project rules remain unchanged.
5. The existing task project ID, state project ID, and resolved-lineage project ID equality checks remain mandatory. Unresolved/global lineage remains project-free.

### State envelope

'state' must be an object with exactly these keys:

    project_id, status, state_revision, updated_at, freshness, current,
    active_requirements, active_work_items, active_blockers, constraints, risks,
    references, error, archived

The following field rules are required:

| Field | Required decoded shape |
| --- | --- |
| 'project_id' | 'null' or a non-empty string. A resolved payload must satisfy the existing lineage/task identity checks. |
| 'status' | One of 'AVAILABLE', 'PROJECT_UNKNOWN', 'PROJECT_ARCHIVED', 'STATE_NOT_FOUND', 'STATE_CORRUPT', 'STATE_UNAVAILABLE', matching the current resolver constants in 'scripts/state_resolver.py:15–26'. No new status is admitted under schema 1. |
| 'state_revision' | 'null' or a non-negative integer; booleans are rejected. An available or populated archived resolver projection requires a non-null revision. Empty/error projections, including an archived project with no initialized state, require null as emitted by '_empty_resolution()'. |
| 'updated_at' | 'null' or a non-empty, parseable ISO-8601 timestamp with an explicit timezone offset. Preserve the accepted string; do not apply local-time defaults. An available or populated archived resolver projection requires a non-null timestamp; empty/error projections require null. |
| 'freshness' | Object with exactly 'status' and 'age_days'. 'status' is 'current', 'stale_candidate', or 'unknown'. 'age_days' is null only for 'unknown'; otherwise it is a non-negative integer, with booleans rejected. Empty/error projections must use 'unknown' and null. |
| 'current' | Object with exactly 'phase_id', 'milestone', and 'objective'. 'phase_id' is null or a non-empty string. 'milestone' and 'objective' are null or records satisfying the record rules below. |
| 'error' | 'null' or a non-empty string. The decoder must not include its value in a rejection message. Existing resolver error text is preserved as data when the payload is otherwise valid. |
| 'archived' | Boolean. 'AVAILABLE' must be false and 'PROJECT_ARCHIVED' must be true. Error projections must preserve the resolver-emitted archived flag, including archived registry cases. |

For 'PROJECT_UNKNOWN', 'STATE_NOT_FOUND', 'STATE_CORRUPT', and 'STATE_UNAVAILABLE', the decoder must require the empty projection emitted by '_empty_resolution()' for revision, timestamp, freshness, current, collections, and reference arrays. The 'archived' flag remains the resolver-emitted boolean because a corrupt or unavailable state can belong to an archived registry entry. 'PROJECT_ARCHIVED' is a populated or empty valid state for an archived project, with the same nested shape rules as 'AVAILABLE' and 'archived=true'.

### Current records and collections

Every collection must be a list. Each element must be an object with the exact record keys for its collection; unknown keys and missing keys are rejected. Record IDs must be unique within each collection. The decoder must use the established canonical record invariants from 'scripts/state_store.py:246–348' or a behaviorally identical pure adapter:

| Location | Record | Required keys and allowed values |
| --- | --- | --- |
| 'current.milestone' | milestone | 'id' with 'mil_' prefix; non-empty 'title'; status in 'PLANNED', 'ACTIVE', 'BLOCKED', 'COMPLETED', 'CANCELLED'; canonical 'source'; timezone-aware 'created_at'/'updated_at'; non-empty 'phase_id'. |
| 'current.objective' | objective | 'id' with 'obj_' prefix; non-empty 'text'; status 'ACTIVE'; canonical 'source'; timezone-aware 'created_at'/'updated_at'. |
| 'active_requirements' | requirement | 'id' with 'req_' prefix; non-empty 'text'; status 'ACTIVE'; canonical 'source'; timezone-aware timestamps. |
| 'active_work_items' | work item | 'id' with 'wrk_' prefix; non-empty 'text'; status 'TODO', 'ACTIVE', or 'BLOCKED'; canonical 'source'; timezone-aware timestamps. |
| 'active_blockers' | blocker | 'id' with 'blk_' prefix; non-empty 'text'; status 'ACTIVE'; canonical 'source'; timezone-aware timestamps; severity 'LOW', 'MEDIUM', 'HIGH', or 'CRITICAL'; optional 'memory_ref' must be a 'mem_' ID. |
| 'constraints' | constraint | 'id' with 'con_' prefix; non-empty 'text'; status 'ACTIVE'; canonical 'source'; timezone-aware timestamps. |
| 'risks' | risk | 'id' with 'rsk_' prefix; non-empty 'text'; status 'ACTIVE'; canonical 'source'; timezone-aware timestamps; severity in the canonical severity set. |

Canonical provenance rules remain in force: 'source' must have the exact '{type, reference?}' shape, use an allowed source type, and be canonical-eligible. Sensitive credential/secret patterns rejected by the canonical string validator remain rejected. The allowed fact-bearing fields are the established 'text' or 'title' fields; an ad hoc 'content' key or arbitrary nested value is not part of the state schema.

Collection names describe the resolver projection and therefore constrain statuses: requirements are active only; work items are 'TODO'/'ACTIVE'/'BLOCKED'; blockers and constraints are active; risks are active. The decoder must not silently filter, reorder, deduplicate, or repair records. It either accepts the already-derived projection or rejects it.

### Reference health

'references' must be an object with the required keys 'status', 'valid', 'dangling', and 'wrong_project'. The only optional key is 'error', and it is permitted only when 'status' is 'unavailable', matching 'StateResolver._reference_health()' at 'scripts/state_resolver.py:109–146'.

* 'status' must be 'not_checked', 'checked', or 'unavailable'.
* 'valid', 'dangling', and 'wrong_project' must be duplicate-free arrays of non-empty 'mem_' IDs.
* 'not_checked' must have empty ID arrays and must not carry 'error'.
* 'checked' must not carry 'error'.
* 'unavailable' may carry a non-empty string 'error'; the decoder must never echo that value in a raised diagnostic.

The decoder does not recheck memory references. It validates the shape and preserves the resolver classification supplied by the payload.

## Rejection and error mapping

The public exception type from 'task_state_from_dict()' remains 'ValueError', preserving current direct callers and the CLI adapters. Each failure must be deterministic and identify the bounded field path and reason, for example:

    task_state.state.status is unsupported
    task_state.state.updated_at must be a timezone-aware ISO-8601 timestamp
    task_state.state.active_requirements[0].source has invalid fields
    task_state.state.references.valid contains duplicate IDs

Diagnostics must not include offending values, serialized JSON, task raw requests, state 'text'/'title', memory IDs beyond a fixed field path, filesystem roots, cache paths, secret material, exception reprs, or tracebacks. If canonical validators raise 'StateSchemaError' or 'StateProvenanceError', the decoder must translate them to bounded 'ValueError' diagnostics rather than exposing implementation-specific exception text that contains values.

The existing adapters remain unchanged:

* 'authority/__main__.py' catches 'ValueError', emits '{"error":{"code":"INVALID_INPUT","message":...}}', and exits '2'.
* 'context_compiler_v2/__main__.py' catches 'ValueError', emits its existing 'INVALID_INPUT' response, and exits '2'.
* Direct package callers continue to receive 'ValueError'.

File-loading errors in 'authority/__main__.py:_load_json()' are outside this contract. TSC-03 must not claim to fix their existing path-bearing diagnostics by changing an unrelated CLI boundary.

## Privacy and no-write requirements

The decoder must be pure with respect to repository authorities:

1. It performs no 'MemoryStore', 'StateStore', 'ProjectRegistry', graph, cache, network, or telemetry writes.
2. It performs no canonical reload or registry revalidation. A serialized payload is validated against the fixed schema and the supplied lineage; authority truth checks remain downstream policy.
3. It does not write a repaired or normalized payload. Rejection is fail-closed.
4. It does not log or return raw payload values. Error text is bounded to stable field paths and reason labels.
5. Existing state record 'text'/'title' and 'TaskEnvelope.request.raw' remain accepted data fields where their current schemas allow them. This contract prevents decoder diagnostics and side effects from leaking those values; it does not redefine the content-free router output contract.
6. Tests must snapshot canonical state, registry, memory, and cache bytes/revisions before decoding and prove that decoding both valid and malformed payloads leaves them unchanged.

## Compatibility risks and holdout policy

'evals/task_state_eval.py' evaluates canonical task/state scenarios and immutable expected results; it does not currently deserialize a 'TaskStateContext'. Its smoke/public/holdout suites include the corrupt-state case ('state_holdout_corrupt'). TSC-03 must leave evaluator code, cases, labels, thresholds, and reports untouched. The implementation package must prove that all task-state eval outputs remain byte-for-byte or semantically equal to the recorded baselines before and after the change.

'tests/test_task_model_package_migration.py:46–105' protects the canonical/package/legacy task model identity and asserts no worktree diff for 'scripts/task_state_context.py'. TSC-03 must not edit that file or alter its inversion boundary. 'TaskStateComposer' output, inherited constraints, unresolved lineage, and schema-1 round trips must remain valid.

The valid 'TaskStateContext' payload is also consumed by:

* 'tests/test_tsc02_identity.py', including round-trip, missing-lineage, path-lineage, mismatch, unresolved, and global lineage cases;
* 'context_compiler_v2/serialization.py', which decodes task state inside compilation requests;
* router and authority CLI paths; and
* context compiler evaluation tests that serialize 'context.to_dict()'.

The principal compatibility risks are overconstraining a valid derived state and accidentally coupling this decoder to a canonical document schema. In particular, preserve the optional reference-health 'error', archived corrupt/unavailable flags, explicit-offset timestamp spelling, legitimate state fact text, empty projections, and the exact tuple-to-list serialization behavior. Do not copy all canonical state-document fields into the derived state envelope: 'revision'/record relationships/events belong to 'StateStore', while the serialized view has 'state_revision' and the seven derived record collections.

If strictness requires changing 'StateStore', 'CurrentProjectState', 'TaskStateComposer', 'task_state_context', router/authority status semantics, native 'compile_context', or evaluation inputs, stop and open a separate bounded contract. That is **RETHINK**, not an implementation detail of TSC-03.

## Focused test plan

Add a new test module, preferably 'tests/test_tsc03_task_state_decoding.py', without modifying evaluator or production callers.

### Acceptance cases

1. Compose valid contexts through 'TaskStateComposer', serialize with 'to_dict()', decode, and assert exact semantic round-trip for available, stale, archived, missing, unknown, corrupt, and unavailable resolver projections where those fixtures are available.
2. Cover resolved lineage plus project-free unresolved/global lineage. Preserve the existing TSC-02 identity tests unchanged.
3. Include milestone, objective, every collection type, blocker 'memory_ref', checked/unavailable reference health, inherited constraints, and explicit-offset timestamps.
4. Send a valid decoded context through the compiler/router/authority paths and assert the same statuses and content-free candidate metadata as the object-composed context.

### Rejection cases

Parameterize malformed values for every nested scalar and container: unsupported state/freshness/reference status, wrong or boolean integer, negative integer, nullability violation, wrong timestamp type, naive/malformed timestamp, non-boolean archived, non-string error, missing/unknown nested keys, wrong collection type, and non-object collection element.

Parameterize record failures for missing/unknown keys, wrong namespace, empty text/title, unsupported record status, invalid provenance or source type, naive timestamps, invalid severity, invalid blocker memory reference, duplicate IDs, and an ad hoc 'content' key. Confirm that legitimate 'text' and 'title' values remain accepted.

Cover cross-field rules: empty/error projection shape, 'AVAILABLE'/'PROJECT_ARCHIVED' revision/timestamp requirements, archived status/flag, resolved identity equality, and project-free unresolved/global lineage.

### Boundary and side-effect cases

1. Assert every malformed serialized payload raises 'ValueError' and that its message contains only a bounded field path/reason. Use sentinel raw request, state text, root path, memory ID, secret-shaped string, and 'references.error' values and assert none appear in the message.
2. Invoke both CLI adapters with a malformed nested payload and assert 'INVALID_INPUT' plus exit code '2'; do not change the adapters.
3. Snapshot canonical authority files and cache/registry revisions before decoding, decode valid and malformed payloads, and assert no bytes or revisions change.
4. Prove that a valid compilation request still decodes through 'context_compiler_v2.serialization.compilation_request_from_dict()'.

The existing focused suites remain required: 'tests/test_tsc02_identity.py', 'tests/test_task_state_context.py', 'tests/test_context_router.py', 'tests/test_authority_resolver.py', 'tests/test_context_compiler_v2_evaluation.py', 'tests/test_task_model_package_migration.py', 'tests/test_pre12_memory_state_caller_migration.py', 'tests/test_state_schema.py', 'tests/test_state_resolver.py', 'tests/test_task_state_eval.py', and 'tests/test_w22_optional_omission.py'.

## Exit gates

TSC-03 can be proposed for implementation only when all gates below are reviewable:

1. **Schema proof:** the accepted field/record/status/timestamp sets are demonstrated to match 'CurrentProjectState.to_dict()', 'StateResolver', and canonical record invariants, with no undocumented tightening.
2. **Strictness proof:** every targeted malformed nested type, key, enum, record, reference, and cross-field case rejects before a 'TaskStateContext' is constructed.
3. **Parity proof:** valid 'TaskStateComposer' output round-trips exactly; TSC-02 identity behavior, compiler decoding, router behavior, authority behavior, raw request parity, and optional omission behavior remain unchanged.
4. **Evaluation proof:** smoke, public, holdout, and all task-state evaluation outputs match their immutable baselines; no evaluator source, holdout data, labels, thresholds, or reports are modified.
5. **Privacy/no-write proof:** diagnostics contain no raw values or paths, and canonical state, memory, registry, cache, graph, and telemetry remain unchanged.
6. **Verification proof:** focused tests pass; full 'pytest tests -q' passes; changed Python passes the repository’s critical lint/compile checks; 'git diff --check' passes; and the diff is confined to the approved serialization/test/documentation package.
7. **Review proof:** an independent read-only review returns exactly 'SHIP'. Any accepted malformed nested value, error leakage, side effect, valid-payload regression, holdout/eval change, or out-of-scope production edit is 'FIX-FIRST'. Any request to widen the boundary listed above is 'RETHINK'.

There is no canonical migration or rollback data step because the envelope remains schema version 1. Rollback is reverting the decoder/test package and leaving canonical stores untouched.

## Estimated diff

* Production: approximately 80–160 lines in 'authority/serialization.py', including bounded primitive/record/reference helpers or a pure adapter around existing validation primitives. If the implementation needs more than this or requires edits to canonical validators, stop for a new contract.
* Tests: approximately 220–360 lines in a new 'tests/test_tsc03_task_state_decoding.py', with existing TSC-02 and evaluator tests left unchanged unless a narrowly justified assertion is added.
* Documentation: this contract draft and, after implementation, a separate evidence/review report.
* No edits to 'scripts/task_state_context.py', 'scripts/state_store.py', 'scripts/state_resolver.py', 'evals/', holdout artifacts, labels, or thresholds.

## Source inventory

* 'authority/serialization.py:106–168' — current task-state decoder and its shallow nested checks.
* 'scripts/state_resolver.py:42–77,80–96,109–146,194–228' — derived state fields, empty projection, reference health, and valid resolver projection.
* 'scripts/state_store.py:195–243,246–348' — primitive, provenance, timestamp, record, and duplicate-ID invariants.
* 'scripts/task_state_context.py:26–107,119–184' — schema version, lineage contract, context serialization, and composition.
* 'brain_eleven/runtime/task.py:390–618' — strict 'ProjectResolution' and 'TaskEnvelope' decoding/serialization.
* 'authority/__main__.py:70–87' and 'context_compiler_v2/__main__.py:58–70' — existing 'ValueError' to 'INVALID_INPUT' mappings.
* 'context_router/router.py:43–71,247–320' and 'authority/resolver.py:68–78,147–190' — downstream scope/identity checks and serialized-boundary separation.
* 'ENGINEERING-WEAK-POINTS-AUDIT.md:13–31,684–742', 'NEXT.md:81–93', and 'PROJECT-STATUS.md:25–42' — TSC-03 is recorded as a separate follow-up after TSC-01/TSC-02.
* 'docs/history/PHASE16-TASK-STATE-CONTRACT.md' and 'docs/history/PHASE17-TASK-AWARE-CONTEXT-ROUTER-CONTRACT.md' — authority, fail-closed, content-safe, read-only, and no-canonical-write boundaries.
* 'WEAKNESS-TSC-02-IDENTITY-CONTRACT.md' and 'WEAKNESS-TSC-02-IDENTITY-CACHE-ACCESS-INDEPENDENT-REVIEW.md' — schema-1 lineage compatibility, privacy, caller inventory, and review-gate precedent.
