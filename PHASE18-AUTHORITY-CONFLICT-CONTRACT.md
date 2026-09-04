# Phase 18 — Metadata-First Authority & Conflict Contract

## Boundary

Phase 18 consumes a Phase 16 `TaskStateContext` and a Phase 17
content-free `RouterResult`, then emits a content-free `ResolutionResult`.
It is read-only: it does not retrieve new candidates, write canonical memory,
state, registry or graph data, modify `ContextCompiler`, or inject a result
into SessionStart. Supported modes are only `OFF` and `SHADOW`.

`ResolutionResult` is an authority annotation, not a final context-selection
result. Token budgeting and final prompt construction remain Phase 19 work.

## Metadata-first evidence

Memory authority uses only canonical ID, scope/project, type, lifecycle,
timestamp, dedup fingerprint, explicit `superseded_by`, and declared source
presence. State authority uses its typed item kind, lifecycle, canonical source
type and explicit blocker `memory_ref`. The resolver never serializes text.

Missing provenance is `INCOMPLETE`; it never breaks an authority tie. Free-text
memories are not semantically compared in V1. Therefore, unannotated active
decisions remain supporting or unresolved rather than being force-resolved.

## Scope and resolution policy

Trusted `AuthorityOptions` must exactly match the Router plan. Raw prompts and
Router candidates cannot broaden scope or history.

| Router scope | Phase 18 behavior |
|---|---|
| `CURRENT_PROJECT` | Compare only current-project records; global and project records coexist without implicit override. |
| `GLOBAL_ONLY` | Admit global evidence only. |
| `SELECTED_PROJECTS` | Process each selected project as an independent authority partition; no cross-project conflict set exists. |

Explicit supersession, same-scope dedup fingerprints and lifecycle are the only
memory-to-memory relations resolved in V1. An active state blocker explicitly
referencing a historical/superseded memory becomes `IMPLEMENTATION_GAP`; it
does not silently override memory. Unknown or unsafe relations return
`UNRESOLVED`, `REQUIRES_CLARIFICATION`, or `ABSTAIN` behavior rather than a
fabricated winner.

Memory/state revisions in `RouterResult` must match canonical snapshots before
and after resolution. A mismatch returns `STALE_INPUT`. The shadow coordinator
may run one new `route → resolve` pass; the resolver itself never reroutes.

## Privacy, evaluation and graduation

The cache, CLI, explanation ledger, shadow reports and telemetry store only
IDs, revisions, policy versions, statuses and reason codes. The cache is
derived, bounded and revision-keyed.

`python -m authority resolve` accepts serialized task/router contracts;
`python -m authority shadow` composes, routes and resolves without prompt
injection. `python -m evals.authority_evaluation --suite all` runs 150 public
synthetic cases plus 30 isolated holdout cases. The existing Phase 15 evaluator
also exposes the `metadata_authority_v1` provider.

Graduation requires a revision-bound green CI run, 180-case authority corpus,
unchanged Phase 15 safety gates, shadow-only evidence, and an independent
read-only `SHIP` review. A local worktree result is never a graduation claim.
