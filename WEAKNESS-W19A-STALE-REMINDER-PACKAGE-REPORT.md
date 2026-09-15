# W-19A — Stale Maintenance Reminder Package Report

**PACKAGE:** W-19A
**REVISION:** `352f51b3e3a125b90a72b877b0baaf37bfbd64f0`
**OBJECTIVE:** Make the newest valid project/revision-bound maintenance
report authoritative for SessionStart reminder delivery.
**CONTRACT:** `WEAKNESS-W19A-STALE-REMINDER-CONTRACT.md`, revision `2454d80`

## Files changed

- `brain_eleven/runtime/maintenance_delivery.py`
- `tests/test_w19a_stale_reminder.py`

## Root cause addressed

`latest_reminder()` scanned reports newest-first but skipped a newer valid
clean, degraded, or non-surfaced report and continued to an older surfaced
report. This could repeat stale anomaly warnings after a newer maintenance
run.

## Tests executed

- W-19A + W-07B focused suite: **22 passed**
- SessionStart/context focused verification: **52 passed**
- Full suite at exact revision: **1298 passed, 4 skipped, 2 warnings**
- Critical flake8 (`E9,F63,F7,F82`): **PASS**
- compileall: **PASS**
- `git diff --check`: **PASS**

Coverage includes newer clean/degraded suppression, generated timestamp
validation, stale/foreign/malformed reports, missing state revision
fail-closed behavior, equal-mtime deterministic tie-breaking, disappearing
report reads, ack replay, project/revision isolation, and canonical revision
read-only assertions.

## Quality metrics before/after

- Before: a newer valid non-surfaced/degraded report could fall through to an
  older surfaced report.
- After: the newest valid report is authoritative; clean/degraded or
  `surface_at_next_session=false` returns `STALE_OR_MISSING` without fallback.

## Safety metrics

- Canonical MemoryStore/StateStore/ProjectRegistry revisions changed by
  `latest_reminder()`: **0**
- Cross-project or stale-revision delivery: **0** in focused tests
- Raw report/prompt/transcript/private-memory content persisted or returned:
  **0**

## Known limitations

W-07B native authenticated Claude/Codex trust, latency matrix and multi-session
dogfood remain open. Native hook health/doctor false-green behavior is tracked
separately as W-19B. This package does not change retrieval ranking, V2,
canonical stores, automatic Markdown writes or Phase 20.

## Open failures

W-19A package failures: **none**. W-07B and W-19B remain outside this package.

## Independent review

Read-only implementation review at exact revision `352f51b` returned
**SHIP**. The review independently verified the contract, focused tests,
full-suite result and critical static checks; no P0/P1/P2 findings remained.

## Score before/after

- Reminder/continuity runtime: **5.0 → 6.0** (bounded stale-reminder path is
  now authoritative; native trust and broader daily-use evidence remain open)
- Other scorecard dimensions: unchanged.

## Verdict

**SHIP**
