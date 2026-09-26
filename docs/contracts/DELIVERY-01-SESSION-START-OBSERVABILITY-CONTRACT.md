# DELIVERY-01 — Native SessionStart Observability

**Status:** IMPLEMENTED / LOCAL VERIFICATION COMPLETE

**Date:** 2026-09-24

**Scope:** native delivery receipts and `brain_eleven doctor` only

**V2:** SHADOW; unchanged

## Reason for this package

The planned capture-silent-gap work was already completed by commit `4858366`:
Claude project-root slug computation was corrected, a RED→GREEN ownership test
was added, and five consecutive two-project dogfood runs passed. Reopening that
closed defect would duplicate work.

The next observed gap was delivery visibility. The native launcher already
wrote content-free delivery receipts under the runtime `deliveries` directory,
but `brain_eleven doctor` read only the legacy
`.claude/session-run-result.json` breadcrumb. A successful native SessionStart
could therefore be reported as `last SessionStart: unknown`.

This was reproduced on the live local vault before editing: the service was
running and a native bootstrap delivery receipt existed, while doctor still
reported the last SessionStart as unknown.

## Contract

1. New native delivery receipts record the bounded hook event name.
2. Doctor recognizes an `EMITTED` native `SessionStart` receipt and reports
   whether context was delivered or empty.
3. Receipts written before this package remain observable when their bounded
   turn hash identifies the `bootstrap` turn.
4. `UserPromptSubmit` receipts must never be mislabeled as SessionStart.
5. Legacy `.claude/session-run-result.json` behavior remains compatible.
6. No prompt, context text, transcript path, raw session identifier, memory
   content, or secret is added to diagnostics or receipts.
7. Capture, retrieval, context selection, rollout mode, V2 promotion, canonical
   memory/state, thresholds and evaluation corpora remain unchanged.

## Implementation

- `brain_eleven/runtime/launcher.py` adds `event` to the existing content-free
  delivery receipt.
- `brain_eleven/runtime/install.py` selects the latest valid SessionStart
  observation from legacy breadcrumbs and native delivery receipts. For old
  native receipts without `event`, it recognizes only the established bounded
  bootstrap turn hash.
- `tests/test_delivery01_session_start_observability.py` proves native,
  pre-event compatibility and non-SessionStart isolation behavior.

## Evidence

- TDD RED: the two native receipt tests initially returned
  `last SessionStart: unknown`.
- GREEN: delivery observability + legacy hook + PRE-13 runtime suite: 81 passed.
- Related bootstrap, W-10 delivery gate, W-06B task-aware and operational
  surface suite: 41 passed.
- `python -m compileall -q brain_eleven/runtime
  tests/test_delivery01_session_start_observability.py`: passed.
- `git diff --check`: passed (Git emitted only the repository's existing
  Windows line-ending advisory).
- Live read-only doctor check after the fix reported:
  `last SessionStart: ok ... (native; context delivered)` and overall `READY`.

## Exit boundary

This closes the false-unknown native SessionStart diagnostic only. Native
client trust remains explicitly `VERIFY_IN_NATIVE_CLIENT`; retrieval quality,
candidate extraction quality and V2 promotion remain separate work.
