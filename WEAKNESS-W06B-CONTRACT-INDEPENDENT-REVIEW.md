# W-06B Contract Independent Review

**Reviewed revision:** `75a2c46fd42d665b7e1910fb402023ffb78b553e`
**Reviewed contract:** `WEAKNESS-W06B-TASK-AWARE-RETRIEVAL-CONTRACT.md`
**Verdict:** `SHIP`

## Scope

This is an independent read-only review of the W-06B contract. It authorizes
the separate implementation phase only; it does not review or approve an
implementation.

## Findings

- The implementation surface now explicitly includes the ranking surfaces,
  `RuntimeConfig`, runtime context/service/launcher parity, and native hook
  wiring needed for the gate and handoff. It excludes unrelated architecture,
  authority mutation, V2 promotion, and Phase 20 changes.
- The production boundary is concrete: direct legacy SessionStart hooks remain
  V1-only, while native UserPromptSubmit flows through launcher, `/api/context`,
  `compile_context`, trusted project authorization, `TaskStateComposer`, and
  the bounded W-06B task input.
- Gate ownership is explicit at `.brain-eleven/runtime/config.json` through
  `RuntimeConfig`; `V1_LEGACY` is the default and the only rollback target,
  while `W06B_TASK_AWARE` is limited to native UserPromptSubmit. Missing,
  malformed, unknown, or unreadable configuration fails closed with bounded
  `RETRIEVAL_MODE_INVALID` telemetry.
- The finite task input/result schemas, status and fallback behavior,
  scope/lifecycle hard gates, mandatory overflow status, deterministic
  tie-break, five-item/1,024-token/8,192-byte bounds, and 250 ms p95 protocol
  are concrete and testable.
- W-09A DEV/TEST/HOLDOUT discipline, frozen corpus and fingerprints, provider
  availability handling, zero-leak safety gates, rollback evidence, and the
  V2 SHADOW / Phase 20 exclusions are preserved. The required test list binds
  config resolution, UserPromptSubmit handoff, SessionStart parity, API and
  launcher parity, and atomic rollback.

## Decision

`SHIP` — the contract is sufficiently precise and bounded to authorize the
separate W-06B implementation phase. This verdict does not claim that the
implementation or its exit-gate evidence is complete.
