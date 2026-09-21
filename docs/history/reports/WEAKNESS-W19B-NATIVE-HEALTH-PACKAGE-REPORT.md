# W-19B — Native Hook Health Package Report

**PACKAGE:** W-19B
**REVISION:** `555531861d22c270e4f01e644d0f7aac115c1a0e`
**OBJECTIVE:** Make native hook warning/error health visible in the durable
breadcrumb and `doctor()` diagnostics.
**CONTRACT:** `WEAKNESS-W19B-NATIVE-HEALTH-CONTRACT.md`, revision `1739697`

## Files changed

- `brain_eleven/runtime/launcher.py`
- `brain_eleven/runtime/install.py`
- `tests/test_w19b_native_health.py`

## Root cause addressed

The launcher previously wrote `last-hook.status="OK"` whenever `hook()`
returned normally, including bounded service-unavailable warnings. `doctor()`
did not consume that native status and could report a false healthy install.

## Tests executed

- Focused launcher/install/session-start suite: **67 passed**
- Full suite at exact revision: **1304 passed, 4 skipped, 2 warnings**
- Critical flake8 (`E9,F63,F7,F82`): **PASS**
- compileall: **PASS**
- `git diff --check`: **PASS**

Coverage includes warning→`DEGRADED`, clean→`OK`, exception privacy,
doctor missing/corrupt safety, degraded→later-success recovery and canonical
revision invariants. Existing legacy SessionStart failure behavior remains
covered.

## Quality metrics before/after

- Before: a normal-return warning could persist as native `OK` and remain
  invisible to doctor status.
- After: warning-bearing output and exceptions persist as `DEGRADED`, doctor
  reports `ATTENTION`, and a later successful hook clears the diagnostic.

## Safety metrics

- Canonical MemoryStore/StateStore/ProjectRegistry revision/content changes:
  **0**
- Raw prompt, transcript, token, exception or memory content persisted in the
  health breadcrumb: **0**
- Existing hook output, timeout and event behavior changed: **0**

## Known limitations

Native client trust still requires real Claude/Codex confirmation; W-07B's
latency matrix and multi-session dogfood remain open. SessionStart context
telemetry and maintenance delivery are separate packages. This change does
not promote V2 or unlock Phase 20.

## Open failures

W-19B package failures: **none**. W-07B native acceptance gates remain open.

## Independent review

Read-only implementation review at exact revision `5555318` returned
**SHIP**. It verified status derivation, safe missing/corrupt reads,
privacy, recovery and unchanged canonical surfaces; no P0/P1/P2 findings
remained.

## Score before/after

- Reminder/continuity runtime: **6.0 → 6.5** (native false-green diagnostics
  closed; trust, latency and dogfood evidence remain open)
- Other scorecard dimensions: unchanged.

## Verdict

**SHIP**
