# W-07B Claude Native Hook Latency Matrix Evidence Report

**PACKAGE:** W-07B evidence closure (Claude side of the "Latency" section only)

**REVISION:** repository HEAD at execution time is `f769ddb`;
`evals/w07b/latency_matrix.py` is the harness bound to this evidence.

**PLAN:** `docs/history/plans/WEAKNESS-W07B-NATIVE-ACCEPTANCE-EVIDENCE-PLAN.md`,
section "Latency"

**STATUS:** FIX-FIRST / NOT ACCEPTED (unchanged — this narrows, not closes,
`NATIVE_LATENCY_MATRIX_MISSING`)

**PHASE 20:** FROZEN / LOCKED — **V2:** SHADOW

## OBJECTIVE

Measure p50/p95 native hook latency for the Claude side of the required
matrix (`Claude × {SessionStart, UserPromptSubmit, Stop, SessionEnd} ×
{cold, warm}`, ≥5 samples per cell) against a real, authenticated `claude`
executable and an isolated vault/config, reusing the isolation method proven
in `WEAKNESS-W07B-CLAUDE-ISOLATED-SMOKE-EVIDENCE-REPORT.md`. No production
code, hook configuration, canonical data or live client config was changed.

## FILES CHANGED

- `evals/w07b/latency_matrix.py` (new) — reusable harness. Same
  isolation as `evals/w07b/native_smoke.py` (throwaway vault/config via
  `tempfile.TemporaryDirectory`, `--settings`/`--setting-sources ""`, real
  `claude` executable). Reads only the runtime's own recorded `elapsed_ms`:
  `SessionStart`/`UserPromptSubmit` from their per-key `deliveries/*.json`
  record's `hook_elapsed_ms` field (identified precisely via the runtime's
  own `identity()` hashing, not guessed), `Stop`/`SessionEnd` from
  `last-hook.json` via a short-lived polling thread (started fresh per
  invocation and seeded with whatever is already on disk, so a stale entry
  left by a *previous* invocation is never recounted — see "Known
  limitations" for the bug this fixes). Never reads prompt or transcript
  content.
- `evals/w07b/2026-09-22-latency-matrix-run.json` (new) — the raw report
  from the final run.

## ROOT CAUSES ADDRESSED

`NATIVE_LATENCY_MATRIX_MISSING` had no data at all. This step produces real
p50/p95 numbers for the Claude side, against the existing fixed budgets
(3 s per-hook timeout, 2.2 s `SessionStart` service-wait budget within the
2.5 s internal deadline — `brain_eleven/runtime/install.py`,
`brain_eleven/runtime/launcher.py`), without loosening either.

## Cold/warm definition (stated explicitly, since the plan does not fully
## specify it for events other than SessionStart)

Cold/warm is architecturally meaningful only for `SessionStart`: its hook
calls `ensure_service(wait=True)` and may have to boot the background
FastAPI service from nothing. Once `SessionStart` has run inside a given
`claude -p` process, that same process's later `UserPromptSubmit`/`Stop`/
`SessionEnd` hooks always find the service already running — there is no
way, via the public CLI, to force an independent cold state for those three
events without also making `SessionStart` cold in the same run. This report
therefore measures:

- `SessionStart`: 5 **cold** samples (service explicitly stopped via
  `POST /api/runtime/stop` before each) and 5 **warm** samples (service left
  running from the previous sample).
- `UserPromptSubmit`, `Stop`, `SessionEnd`: 10 **warm-only** samples each
  (one per invocation across both the cold-SessionStart and warm-SessionStart
  runs), reported without a separate cold figure. This is a stated
  limitation, not a fabricated cold value.

## TESTS EXECUTED

`python -m evals.w07b.latency_matrix`, 10 real authenticated `claude -p`
invocations (5 with the service stopped beforehand, 5 with it left running),
each against the same isolated vault/config. `flake8 --select=E9,F63,F7,F82`
and `compileall` on the new files: **PASS**.

Final run (`evals/w07b/2026-09-22-latency-matrix-run.json`):

| Event | Cold p50 / p95 (ms) | Warm p50 / p95 (ms) | n (cold / warm) | Existing budget |
|---|---|---|---|---|
| SessionStart | 1365 / 1385 | 174 / 193 | 5 / 5 | 3000 ms hook timeout; 2200 ms service-wait sub-budget |
| UserPromptSubmit | — (see above) | 218.5 / 235 | — / 10 | 3000 ms hook timeout |
| Stop | — | 102.0 / 121 | — / 10 | 3000 ms hook timeout |
| SessionEnd | — | 99.5 / 107 | — / 10 | 3000 ms hook timeout |

All measured p95 values are comfortably inside the existing 3-second hook
timeout; cold `SessionStart` p95 (1385 ms) is inside its 2200 ms service-wait
sub-budget plus its own request/response overhead, consistent with the
existing `test_cold_native_session_start_delivers_v1_within_hook_budget`
timing test's 3-second assertion. No budget was loosened or evaluated
against a relaxed figure.

## SAFETY METRICS

Identical isolation guarantees as the prior isolated-smoke evidence step:
live global `~/.claude/settings.json` is never targeted by `install()` (a
fresh throwaway `home` is used) and this repository's own project-local
`.claude/settings.json` is excluded via `--setting-sources ""`. Only
synthetic, content-free prompts were used. No canonical write occurred (the
isolated vault stayed in `SHADOW`, the install default). Temporary vault and
client config were removed by `tempfile.TemporaryDirectory` on every run.

## KNOWN LIMITATIONS

- **A harness bug was found and fixed during this step, not after.** The
  first version of the `Stop`/`SessionEnd` poller seeded its dedup set as
  empty at start, so if the next invocation's poller began sampling before
  the runtime had overwritten `last-hook.json` with a fresh event, it
  recorded the *previous* invocation's stale entry as a new sample — the
  first full run reported 19 `SessionEnd` samples from only 10 invocations.
  Seeding the dedup set with whatever is already on disk at poller start
  fixed it; the corrected run shows exactly 10/10 for `Stop` and
  `SessionEnd`, matching one event per invocation. This report is the
  corrected run only; the inflated run's output was discarded, not archived.
- `UserPromptSubmit`/`Stop`/`SessionEnd` cold latency is not measured — see
  the cold/warm definition above for why the public CLI cannot produce it
  independently of `SessionStart`.
- Codex side entirely unmeasured — no `codex` executable exists in this
  environment (same limitation as the isolated-smoke evidence step).
- Single machine, single `claude` version (`2.1.278`), one session, ten
  invocations. Not a statistically large sample; p95 over n=5/10 is a rough
  tail estimate, not a tight bound.

## OPEN FAILURES

- `NATIVE_LATENCY_MATRIX_MISSING` — **narrowed, not closed**: the Claude
  half now has real p50/p95 data for all four events; the Codex half remains
  entirely unmeasured (`BOUNDED_UNVERIFIED_CODEX_BINARY_MISSING`, same as
  the isolated-smoke report), and cold `UserPromptSubmit`/`Stop`/
  `SessionEnd` are architecturally unavailable via the public CLI as
  explained above.
- `NATIVE_CODEX_TRUST_UNVERIFIED` / `NATIVE_DOGFOOD_SAMPLE_MISSING` —
  unchanged, out of this step's scope.

W-07B remains `FIX-FIRST / NOT ACCEPTED`; no V2 promotion or Phase 20 unlock
is implied.

## INDEPENDENT REVIEW

**PENDING — not yet independently reviewed.** Self-executed within one
session; self-review is not acceptance. A separate reviewer should verify
the isolation claims, the poller's corrected dedup logic against the raw
`evals/w07b/2026-09-22-latency-matrix-run.json` output, and the stated
cold/warm scope before this step is treated as closed.

## SCORE BEFORE / AFTER

W-07B native maintenance delivery: **7.5 → 7.5 provisional**, unchanged. The
plan's acceptance gate requires the full matrix (including Codex) before the
package score can move.

## VERDICT

**FIX-FIRST / NOT ACCEPTED** — Claude-side latency data now exists and is
within the existing fixed budgets; Codex-side latency, cold measurements for
three of the four events, and the dogfood sample remain required.
