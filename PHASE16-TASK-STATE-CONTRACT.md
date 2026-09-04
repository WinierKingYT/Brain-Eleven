# Phase 16 — Task + State Contract

**Status:** Active implementation contract
**Scope:** Task interpretation and current project state. Context routing is out
of scope.

## Purpose

Phase 16 gives Brain-Eleven two independently trustworthy answers:

- **Task:** what the current invocation asks for.
- **State:** what is currently true for a known project.

They are inputs to a future Context Router. They never select retrieval results
in this phase.

## Authority boundaries

| Concern | Authority | Persistence |
|---|---|---|
| Durable historical knowledge | `MemoryStore` | `.claude/validated-memory.json` |
| Project identity and lifecycle | `ProjectRegistry` | `.claude/project-registry.json` |
| Mutable project reality | `StateStore` | `.claude/project-state.json` |
| Current invocation interpretation | `TaskEnvelope` | Runtime only in V1 |

`Memory != State != Task`. State writes must never modify `MemoryStore`, and
memory writes must never modify `StateStore`.

## Invariants

1. Task analysis never creates or changes a project registry record.
2. A missing, corrupt, unsupported, or inaccessible state is explicit; it is
   never treated as an empty successful state.
3. Canonical state writes use lock, reload, project-revision compare-and-swap,
   fsync, and atomic replacement.
4. Every canonical state mutation has `user`, `system`, or trusted `tool`
   provenance. `ai_proposed` values cannot reach a canonical mutator.
5. Default state resolution only returns the requested project's state.
6. A state memory reference must identify global memory or memory from the
   same project. Invalid and dangling references remain visible diagnostics.
7. State contains current facts and references; it does not copy durable
   decision content.
8. Task and state IDs are immutable and use namespaces distinct from memory
   IDs (`tsk_`, `evt_`, `req_`, `wrk_`, `blk_`, `mil_`, `obj_`).
9. Typed mutations enforce lifecycle transitions. Arbitrary JSON patching is
   not exposed.
10. Phase 16 describes task and reality; it does not route, rank, resolve
    authority, or automatically execute work.

## Canonical state document

The store is one atomically-written JSON document. It contains a document
revision, per-project revisions, project records, and the latest 1,000 audit
events. Keeping events in the same document makes a state change and its audit
lineage indivisible; there is no separate JSONL transaction to recover.

Only explicitly initialized, registry-known active projects are mutable.
Archived projects are read-only historical state. A state record is initialized
only by the typed `state init` command, never by a resolver, compiler, or task
analyzer.

## Provenance and lifecycle

Milestones use `PLANNED`, `ACTIVE`, `BLOCKED`, `COMPLETED`, or `CANCELLED`.
Work items use `TODO`, `ACTIVE`, `BLOCKED`, `DONE`, or `DROPPED`. Requirements
and blockers are active until explicitly resolved or cancelled where allowed.
Terminal transitions are not silently reopened in V1.

Each mutation produces an embedded event with an immutable event ID, timestamps,
project ID, operation, old/new project revision, source, affected record IDs,
and non-sensitive change metadata. It does not duplicate state text.

## Fail-closed integration

`StateResolver` returns stable machine statuses: `PROJECT_UNKNOWN`,
`PROJECT_ARCHIVED`, `STATE_NOT_FOUND`, `STATE_CORRUPT`, `STATE_UNAVAILABLE`,
`STATE_CONFLICT`, `INVALID_TRANSITION`, `INVALID_SCHEMA`, and
`INVALID_PROVENANCE`.

Bootstrap artifacts record both the memory revision and current project's state
resolution/revision. A state-revision or resolution-status mismatch makes a
saved bootstrap stale. A missing state is rendered explicitly as unknown. A
corrupt or unavailable state prevents creation of a SessionStart-ready
bootstrap rather than injecting fabricated current state.

## Non-goals

- Context Router or task-aware memory selection
- LLM-based task analysis or enrichment
- Automatic task stitching, decomposition, completion, or state promotion
- State-to-memory conversion
- Arbitrary state patch APIs
- Private or network-dependent evaluation data
