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

## 2026-09-28 exact-head follow-up

**Harness revision:** `c85d67b14358aea34c7d0c546f81cf7c8c1d4ff9`.
**Implementation baseline:** `5c7d91346297e02ee0fffa884033692bbd795740`.

One isolated Claude smoke repetition ran on the exact harness revision above.
The real CLI returned exit code `1`, while a fresh session ID was present and
the isolated capture ledger reached `ENQUEUED → CLAIMED → PROCESSING →
COMMITTED` once. One review item was present, the canonical memory revision
was unchanged, and the live global settings hash was unchanged. Because the
client exited non-zero, this is recorded as
`BOUNDED_UNVERIFIED_CLAUDE_CLI_EXIT_1`, not as verified native trust. No prompt,
transcript, exception text, credential or absolute path is included in this
evidence report.

The first attempt on this baseline exposed an evidence-harness cleanup defect:
the background service remained alive when Windows removed the temporary
vault. `native_smoke.py` now stops the service in a `finally` block by reusing
the W-07B latency harness's existing bounded stop helper. The exact-head
follow-up produced a structured report and no cleanup error; a process check
found no remaining process tied to a W-07B temporary vault. This changes only
the evidence helper, not production runtime behavior or canonical data.

Codex CLI `0.158.0-alpha.2.1` is present and the host login status is
authenticated, but an isolated `CODEX_HOME` does not have authentication. No
Codex smoke was attempted; status is
`BOUNDED_UNVERIFIED_CODEX_ISOLATED_AUTH_UNAVAILABLE`. Host-level login status
does not substitute for isolated native evidence.

The earlier Claude latency and dogfood reports remain bound to their stated
older revisions. No current-baseline latency or dogfood matrix was run here.
W-07B remains **FIX-FIRST / NOT ACCEPTED**; the Claude non-zero exit, isolated
Codex authentication, current-baseline latency/dogfood evidence and
independent review remain open.

## 2026-09-28 Claude dogfood and latency follow-up

**Dogfood harness source:** `d5565ddb8b9d90a678051ae537b76ece3e0aeec6`.
**Latency cleanup fix:** `3e37357be39b34a3cdc0e586928420e2f5ad8e3c`.
**Implementation baseline:** `5c7d91346297e02ee0fffa884033692bbd795740`.

The isolated Claude dogfood harness completed five sessions and twenty
synthetic turns across two projects, observed the project switch, and recorded
session IDs for all five sessions. Every turn returned CLI exit code `1` and
`is_error=true` (`all_turns_ok=false`). The capture ledger's cumulative
`COMMITTED` count advanced by four after each session, ending at twenty; each
session added four review items. The worker reported `QUEUED`, and the
canonical memory revision stayed at `0`. This confirms the isolated capture
and handoff path for these turns, but is not authenticated client success or a
passing dogfood sample. No prompt, transcript, exception text, credential or
absolute path is recorded.

A separate sanitized one-turn diagnostic returned `api_error_status=429`,
`exit_code=1`, and `is_error=true`, identifying a provider rate-limit/quota
response for that diagnostic. The dogfood harness did not record API status
per turn, so this single status is not attributed to all twenty failures.
Native Claude trust remains unverified until a successful client call can be
captured after the rate limit clears.

| Claude hook event | Samples | p50 (ms) | p95 (ms) | Status |
| --- | ---: | ---: | ---: | --- |
| SessionStart, cold | 5 | 1971 | 1984 | measured |
| SessionStart, warm | 5 | 669 | 675 | measured |
| UserPromptSubmit, warm | 10 | 685 | 728 | measured |
| Stop, warm | 0 | — | — | missing |
| SessionEnd, warm | 10 | 567.5 | 599 | measured |

The corrected latency command exited `0`, but its current exit condition checks
only the SessionStart sample counts. Stop latency remains unmeasured, and the
dogfood CLI failures keep native Claude trust unverified. As documented in the
plan, cold UserPromptSubmit/Stop/SessionEnd samples are unavailable through
the public CLI because SessionStart starts the service for the invocation.

The first latency attempt failed during Windows temporary-vault cleanup before
it emitted metrics. `latency_matrix.py` now calls its bounded service-stop
helper in `finally`; the corrected run emitted the values above. The service
from the failed attempt was stopped, though its temporary directory remains
after automatic review rejected recursive removal. No process for that run
remains active.

W-07B remains **FIX-FIRST / NOT ACCEPTED**. Native Claude CLI success,
complete Stop latency, isolated Codex authentication/evidence, and independent
review remain open. No production runtime, canonical data, Phase 20 state, or
V2 mode was changed.

## 2026-09-28 exact-current-baseline recovery and regression rerun

**Implementation baseline:** `5c7d91346297e02ee0fffa884033692bbd795740`.
**Evidence head:** `23e97ea97b386ae148271ba3506c413605658939`.

The earlier process-recovery evidence was tied to `78c5671`. The current
baseline contains later changes in the runtime, worker, service, capture,
memory and state dependency graph, so that earlier result was not treated as
current. At the exact baseline/head above, the deterministic process-recovery
matrix passed **18/18** (`tests/test_w07b_process_recovery.py`, 22.32 seconds),
covering the named worker/service crash boundaries and repeated recovery.
The full local regression at the same evidence head passed **1715 tests**;
pytest reported **4 skipped**. No test, skip marker or quarantine was added
or changed for this work.

Matching remote evidence on head `23e97ea97b386ae148271ba3506c413605658939`:
Validation run `36390515458` completed successfully, including unit,
coverage, security, integration and phase checks. PRE-13 runtime-gates run
`36390515424` completed with failure only at the frozen `quality` holdout
measurement; Ubuntu and Windows runtime jobs passed. The holdout and its
threshold were not changed.

This closes the current-base process-recovery and local-regression evidence
gaps only. It does not satisfy the native Claude/Codex trust, complete
two-client latency, successful dogfood, or separate-review acceptance gates.
W-07B remains **FIX-FIRST / NOT ACCEPTED**.

## 2026-09-28 Claude history isolation audit

A review of the Claude evidence subprocesses found that earlier runs passed a
temporary `--settings` file but did not set `CLAUDE_CONFIG_DIR`. Claude Code
stores session history under that config directory, so those runs do not prove
that client-side session records stayed out of the host profile. The dogfood
prompts were synthetic; no prompt or transcript content was copied into this
report. Those earlier Claude smoke, latency and dogfood results are not counted
as privacy-verified evidence, and the host profile was not inspected or
modified.

The evidence harness now sets `CLAUDE_CONFIG_DIR` to the throwaway client home
for every Claude subprocess through `evals/w07b/client_process.py`; native
smoke, latency and dogfood all use that helper. Its focused isolation test
passed (**1 passed**), and the updated harness modules compile. This fixes the
evidence path only; no native call was made with the corrected isolation, so
the Claude trust, latency and dogfood gates remain open. The current provider
rate limit and isolated Codex sign-in are still prerequisites for those runs.

## 2026-09-28 isolated Codex smoke harness preparation

The Codex evidence harness now runs only with a `CODEX_HOME` under the
system temporary directory and reads its transcript from that isolated
profile. Code-graph inspection confirmed that the completed queue job stores
terminal status and event identity, while effect details are written to a
separate `EFFECT_VERIFIED` capture receipt. The harness now validates that
receipt against the job and event IDs before reading its bounded review-effect
IDs; it no longer assumes the terminal job contains a result payload.

Focused evidence-harness tests passed (**5 passed**), the updated harness
modules compiled, and `git diff --check` passed. No authenticated Codex smoke
has run yet. The temporary profile still requires sign-in and explicit review
of its installed hook definitions before native evidence can be counted.
W-07B remains **FIX-FIRST / NOT ACCEPTED**.
