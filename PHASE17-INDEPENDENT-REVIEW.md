# Phase 17 Independent Read-Only Review

**Status:** NOT STARTED — this file is a review brief, not a verdict.

The reviewer must be independent from the implementation and work read-only
against a specific commit plus its revision-bound CI evidence.

## Required checks

1. Confirm `context_router` does not modify canonical memory, state, registry,
   graph, ContextCompiler or SessionStart.
2. Verify raw task text cannot widen project scope, history, archived access or
   rollout mode.
3. Verify `CURRENT_PROJECT`, `GLOBAL_ONLY`, and explicit
   `SELECTED_PROJECTS` scopes; reject any implicit or unbounded all-project
   behavior.
4. Verify corrupt memory/state/config fails closed, state revision races return
   `STALE_INPUT`, and a stale/corrupt graph produces `DEGRADED`, not trusted
   graph candidates.
5. Verify RouterResult, cache, CLI, telemetry, route evaluation and shadow
   reports exclude memory/state text.
6. Verify the unchanged Phase 15 evaluation contract runs through the router
   adapter and reports zero wrong-project/inactive leakage for the public and
   holdout suites.
7. Verify the Phase 17 evidence manifest is based on the tested revision, not
   a manually asserted status.

## Verdict format

Return exactly one of:

- `SHIP` — every graduation gate is evidenced.
- `FIX-FIRST` — a bounded defect blocks graduation.
- `RETHINK` — a contract boundary or safety model is wrong.

Include the reviewed commit SHA, workflow run URL, evidence artifact name, and
each finding's severity. Do not mark Phase 17 graduated from a local working
tree alone.
