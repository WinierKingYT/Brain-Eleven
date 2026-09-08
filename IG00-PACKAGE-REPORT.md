# IG-00 Package Report — Freeze & Baseline Closure

**Package:** IG-00 Freeze & Baseline
**Revision:** `b8d8fa2a6f99f51c672d148d4c4e1506971e91de`
**Date:** 2026-09-08
**Contract:** `IG00-FREEZE-BASELINE.md`

## Objective

Verify the Phase 20 freeze, preserve the immutable PRE-12 baseline, reconcile
the actual runtime dataflow, classify documentation authority, and prove the
native hook/queue boundary without opening IG-01.

## Files changed

This report records evidence for the existing IG-00 implementation. The
working tree also contains user-owned untracked files; they were not touched,
staged or deleted.

## Root causes addressed

- Phase 20 status and IG sequencing were made explicit.
- PRE-12 immutable baseline (`211bf2...`) was separated from current review HEAD.
- Native V1/V2 ownership and legacy compatibility paths were documented.
- Unsafe semantic fallback, cache provenance and bounded runtime hardening were
  retained inside IG-00 without promoting V2.

## Tests added

No new production behavior was added during closure verification. Existing
focused coverage includes native bootstrap, local hook paths, SessionEnd,
queue replay and runtime lifecycle tests.

## Tests executed

| Check | Result |
|---|---|
| Non-integration regression (`pytest -q --ignore=tests/integration`) | **718 passed**, 2 warnings |
| Integration marker suite (`pytest -q -m integration`) | **39 passed**, 2 warnings |
| IG-00 hook/queue focus | **21 passed** |
| Critical flake8 (`E9,F63,F7,F82`) | **PASS** |
| `git diff --check` | **PASS** |
| `pyproject.toml` parse | **PASS** |

## Native smoke evidence

All rows used an isolated temporary vault and client configuration. No live
user vault or client configuration was modified.

| Client/event | Exit | Hook receipt | Queue/canonical evidence | Trust boundary |
|---|---:|---|---|---|
| Claude / SessionStart + UserPromptSubmit | SessionStart hook success; client turn ended without credentials | `last-hook=OK` | Separate Claude Golden E2E: queue `COMMITTED`, canonical effect verified | Client model call unavailable; installed trust not inferred |
| Codex / UserPromptSubmit | Hook success; client turn ended with 401 and bounded timeout | `last-hook=OK` | Separate Codex Golden E2E: queue processed, canonical effect verified | Temporary hook was explicitly trust-bypassed; live trust not inferred |

The model-authentication failures are environment limitations, not product
successes. They do not invalidate the hook and queue evidence, but they prevent
claiming a completed authenticated model turn.

## Quality metrics before/after

| Dimension | Before | After |
|---|---:|---:|
| Phase 20 freeze visibility | Partial | Verified in current status/docs |
| Exact-head local regression | Pending | Verified: 718 + 39 passing |
| Native hook boundary | Configuration-only | Isolated Claude/Codex hook responses verified |
| Queue canonical effect | Focused-test evidence | Both client transcript shapes verified in Golden E2E |
| Independent review | Pending | Pending |
| Exact-head GitHub CI | Pending | Blocked: PR write permission unavailable |

## Safety metrics

- Live-vault/config mutation during smoke: **0**.
- Synthetic vector production fallback: **disabled**.
- Native hook output preserved content-free boundaries in receipts/logs.
- Wrong-project or secret leakage was not observed in the executed focused
  suites; no new graduation claim is made from this package.

## Known limitations

- GitHub draft PR creation returned HTTP 403 (`Resource not accessible by
  integration`); local `gh` is not installed and no signed-in browser session
  is available.
- Exact-head GitHub Validation/runtime/security workflows therefore have no
  current run for this revision.
- No independent read-only reviewer was available in this execution context.
- Claude/Codex model calls could not authenticate in the isolated temporary
  homes; native client trust remains `VERIFY_IN_NATIVE_CLIENT`.

## Open failures

1. Create the master-targeted draft PR from an authenticated GitHub context.
2. Capture exact-head Validation and PRE-13 runtime workflow results.
3. Obtain an independent read-only IG-00 review with a `SHIP` verdict.

IG-01 remains closed while any of these gates are open.

## Independent review

**NOT AVAILABLE — no independent reviewer was present.** Self-review and local
test evidence are not counted as independent acceptance.

## Score before/after

No score increase is claimed without CI and independent review. Existing
approximate scorecard values remain unchanged.

## Verdict

**FIX-FIRST / NOT ACCEPTED**

Phase 20 remains **FROZEN / LOCKED** and V2 remains **SHADOW**. This report does
not authorize IG-01, merge, release or Phase 20 unlock.
