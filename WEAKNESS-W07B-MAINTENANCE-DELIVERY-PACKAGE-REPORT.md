# W-07B Native Maintenance and Reminder Delivery — Package Report

**PACKAGE:** W-07B  
**REVISION:** `72e038a` (exact regression evidence head; code/test head `f322d2c`, implementation `94f331f`, hardening `facd5e1`)
**STATUS:** FIX-FIRST / NOT ACCEPTED  
**PHASE 20:** FROZEN / LOCKED  
**V2 RUNTIME:** SHADOW

## OBJECTIVE

Connect a verified native `SessionEnd` capture effect to an asynchronous,
durable maintenance intent and deliver only a project- and revision-matched,
privacy-safe bounded reminder at the next `SessionStart`. `Stop` remains a
capture-only event. Existing canonical memory/state authorities, retrieval,
and the manual maintenance path remain unchanged.

## FILES CHANGED

Implementation commit `94f331f`:

- `brain_eleven/runtime/maintenance_delivery.py` — durable intent/receipt
  queue, atomic report projection, replay/freshness handling, and bounded
  reminder lookup.
- `brain_eleven/runtime/worker.py` — enqueue a maintenance intent only after
  the capture receipt and terminal queue commit are durable.
- `brain_eleven/runtime/service.py` — process at most one maintenance intent
  asynchronously per worker loop.
- `brain_eleven/runtime/maintenance.py` — optional project-scoped anomaly and
  digest inputs while preserving the manual/default API.
- `brain_eleven/runtime/context.py` — append a fresh bounded reminder to the
  existing bootstrap context without replacing the normal V1 path.

Test commit `1a2c839`:

- `tests/test_w07b_maintenance_delivery.py` — native scheduling, duplicate
  intent, privacy projection, crash-after-publication replay, revision
  freshness, corruption/cross-project rejection, bounded failure, and
  canonical non-mutation tests.

Follow-up commits `b2a0ff8` and `8468b32` bound persisted failure codes to
content-free uppercase identifiers, keep maintenance processing disabled in
runtime `OFF`, and test the rejection of an unsafe exception code.

Final hardening commit `8b18d66` makes report severity projection bounded,
keeps raw exception text out of maintenance logs, and acknowledges a
SessionStart reminder only after final scope/freshness validation and an
atomic delivery receipt.

Reconciliation fairness commit `e1512e9` scans past already-reconciled
completed jobs so a later enqueue gap cannot be starved by the bounded batch.

Exact-head hardening commit `6d40011` adds an expiring processing lease so a
second worker cannot claim a live intent, validates every report envelope
before reminder delivery, and keeps canonical revision failures out of logs.
Test commits `4e0f3fc` and `f322d2c` add lease-concurrency, structurally
incomplete report, post-maintenance-crash retry, and expired-lease fencing
coverage.

## ROOT CAUSES ADDRESSED

- Native `SessionEnd` previously stopped at capture delivery and did not
  schedule packaged maintenance.
- `Stop` and `SessionEnd` were not separated at the maintenance boundary.
- Maintenance output had no durable execution identity or retry/terminal
  state.
- Reports were not project/revision bound and could retain raw step data.
- A crash after atomic report publication could have rerun derived work; the
  published-report reconciliation path now completes the intent without a
  second run.
- SessionStart had no bounded native reminder projection.

## TESTS ADDED

Fifteen focused tests in `tests/test_w07b_maintenance_delivery.py` cover:

1. SessionEnd-only intent creation and duplicate idempotence; Stop exclusion.
2. Worker scheduling after a terminal capture result.
3. Completed-capture reconciliation after an enqueue gap.
4. Privacy-safe report projection and fresh reminder delivery.
5. Repeated processing without rerunning maintenance.
6. Crash after report publication and before terminal intent move.
7. Crash before report publication with staging promotion and no rerun.
8. Stale report rejection after a canonical revision change.
9. Corrupt and foreign report rejection.
10. Surface flag and session-keyed delivery receipt behavior.
11. Bounded retry/failure, content-free error persistence, and unchanged
   MemoryStore/StateStore revisions.
12. Structurally incomplete success reports are rejected before reminder
   delivery.
13. A live processing lease blocks a concurrent duplicate maintenance run.
14. A crash after derived work but before staging is retryable without any
   canonical effect.
15. An expired lease fences the old worker before report publication.

## TESTS EXECUTED

- Focused W-07B: **15 passed**.
- Existing native/maintenance/session/capture focus: **100 passed**.
- Full regression at exact documentation head `72e038a` (code/test head
  `f322d2c`): **1172 passed, 2
  warnings**.
- Critical flake8 (`E9,F63,F7,F82`) on touched runtime/test files: PASS.
- `compileall` on touched runtime/test files: PASS.
- `git diff --check`: PASS.

The two warnings are existing FastAPI/Starlette deprecation warnings; no new
failure or warning gate was introduced by W-07B.

## QUALITY METRICS BEFORE / AFTER

| Dimension | Before W-07B | After evidence |
|---|---:|---:|
| Capture runtime | 8.5/10 | 8.5/10 pending independent review |
| Native maintenance delivery | 0/10 (not connected) | 7.5/10 evidence-complete locally; acceptance pending |
| SessionStart reminder quality | 0/10 (not delivered) | 7.0/10 bounded projection tested; native dogfood pending |

The core audit score is not promoted by local implementation tests alone.

## SAFETY METRICS

- Stop-created maintenance intents: **0** in focused tests.
- Duplicate intent for one event: **0 additional intents**.
- Crash-after-publication duplicate maintenance run: **0**.
- Cross-project reminder delivery: **0**.
- Corrupt report injection: **0**.
- Raw private content in durable projected report: **0** in focused tests.
- Canonical MemoryStore/StateStore revision change during failure: **0**.
- Canonical write path added by W-07B: **0**.

## KNOWN LIMITATIONS

- A real Claude and Codex executable run with an isolated vault has not yet
  been attached to this package evidence.
- Service-loop asynchronous execution is covered structurally and through the
  delivery worker tests, but a process-level restart/kill harness is still
  required for final acceptance.
- Native latency and a multi-session dogfood sample are not measured here.
- Lease expiry fencing is covered at exact implementation head `f322d2c`; a
  stale worker cannot publish after a second worker recovers the intent.
- A crash after `run_maintenance()` returns but before safe staging causes a
  retry of derived work; the retry is bounded and canonical-store safe, but
  exactly-once derived execution across that window is not yet proven.
- The manual `session_pipeline.py` path remains intentionally separate and is
  covered only by its existing parity suite.

## OPEN FAILURES

- No known production test failure.
- Independent read-only review of code/test head `f322d2c3cc341f6e394b5d950d55f49c1322a1c1`
  returned `FIX-FIRST`; the reviewer confirmed the owner-fencing hardening.
- Native executable smoke, process restart/kill and latency/dogfood evidence
  remain open acceptance gates.

## INDEPENDENT REVIEW

Independent read-only review of exact code/test head `f322d2c` returned
**FIX-FIRST**. The reviewer confirmed the lease, strict report validation,
bounded error logging, owner fencing and new tests, while keeping the native,
process and latency/dogfood gates open.

## SCORE BEFORE / AFTER

- Capture runtime: **8.5 → 8.5 pending native evidence**
- W-07B maintenance delivery: **unscored → provisional 8.0/10**
- Daily-use reminder delivery: **unscored → provisional 7.5/10**

## VERDICT

**FIX-FIRST / NOT ACCEPTED**

The implementation and evidence commits are pushed, but W-07B remains open
because the independent exact-head verdict is `FIX-FIRST` and native/process
and latency/dogfood evidence are still required. Phase 20 remains FROZEN /
LOCKED and V2 remains SHADOW.
