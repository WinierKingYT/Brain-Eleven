# W-19A — Latest Maintenance Reminder Authority Contract

**Status:** CONTRACT REVIEW PENDING — implementation not started

**Program:** Engineering Weak-Point Improvement Goal

**Phase 20:** FROZEN / LOCKED — **V2:** SHADOW

## Objective

Make the newest valid maintenance report for a project and canonical source
revision authoritative for SessionStart reminder delivery. A newer clean or
degraded report must not fall back to an older report that still asks to be
surfaced.

## Observed weakness

`brain_eleven/runtime/maintenance_delivery.py::latest_reminder` sorts report
files newest-first, but continues scanning when a matching-revision report is
valid yet has `surface_at_next_session=false`, or when the report is degraded.
With two reports bound to the same memory/state revisions, a newer clean or
degraded report can therefore expose an older anomaly reminder again. Existing
coverage tests the clean-first path only and does not assert newest-report
authority.

## Bounded behavior contract

1. Select reports only for the requested project whose report envelope is
   valid, successful or explicitly degraded, and whose memory/state revisions
   match one current revision snapshot.
2. Every candidate must contain a parseable, timezone-aware ISO-8601
   `generated_at` string. Among those reports, choose the newest report
   deterministically. Filesystem modification time alone is not a sufficient
   tie-break; use validated report metadata (`generated_at`, then `report_id`)
   after the existing newest-first scan.
3. Once the newest matching report is selected, its
   `surface_at_next_session` flag is authoritative:
   - `true` returns the existing bounded `FRESH` reminder;
   - `false` returns `STALE_OR_MISSING` and never falls back to an older
     surfaced report;
   - a valid `DEGRADED` report returns the existing bounded
     `STALE_OR_MISSING` status and never falls back to an older surfaced
     report.
4. A malformed, foreign, stale-revision, or unreadable report is not a
   candidate and may be skipped. The current revision snapshot includes an
   explicit `None` state revision; a report with any non-`None`
   `source_state_revision` does not match that snapshot. Report enumeration
   must treat a file disappearing or failing `stat()` between directory scan
   and read as unreadable and skip it without raising. No raw report content,
   prompt, transcript,
   exception, or private memory text may be returned or persisted.
5. Existing `ack_reminder` delivery receipts remain content-free,
   project-scoped, idempotent, and unchanged for a selected fresh report.
6. The function remains read-only with respect to canonical MemoryStore,
   StateStore, and ProjectRegistry. It may create only the existing derived
   runtime directories through `_ensure`; no canonical revision may change.

## Determinism and tie handling

The implementation must define and test a stable ordering for reports with
equal filesystem timestamps. The test fixture must set equal `st_mtime` values
and assert that the same report is selected on repeated calls. The ordering
must not depend on directory iteration order.

## Required tests

Add focused tests without weakening existing tests:

- newer `surface_at_next_session=false` suppresses an older surfaced report;
- newer valid `DEGRADED` report suppresses an older surfaced report;
- stale/foreign/malformed reports are skipped and do not suppress a valid
  current report;
- equal-mtime reports choose the same newest report deterministically;
- selected report remains revision-bound and project-isolated;
- `ack_reminder` still creates one receipt and a replay is a no-op;
- no MemoryStore/StateStore/ProjectRegistry revision changes occur.

Run the existing W-07B maintenance delivery/context suites unchanged, then
the full `pytest tests -q`, critical flake8 (`E9,F63,F7,F82`), compileall and
`git diff --check`.

## Scope exclusions

This package does not change canonical memory/state, extraction, retrieval
ranking, V2 delivery, native hook authentication, W-07B acceptance gates,
automatic Markdown writes, or Phase 20. Native health/doctor false-green
behavior is tracked separately as W-19B and is not part of this contract.

## Exit gate

W-19A may be marked `SHIP` only after:

1. contract-independent review returns `SHIP`;
2. implementation and tests satisfy every behavior above;
3. focused and full regression are green at an exact committed revision;
4. an independent read-only implementation review returns exactly `SHIP`.

Until then: **W-19A = OPEN / NOT ACCEPTED**.

**Contract status: REVIEW PENDING — implementation başlamadı.**
