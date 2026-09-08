# Phase 18 Independent Read-Only Review

**Status:** NOT STARTED — this is a review brief, not a verdict.

Review one immutable commit and its matching CI evidence without modifying the
repository. Confirm:

1. `authority` never writes canonical memory, state, registry, graph,
   ContextCompiler or SessionStart.
2. Resolver scope exactly matches trusted Router scope and no cross-project
   conflict comparison occurs.
3. Retrieval scores, free text and incomplete provenance never determine an
   authority winner.
4. Explicit supersession, duplicate metadata, lifecycle, stale input,
   corrupt policy/source and blocker-memory implementation gaps behave
   deterministically and fail closed.
5. CLI, cache, ledger, telemetry, provider and shadow reports contain no
   memory or state text.
6. The 150 public + 30 holdout authority corpus, Phase 15 provider adapter,
   shadow report and revision-bound evidence manifest are green.

Return `SHIP`, `FIX-FIRST`, or `RETHINK`, citing the commit SHA, workflow URL,
evidence artifact and severity of every finding. Do not treat local validation
as a graduation verdict.
