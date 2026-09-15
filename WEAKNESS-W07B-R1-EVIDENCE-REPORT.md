# W-07B R1 Evidence Harness Report

**PACKAGE:** W-07B-R1 evidence harness repair

**REVISION:** `6acfe9e0a71636a6dcaf406c31f32964be2bbc54`

**IMPLEMENTATION UNDER TEST:** W-07B runtime at `f322d2c`

**STATUS:** FIX-FIRST / NOT ACCEPTED

**PHASE 20:** FROZEN / LOCKED — **V2:** SHADOW

## OBJECTIVE

Repair the synthetic process benchmark so it exercises transcript ownership
and reports degraded hook output instead of raising before measurements are
written. This package changes evidence tooling and tests only; it does not
promote W-07B, V2 or Phase 20.

## FILES CHANGED

- `evals/runtime_benchmark.py` — disposable Claude/Codex transcript roots,
  native-shaped synthetic records, bounded hook status fields and explicit
  benchmark gates.
- `tests/test_w07b_r1_evidence.py` — focused checks for status mapping,
  transcript-root binding and visible failure gates.

No production runtime, hook configuration, live vault, canonical store,
credential or prompt/transcript content was changed or persisted.

## ROOT CAUSES ADDRESSED

The former benchmark wrote transcripts outside configured roots, so the
ownership guard rejected the first event and the harness raised without a
report. It also treated any non-empty hook response as an exception, hiding
latency and degradation counts. The repaired harness binds both clients to
temporary roots, emits client-shaped records and records bounded status codes.

## TESTS ADDED

Three focused tests cover hook-status mapping without retaining output,
disposable transcript-root configuration for both clients, and the explicit
`all_hooks_ok` failure gate.

## TESTS EXECUTED

- W-07B focused suite (`test_w07b_r1_evidence.py`, process recovery and
  maintenance delivery): **36 passed**.
- W-06C0R1 scope contract suite: **23 passed**.
- Full regression at this exact revision: **1342 passed, 4 skipped, 2
  existing dependency warnings**.
- Critical flake8 (`E9,F63,F7,F82`), `compileall` and `git diff --check`:
  **PASS**.

## SYNTHETIC BENCHMARK RESULT

Command parameters were `samples=20`, `records=1000` in a disposable vault.
Only timings, counts and status codes were emitted:

| Measure | Result |
| --- | ---: |
| completed canonical effects | 20/20 |
| dead-letter files | 0 |
| singleton service | true |
| Stop p95 | 541.95 ms |
| UserPromptSubmit p95 | 959.08 ms |
| queue p95 | 70,106.58 ms |
| queue max | 75,177.31 ms |
| Stop statuses | 20 `OK` |
| UserPromptSubmit statuses | 18 `OK`, 2 `DEGRADED` |

Gates: `no_dead_letters=true`, `singleton=true`; `hook_p95_500ms=false`,
`queue_30s=false`, `all_hooks_ok=false`. Overall synthetic benchmark status is
**FAIL**, which is the intended visible result for an unmet latency/degraded
hook condition.

## QUALITY METRICS BEFORE / AFTER

| Gate | Before R1 | After R1 |
| --- | --- | --- |
| Synthetic capture benchmark | Raised on first ownership rejection; no report | Completes 20 events and emits bounded report |
| Hook degradation visibility | Hidden by exception | Explicit status counts and failing gate |
| Native authenticated Claude trust | Unverified | Unverified |
| Native authenticated Codex trust | Unverified | Unverified |
| Required 2×4 cold/warm latency matrix | Missing | Still missing; two-event synthetic timing is recorded |
| Multi-session dogfood | Missing | Missing |

## SAFETY METRICS

- Canonical authority or production runtime writes introduced: **0**.
- Synthetic canonical effects are confined to a temporary vault and are
  deleted with the harness: **yes**.
- Raw prompt, transcript, token or exception content in evidence: **0**.
- Live vault/config mutation: **0**.
- Queue completion without canonical verification in this benchmark: **0**;
  all 20 completed records were counted from the canonical completion folder.

## KNOWN LIMITATIONS

This is an evidence-harness repair, not native-client acceptance. The
benchmark covers synthetic `Stop` and `UserPromptSubmit` events only; it does
not provide the required Claude/Codex `SessionStart`/`SessionEnd` cold/warm
matrix. The measured queue and hook latency gates currently fail. Authenticated
isolated Claude and Codex execution, privacy-safe multi-session dogfood and an
independent review remain outstanding.

## OPEN FAILURES

- `NATIVE_CLAUDE_TRUST_UNVERIFIED`
- `NATIVE_CODEX_TRUST_UNVERIFIED`
- `NATIVE_LATENCY_MATRIX_INCOMPLETE`
- `SYNTHETIC_QUEUE_LATENCY_GATE_FAILED`
- `SYNTHETIC_PROMPT_HOOK_DEGRADED`
- `NATIVE_DOGFOOD_SAMPLE_MISSING`

W-07B remains `FIX-FIRST / NOT ACCEPTED`; no V2 promotion or Phase 20 unlock
is implied.

## INDEPENDENT REVIEW

The first independent review returned `FIX-FIRST` with one P1: unhandled
`TimeoutExpired` could still suppress a report. That path is now bounded as a
`TIMEOUT` status at this revision; a fresh read-only re-review is pending.
Self-review is not an acceptance verdict.

## SCORE BEFORE / AFTER

W-07B runtime acceptance: **7.5 → 7.5 provisional**. The repaired harness
improves evidence quality but does not satisfy the native trust, complete
latency or dogfood gates.

## VERDICT

**FIX-FIRST / NOT ACCEPTED** — evidence reporting is repaired; the remaining
native and quality gates are still open.
