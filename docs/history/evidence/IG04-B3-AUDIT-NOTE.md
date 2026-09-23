# IG04-B3 Phase 0 Audit Note

**Status: PASS TO CONTRACT — implementation has not started.** Phase 0 found no unresolved STOP after the owner's two scope decisions recorded below. This note is audit evidence, not a package acceptance report or independent review.

**Audit date:** 2026-09-23

**Audited head:** `99c080d74531fd7b25a3ea6097075cb2e0faef4c` on `ig/ig04b3-review-nudge`.

**Green base:** `6142c2c02d5ea13d1260f0ce10597918f58c4afc`; exact-head master [Validation run `35820195178`](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35820195178) passed. The audited branch is clean and contains only three earlier B3 audit/status documentation commits above that base. No product code, tests, hook configuration, thresholds, or runtime behavior changed during this audit.

## Owner decisions that resolve the initial STOP

On 2026-09-23 the owner approved both of these bounded contract revisions:

1. Permit a content-free, project-scoped review metadata index/sidecar and the review-queue lifecycle changes needed to maintain it. SessionStart may query that metadata only; it may not enumerate or materialize candidate records, call the mutating list/expiry path, or reconstruct a missing index from candidate bodies.
2. Preserve the prompt counter across per-turn `Stop`; finalize it only on the per-session `SessionEnd` event. This is required for the five-prompts-per-session threshold to be reachable.

These decisions authorize a revised contract, not implementation before that contract is committed.

## Review queue and count semantics

- `ReviewStore.add()` stores the candidate body together with top-level `status`, `expires_at`, `project_id`, and content/event fingerprints in `brain_eleven/runtime/review.py:143-182`. Pending proposals expire after seven days.
- `ReviewStore._items()` at `brain_eleven/runtime/review.py:115-116` calls `read_json()` on every review record, materializing the complete record. `expire()` at `:184-192` reads records and terminalizes expired pending items.
- `ReviewStore.list()` at `brain_eleven/runtime/review.py:257-280` expires records, loads full records, groups pending candidates by project ID and content fingerprint, returns one visible primary per group with duplicate metadata, and may write `duplicate_of` / `duplicate_status` to records.
- B2's visible count is therefore the number of distinct `(project_id, content_fingerprint)` groups having at least one pending, unexpired member — not the raw number of `rev_*.json` files. B2's ordering picks a deterministic primary but does not change that group count. Existing project-scope and expiry tests are in `tests/test_ig04_b2_review_order.py:64-142`.
- `GET /api/review/candidates` at `brain_eleven/runtime/service.py:193-215` calls `ReviewStore.list()`, reads candidate content to derive targets, and returns the candidate list. No existing production count-only API was found. The filename counter in `evals/w07b/dogfood.py:60-62` is not semantically equivalent.
- Queue mutations are owned by `ReviewStore.add/expire/finish` and review service actions under the review index lock (`review.py:155-192,232-279`; `service.py:27-29,59-67`). The worker also serializes its processing loop and expiry (`worker.py:192-203,557-568`).
- `runtime_file_lock()` provides cross-process locking (Windows mutex / POSIX `flock`) at `brain_eleven/runtime/storage.py:37-142`; `write_json()` uses a same-directory temporary file, fsync and `os.replace` at `:158-190`. Atomic replacement is per file, not a transaction across the proposal and an index.

### Bounded index design required by the contract

The metadata index must hold only the data needed to count visible groups: review ID, project ID, lifecycle status, expiry timestamp, and the existing content fingerprint (a hash). It must not hold candidate text, prompt text, or filesystem paths. The count is per registered, opted-in project and excludes terminal or expired records while collapsing B2 duplicates by project plus content fingerprint.

All queue writers must update record metadata and the index while holding the existing review index lock. Since two-file `write_json()` calls are not jointly atomic, the implementation must use a recoverable transaction/intent protocol or an equivalent generation-checked scheme. Any incomplete, corrupt, or inconsistent index is an unknown count: SessionStart fails closed with no nudge and does not rebuild by reading candidate bodies. Reconciliation may occur only on an existing review-queue path that already owns queue reads/writes. Tests must cover interrupted add, expiry, and finish updates, as well as legacy records and direct fixture mutations.

## Hook identity and lifecycle

- Official Claude hook documentation identifies `session_id` in UserPromptSubmit, Stop and SessionEnd payloads; it defines UserPromptSubmit/Stop as per-turn events and SessionStart/SessionEnd as per-session events ([hook lifecycle](https://code.claude.com/docs/en/hooks#hook-lifecycle), [UserPromptSubmit input](https://code.claude.com/docs/en/hooks#userpromptsubmit-input), [Stop](https://code.claude.com/docs/en/hooks#stop), [SessionEnd input](https://code.claude.com/docs/en/hooks#sessionend-input)).
- Official Codex hook documentation defines the common `session_id` field and includes it on UserPromptSubmit, Stop and SessionEnd ([common input fields](https://developers.openai.com/codex/hooks#common-input-fields), [UserPromptSubmit](https://developers.openai.com/codex/hooks#userpromptsubmit), [Stop](https://developers.openai.com/codex/hooks#stop), [SessionEnd](https://developers.openai.com/codex/hooks#sessionend)).
- The repository's transcript ownership reader maps Claude's `sessionId` and Codex's `session_meta.payload.session_id` at `brain_eleven/runtime/ownership.py:117-132`; synthetic payload coverage is in `tests/test_w03b_transcript_ownership.py:46-95`. This verifies documented schema and parser paths, not live native-client delivery. Native hook trust remains unverified.
- In the current launcher, Stop and SessionEnd share the same enqueue route (`brain_eleven/runtime/launcher.py:84-103`; `brain_eleven/runtime/worker.py:129-135`). B3 must distinguish the raw event at the hook boundary and finalize its counter independently of transcript availability or queue success. The per-session delivery lock currently covers SessionStart/UserPromptSubmit only (`launcher.py:153-163`); the new state update needs its own bounded cross-process lock.
- Claude Stop is a turn completion event and does not run for a user interrupt; SessionEnd is the cleanup event. Codex SessionEnd can be delayed until lifecycle termination or idle. The contract must preserve counters through every Stop and finalize/clean them only on SessionEnd; any delay before the next nudge is an explicit cadence limitation. On SessionEnd, finalization must locate all counters for that session hash, preserving their stored project IDs rather than assuming the final event's cwd identifies every project touched.
- The existing UserPromptSubmit V1 pipeline transiently uses its prompt for capture (`launcher.py:100-116`; `context.py:200`). The B3 counter branch itself must use only event/session/project metadata and must not inspect, retain, or emit prompt text.

## State, V1 rendering, telemetry and modes

- `RuntimeConfig` resolves operational service state to `<vault>/.brain-eleven/runtime` and its review queue to `<vault>/.brain-eleven/runtime/review` (`brain_eleven/runtime/storage.py:210-218`; `brain_eleven/runtime/review.py:22-29`). These are vault-owned operational paths, separate from canonical memory/state stores.
- The V1 SessionStart renderer has bounded optional maintenance output and a 3,000-token total budget at `brain_eleven/runtime/context.py:121-183`. It renders the core context first, applies safety and budget checks, and performs final revision/scope/mode checks. The hook emits only through `hookSpecificOutput.additionalContext` after V1 approval/delivery (`launcher.py:115-127`). The nudge must be a separately identifiable optional line inside the same budget and final checks; overflow or failed checks omit it without changing accepted V1 behavior.
- Existing telemetry is content-free: delivery receipts keep session/turn hashes, IDs, flags and timing (`launcher.py:130-136`); context telemetry removes `context` before persistence (`context.py:249-253`); the launcher error path does not echo stdin, prompt, path or exception content (`launcher.py:171-177`). B3 telemetry and persisted marker/counter state must follow the same boundary.
- Runtime gates already default OFF and scope to registered project IDs (`brain_eleven/runtime/storage.py:220-277,323-333`); installer opt-in defaults to SHADOW (`brain_eleven/runtime/install.py:139-163`). UserPromptSubmit delivery is suppressed in SHADOW while V1 SessionStart remains available (`brain_eleven/runtime/context.py:194-199,236-248`; `RUNTIME-DATAFLOW.md:55-58,96-102`). No gate or threshold change is needed or authorized.
- The project hooks route optional context through V1; no direct-text SessionStart owner should be added. Unknown/unregistered/not-opted-in projects and all marker/index/queue errors must produce no nudge and must not block session start.

## Same-machine W-07B baseline

The isolated temporary-vault W-07B harness at `evals/w07b/latency_matrix.py:1-20,31-38,108-134,147-187` completed its required sample gate on the current host (Claude 2.1.278). It created and removed its isolated vault/client artifacts and did not touch the user vault. Results:

| Event | Samples | p50 | p95 |
|---|---:|---:|---:|
| Cold SessionStart | 5 | 1354 ms | 1387 ms |
| Warm SessionStart | 5 | 181 ms | 203 ms |
| UserPromptSubmit | 10 | 225.5 ms | 258 ms |
| Stop | 10 | 95.5 ms | 105 ms |
| SessionEnd | 10 | 94.5 ms | 119 ms |

This is a Claude-only same-host baseline for later comparison; it does not establish Codex latency or native hook trust. The existing W-07B quality/latency gates remain unchanged and are not claimed to pass.

## Focused read-only validation

`python -m pytest tests/test_ig00_bootstrap.py tests/test_ig04_b2_review_order.py tests/test_w03b_transcript_ownership.py tests/test_srt01_runtime_lock.py -q` passed **31 tests** in 12.52 seconds on the audited tree. No tests were changed or skipped.

## Phase 0 result and remaining boundaries

**Decision: PASS TO A REVISED, FROZEN CONTRACT.** The user's two decisions resolve the only Phase 0 STOPs. Before implementation, the contract must freeze (1) per-turn Stop preservation and SessionEnd-only finalization, and (2) the content-free visible-group index, recoverable record/index updates, fail-closed handling, and no candidate-body access on SessionStart.

Live Claude/Codex native hook trust, Codex latency, and post-change latency remain unverified. They are not Phase 0 blockers; they must be reported as limitations and compared where measurable after implementation. IG01 evaluation packages, HOLDOUT, canonical memory/state, V2 SHADOW, thresholds, gates and root-level files remain out of scope.
