# W-07B R1 Evidence Harness Report

**PACKAGE:** W-07B-R1 evidence harness repair

**REVISION:** `ca15e31eb5bf3ab987246b3f2b5ce8dd5bed06f3`

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
  native-shaped synthetic records, bounded hook status fields, the complete
  synthetic client/event/phase matrix and explicit benchmark gates.
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

Seven focused tests cover hook-status mapping without retaining output,
disposable transcript-root configuration for both clients, the explicit
`all_hooks_ok` failure gate and the complete matrix contract.

## TESTS EXECUTED

- W-07B focused suite (`test_w07b_r1_evidence.py`, process recovery,
  maintenance delivery and stale-reminder safety): **47 passed**.
- W-06C0R1 scope contract suite: **36 passed**.
- Full regression at this exact revision: **1345 passed, 4 skipped, 2
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
| canonical revision delta | +20 |
| latency matrix cells | 16/16, 5 samples per cell |
| maximum matrix p95 | 2,695.03 ms |
| cold SessionStart statuses | Claude 4 `DEGRADED`/1 `OK`; Codex 4 `DEGRADED`/1 `OK` |
| cold UserPromptSubmit statuses | Claude 5 `DEGRADED`; Codex 5 `DEGRADED` |
| matrix queue terminal verification | drained `true`; expected/delta `40/40` |
| queue p95 / max | gate remains `false` (over 30 s) |

Gates: `no_dead_letters=true`, `singleton=true`,
`canonical_effect_verified=true`, `latency_matrix_complete=true`,
`latency_matrix_p95_3000ms=true`, `latency_matrix_queue_drained=true` and
`latency_matrix_terminal_verified=true`; `hook_p95_500ms=false`,
`queue_30s=false` and `all_hooks_ok=false`. Overall synthetic benchmark status is **FAIL**,
which keeps the observed latency/degraded-hook condition visible. The matrix
is complete as synthetic evidence; it is not authenticated native-client
evidence.

## QUALITY METRICS BEFORE / AFTER

| Gate | Before R1 | After R1 |
| --- | --- | --- |
| Synthetic capture benchmark | Raised on first ownership rejection; no report | Completes 20 events and emits bounded report |
| Hook degradation visibility | Hidden by exception | Explicit status counts and failing gate |
| Native authenticated Claude trust | Unverified | Unverified |
| Native authenticated Codex trust | Unverified | Unverified |
| Required 2×4 cold/warm latency matrix | Missing | Complete synthetic 16-cell matrix; native execution remains unverified |
| Multi-session dogfood | Missing | Missing |

## SAFETY METRICS

- Canonical authority or production runtime writes introduced: **0**.
- Synthetic canonical effects are confined to a temporary vault and are
  deleted with the harness: **yes**.
- Raw prompt, transcript, token or exception content in evidence: **0**.
- Live vault/config mutation: **0**.
- Queue completion without canonical verification in this benchmark: **0**;
  all 20 completed records were verified by a +20 canonical record delta and
  +20 canonical revision delta before the report was emitted.

## KNOWN LIMITATIONS

This is an evidence-harness repair, not native-client acceptance. The
benchmark now covers all required synthetic Claude/Codex ×
`SessionStart`/`UserPromptSubmit`/`Stop`/`SessionEnd` × cold/warm cells, but the
matrix invokes the disposable launcher rather than authenticated native
executables. The measured queue and hook latency gates currently fail.
Authenticated isolated Claude and Codex execution, privacy-safe multi-session
dogfood and a fresh independent review of this revision remain outstanding.

## OPEN FAILURES

- `NATIVE_CLAUDE_TRUST_UNVERIFIED`
- `NATIVE_CODEX_TRUST_UNVERIFIED`
- `NATIVE_LATENCY_MATRIX_UNVERIFIED`
- `SYNTHETIC_QUEUE_LATENCY_GATE_FAILED`
- `SYNTHETIC_PROMPT_HOOK_DEGRADED`
- `NATIVE_DOGFOOD_SAMPLE_MISSING`

W-07B remains `FIX-FIRST / NOT ACCEPTED`; no V2 promotion or Phase 20 unlock
is implied.

## INDEPENDENT REVIEW

The independent review found two harness P1s and two P2s: degraded responses
could be misclassified as `OK`, a failed cold stop could be counted as a valid
cold sample, an HTTP protocol error could abort cleanup, and a queue polling
protocol/schema failure could suppress the report. All four are now
bounded/fail-closed; matrix queue drain and terminal deltas are explicit gates.
A fresh independent read-only review is required for this revision, while
native trust and dogfood gaps remain. Self-review is not an acceptance verdict.

## SCORE BEFORE / AFTER

W-07B runtime acceptance: **7.5 → 7.5 provisional**. The repaired harness
improves evidence quality but does not satisfy the native trust, complete
latency or dogfood gates.

## VERDICT

**FIX-FIRST / NOT ACCEPTED** — evidence reporting and the synthetic matrix are
repaired; authenticated native trust, native quality and dogfood gates remain
open.
