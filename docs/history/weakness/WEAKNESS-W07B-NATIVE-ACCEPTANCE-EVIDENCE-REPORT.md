# W-07B Native Acceptance Evidence Report

**PACKAGE:** W-07B evidence closure

**REVISION:** `78c5671`

**PROCESS TEST REVISION:** `b7f8ca312a044aacf474ff404cb251e5bd0e33`

**IMPLEMENTATION UNDER TEST:** `f322d2c` (W-07B runtime package)

**STATUS:** FIX-FIRST / NOT ACCEPTED

**PHASE 20:** FROZEN / LOCKED — **V2:** SHADOW

## OBJECTIVE

Close the remaining W-07B acceptance evidence without changing runtime
implementation, hook configuration or canonical data. This report covers the
new process-level recovery evidence and records the still-unavailable native
authenticated client gate.

## FILES CHANGED

- `tests/test_w07b_process_recovery.py` — test-only deterministic child
  process termination at claim, staging, publication and final-receipt
  boundaries.
- `WEAKNESS-W07B-NATIVE-ACCEPTANCE-EVIDENCE-PLAN.md` — approved evidence
  contract and exact-revision rules.

No production file, live vault, live Claude/Codex configuration, canonical
store or Phase 20/V2 setting was changed.

## ROOT CAUSES ADDRESSED

The prior W-07B package had focused fault tests but no process-level proof that
a worker/service restart after a durable intent boundary recovers exactly one
report. The harness uses named child-process seams rather than timing sleeps
and verifies recovery after actual process termination.

## TESTS ADDED

Five process-level scenarios cover:

1. worker crash after durable intent write;
2. worker crash after lease/claim;
3. worker crash after staging;
4. worker crash after report publication before terminal move;
5. restart of the real service process after final receipt as a no-op.

Each crash boundary is exercised in three independent repetitions. Recovery
asserts one eventual report/receipt and unchanged MemoryStore/StateStore
revisions; staging recovery also asserts no staging residue. A controlled raw
maintenance result is used only inside the test child; it is not a production
path.

## TESTS EXECUTED

- Process recovery harness: **18 passed** (five scenarios, three repetitions
  for each boundary, plus the in-process final-receipt no-op coverage).
- W-07B/native/capture/runtime focused suite at exact evidence head:
  **133 passed, 2 warnings**.
- Full regression at exact committed evidence head `78c5671`:
  **1291 passed, 4 skipped, 2 warnings**.
- The warnings are existing FastAPI/Starlette deprecations.
- Critical flake8 (`E9,F63,F7,F82`) on the new test: **PASS**.
- `compileall` and `git diff --check`: **PASS**.

## NATIVE CLIENT GATE

The installed executables are present (`Claude Code 2.1.268`, `Codex CLI
0.154.0-alpha.6.2`). The prior isolated real-client smoke remains the latest
authenticated evidence: hooks were loaded and invoked, but Claude stopped for
missing API authentication and Codex stopped for missing network
authentication before a client-owned transcript reached the queue. No new
live-client run was performed in this evidence-only step, so native trust is
not relabeled as verified. The required next run must use authenticated
isolated configurations and record only content-free bounded telemetry.

## QUALITY METRICS BEFORE / AFTER

| Gate | Before | After this evidence step |
| --- | --- | --- |
| Process restart/kill recovery | Missing | 18 deterministic boundary repetitions pass |
| Native authenticated Claude capture | Unverified | Unverified |
| Native authenticated Codex capture | Unverified | Unverified |
| Latency matrix | Missing | Missing |
| Multi-session dogfood | Missing | Missing |

## SAFETY METRICS

- Canonical MemoryStore/StateStore/ProjectRegistry writes introduced: **0**.
- Canonical revision change during crash/restart tests: **0**.
- Duplicate report/receipt after recovery: **0**.
- Raw prompt, transcript, token or exception content persisted: **0**.
- Live vault/config mutation: **0**.

## KNOWN LIMITATIONS

Authenticated real-client execution requires credentials/network access that
were unavailable in the existing isolated smoke. Native latency and the
multi-session project dogfood matrix are still absent. The process harness
proves the durable delivery protocol, not client authentication or product
quality.

## OPEN FAILURES

- `NATIVE_CLAUDE_TRUST_UNVERIFIED`
- `NATIVE_CODEX_TRUST_UNVERIFIED`
- `NATIVE_LATENCY_MATRIX_MISSING`
- `NATIVE_DOGFOOD_SAMPLE_MISSING`

W-07B remains `FIX-FIRST / NOT ACCEPTED`; no V2 promotion or Phase 20 unlock
is implied.

## INDEPENDENT REVIEW

**FIX-FIRST.** Independent read-only review at report HEAD verified the
process evidence and exact counts. The first four crash tests invoke the
delivery API directly inside deterministic child processes rather than the
full native `Worker` object path; existing W-07B worker tests cover that
trigger path separately. This remains a bounded evidence limitation, not a
new production failure. Native trust, latency and dogfood gates remain open;
self-review is not acceptance.

## SCORE BEFORE / AFTER

W-07B native maintenance delivery: **7.5 → 7.5 provisional**. Process
recovery evidence improves confidence but does not raise the program score
until native trust, latency and dogfood gates pass.

## VERDICT

**FIX-FIRST / NOT ACCEPTED** — process recovery is evidenced; authenticated
native client, latency and dogfood evidence remain required.
