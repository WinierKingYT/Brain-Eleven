# W-07B Native Maintenance and Reminder Delivery — Package Report

**PACKAGE:** W-07B  
**REVISION:** `8b18d66` (final evidence head; implementation `94f331f`, recovery `44dfe43`)
**STATUS:** REVIEW PENDING / NOT ACCEPTED  
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

Eleven focused tests in `tests/test_w07b_maintenance_delivery.py` cover:

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

## TESTS EXECUTED

- Focused W-07B: **11 passed**.
- Existing native/maintenance/session/capture focus: **66 passed**.
- Full regression at implementation + test exact head: **1168 passed, 2
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

- The focused suite uses deterministic worker/runtime fixtures; a real Claude
  and Codex executable run with an isolated vault has not yet been attached to
  this package evidence.
- Service-loop asynchronous execution is covered structurally and through the
  delivery worker tests, but a process-level restart/kill harness is still
  required for final acceptance.
- Native latency and a multi-session dogfood sample are not measured here.
- The manual `session_pipeline.py` path remains intentionally separate and is
  covered only by its existing parity suite.

## OPEN FAILURES

- No known production test failure.
- Native executable smoke, process restart/kill evidence, latency evidence,
  and independent read-only review remain open acceptance gates.

## INDEPENDENT REVIEW

Not yet performed. A self-review is not an independent review and cannot
close this package.

## SCORE BEFORE / AFTER

- Capture runtime: **8.5 → 8.5 pending review**
- W-07B maintenance delivery: **unscored → provisional 7.5/10**
- Daily-use reminder delivery: **unscored → provisional 7.0/10**

## VERDICT

**REVIEW PENDING / NOT ACCEPTED**

The implementation and evidence commits are pushed, but W-07B remains open
until exact final head `8468b32` receives an independent read-only verdict of
`SHIP`, `FIX-FIRST`, or `RETHINK` and the remaining native/process evidence is
addressed.
