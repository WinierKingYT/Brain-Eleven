# IG04-B3 Phase 0 Audit Note

**Status: STOP — no B3 contract or implementation is authorized by this audit.**  
**Audit date:** 2026-09-23  
**Audited branch/base:** `ig/ig04b3-review-nudge` at `9472dc21bf1cbf109901b54f9e2d7fe000b4e46c`.

## Scope and result

This is a bounded, read-only Phase 0 audit for the IG04-B3 SessionStart review nudge. It is not a package acceptance report or an independent review. No product code, tests, hook configuration, thresholds, or runtime behavior were changed.

The exact-head master [Validation run `35781758406`](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35781758406) succeeded at `9472dc2` before branching. During this audit `origin/master` advanced to `6142c2c` with a documentation-only work-intake change; exact-head Validation run `35820195178` for that newer head is still in progress. Recheck the precondition if B3 is resumed.

## Review queue: verified facts

- `brain_eleven/runtime/review.py:176-181` stores each proposal, including its full `candidate` object, in the `rev_*.json` review record; the record has a seven-day `expires_at`.
- `ReviewStore._items()` at `brain_eleven/runtime/review.py:115-116` calls `read_json()` for every `rev_*.json`, materializing the complete records rather than reading content-free metadata only.
- `ReviewStore.expire()` at `brain_eleven/runtime/review.py:184-192` takes the review index lock, reads each complete record, and terminalizes expired pending items through `finish()`; this is a mutating lifecycle operation, not a read-only count.
- `ReviewStore.list()` at `brain_eleven/runtime/review.py:257-280` calls `expire()`, then loads all complete records while holding the index lock. It scopes B2 groups by project ID and content fingerprint (lines 262-265), computes visible duplicate groups, and can write `duplicate_of` / `duplicate_status` metadata (lines 275-279).
- `GET /api/review/candidates` at `brain_eleven/runtime/service.py:193-215` directly calls `ReviewStore(vault).list()` (line 200), then reads candidate objects to derive targets (lines 203-214), and returns the candidate list. This is not a count-only, content-free API.
- The repository-wide Python search found no product pending-count API. `evals/w07b/dogfood.py:60-62` has a benchmark helper that counts every JSON filename in the review directory; it does not filter by project, pending status, expiry, or B2 visible duplicate grouping, so it is not semantically equivalent to B3's requested pending-candidate count.

## Explicit STOP condition

The B3 goal says to stop if obtaining the pending count requires reading candidate text. The current production listing path materializes complete candidate records, and it also expires records and may write duplicate metadata. The only filename-count helper found does not implement the required project-scoped pending semantics. Therefore the available count path violates the content-free/read-only requirement. A separate metadata index or changed queue lifecycle would be a design change beyond this frozen package; this audit does not propose or implement one.

**Decision: STOP and wait for an owner-approved contract/spec revision.** Do not proceed to the frozen contract, code, tests, or B3 CI on this specification.

## Remaining audit surfaces

The decisive queue STOP was reached before the remaining Phase 0 surfaces were fully audited. They are explicitly **not verified by this note**: stable session-ID continuity across every Claude and Codex `UserPromptSubmit` and `Stop`/`SessionEnd` payload; exact client transcript shapes; service-state locking/atomic-write behavior for a proposed B3 marker; optional-line and budget behavior in the V1 SessionStart renderer; B3-compatible content-free telemetry; OFF/SHADOW/CANARY/ACTIVE behavior; and a same-machine before/after W-07B latency comparison. Repository code does read a `session_id` field in the launcher, but that alone does not prove stable identity across every required native event and client. No post-change latency measurement exists because no change was made.

## Re-entry requirements

If the owner chooses to continue B3, first resolve the pending-count boundary explicitly (including expiry, B2 duplicate visibility, project scope, and no candidate-text access). Then restart Phase 0 against an exact-head green base and complete every still-unverified audit surface before freezing any contract. Until then, the work remains stopped and no nudge is configured or delivered.
