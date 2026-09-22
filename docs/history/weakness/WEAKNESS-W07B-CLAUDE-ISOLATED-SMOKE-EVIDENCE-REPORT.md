# W-07B Claude Isolated Native Smoke Evidence Report

**PACKAGE:** W-07B evidence closure (Claude side of the "Isolated native
smoke" section only)

**REVISION:** `9200a75` (repository HEAD at execution time; `evals/w07b/native_smoke.py`
is the harness bound to this evidence)

**PLAN:** `docs/history/plans/WEAKNESS-W07B-NATIVE-ACCEPTANCE-EVIDENCE-PLAN.md`,
section "Isolated native smoke"

**STATUS:** FIX-FIRST / NOT ACCEPTED (unchanged — this closes one of four
open failures, not the package)

**PHASE 20:** FROZEN / LOCKED — **V2:** SHADOW

## OBJECTIVE

Close the Claude half of `NATIVE_CLAUDE_TRUST_UNVERIFIED` /
`NATIVE_CODEX_TRUST_UNVERIFIED` from the prior evidence report
(`WEAKNESS-W07B-NATIVE-ACCEPTANCE-EVIDENCE-REPORT.md`): prove that an
authenticated, real `claude` executable, invoked against an isolated vault
and an isolated client configuration, completes the full
hook → queue → terminal receipt → review-effect chain, verified by opaque ID
and revision rather than a bare `COMPLETED` queue row. No production code,
hook configuration, canonical data or live client config was changed.

## FILES CHANGED

- `evals/w07b/native_smoke.py` (new) — reusable harness. Builds a throwaway
  vault and a throwaway client config via `tempfile.TemporaryDirectory`
  (always removed, including on failure), installs the existing hook
  definitions into that throwaway config only (`brain_eleven.runtime.install.install`),
  invokes the real `claude` CLI with `--settings <isolated hooks>
  --setting-sources ""` so neither the live global `~/.claude/settings.json`
  nor this repository's own project-local `.claude/settings.json` is loaded,
  and verifies the queue/review/canonical outcome by ID. It is a manual,
  credential-gated script (like `evals/ig01d/*`); it is not collected by
  pytest and is not run by CI, since CI runners have no authenticated
  `claude` CLI.

No production runtime file, live vault, live client configuration, canonical
store or Phase 20/V2 setting was changed.

## ROOT CAUSES ADDRESSED

The prior evidence step recorded: "No new live-client run was performed in
this evidence-only step, so native trust is not relabeled as verified." This
step performs that run, for the Claude side, using this environment's own
already-authenticated `claude` CLI (`2.1.278`).

## TESTS ADDED

Not a pytest suite. `evals/w07b/native_smoke.py --repetitions N` is the
harness; each repetition is one full authenticated cycle: real `claude -p`
invocation → `Stop`/`SessionEnd` hooks fire → capture events enqueue → the
runtime's own background worker drains the queue → terminal state and
review-store effect are verified by ID.

## TESTS EXECUTED

Three repetitions, run twice (a 2-repetition set immediately followed by a
fresh 3-repetition harness run after the script was finalized — 5 authenticated
invocations in total across the session), each with a distinct synthetic,
content-free, decision-shaped prompt (no real user data). All five: exit code
`0`, a real assistant response (`is_error: false`), a fresh `session_id`.

Per-repetition queue lifecycle (cumulative counts across the run, confirmed
against the isolated vault's own capture ledger and the `completed/` and
`dead-letter/` directories): every enqueued capture event reached `ENQUEUED →
CLAIMED → PROCESSING → COMMITTED`, `dead-letter/` stayed empty throughout.

Final 3-repetition run (raw JSON: `evals/w07b/2026-09-22-isolated-smoke-run.json`,
produced by `python -m evals.w07b.native_smoke --repetitions 3 --report <path>`):

| Repetition | Exit | Elapsed | Ledger terminal counts | Review items (cumulative) | Canonical revision unchanged |
|---|---|---|---|---|---|
| 1 | 0 | ~9 s | ENQUEUED/CLAIMED/PROCESSING/COMMITTED = 2/2/2/2 | 1 | yes |
| 2 | 0 | ~11 s | 4/4/4/4 | 2 | yes |
| 3 | 0 | ~5 s | 6/6/6/6 | 3 | yes |

Each repetition's distinct synthetic content produced exactly one new,
distinctly-ID'd `PENDING` review item (`reason: REVIEW_REQUIRED`,
`candidate_type: NEW_MEMORY`) — the correct terminal effect for this
runtime's actual configured mode (`SHADOW`, install default), not a
canonical `MemoryStore` write. This is the same shape production capture
takes today; the harness does not run in `CANARY` (that would re-trigger the
holdout quality gate, out of scope here) and does not claim a canonical
memory write it did not produce.

`compileall` and `flake8 --select=E9,F63,F7,F82` on the new file: **PASS**.

## QUALITY METRICS BEFORE / AFTER

| Gate | Before | After this evidence step |
| --- | --- | --- |
| Native authenticated Claude capture | Unverified (prior smoke stopped on missing API auth) | **Verified**, bounded to isolated-vault SHADOW capture — 3/3 (this run) + 2/2 (prior run) repetitions, 5/5 clean |
| Native authenticated Codex capture | Unverified | Still unverified — `codex` executable is absent from this environment's `PATH` (only a stale `~/.codex/auth.json` remains); recorded as `BOUNDED_UNVERIFIED_CODEX_BINARY_MISSING`, not attempted |
| Process restart/kill recovery | 18 deterministic boundary repetitions pass (prior step) | Unchanged — out of this step's scope |
| Latency matrix | Missing | Still missing |
| Multi-session dogfood | Missing | Still missing |

## SAFETY METRICS

- Live global `~/.claude/settings.json` SHA-256 before and after every
  invocation: **identical** (`e46029ae…`), confirmed programmatically by the
  harness (a hash mismatch is a fatal script error, exit code 2).
- This repository's own project-local `.claude/settings.json` and
  `.brain-eleven/runtime/` state: unread and unwritten by the isolated runs
  (`--setting-sources ""` excludes project/local sources; the harness never
  sets `cwd` to this repository).
- Live vault (`C:\Users\faruk\Documents\Brain-Eleven`) `last-hook.json`
  timestamp: unchanged across the whole evidence session (checked before and
  after).
- Canonical `MemoryStore` revision in the isolated vault: `0` throughout —
  **0** canonical writes from any repetition.
- Raw prompt, transcript, token or exception content persisted in this
  report or in the harness's own ledger: **0** (the capture ledger records
  only hashed session/source identity; only the synthetic prompt text, which
  is safe by construction, appears in the harness source and the live
  `claude` process's own stdout/stderr, both scratch/ephemeral and not
  copied into this report).
- Temporary vault and client config: removed by `tempfile.TemporaryDirectory`
  on every run, including the two ad hoc pre-harness runs used to design the
  script (manually deleted immediately after inspection).

## KNOWN LIMITATIONS

- Bounded to `SHADOW` mode; a `CANARY`/`ACTIVE` canonical-write path was not
  exercised (would re-trigger the independent holdout quality gate, which is
  out of scope for this evidence step and already tracked separately).
- Five repetitions total is a smoke sample, not the latency matrix's
  required five cold **and** five warm samples per cell, and not the
  dogfood section's five-session/twenty-turn/two-project requirement. Both
  remain separate, larger, not-yet-executed sections of the same plan.
- Codex-side trust remains entirely unaddressed; this environment has no
  `codex` executable to invoke. That half of the plan's acceptance gate
  ("both real executable paths are `VERIFIED`") needs a session with an
  authenticated Codex CLI.
- Single machine, single `claude` version (`2.1.278`), single day.

## OPEN FAILURES

- `NATIVE_CODEX_TRUST_UNVERIFIED` (now more precisely
  `BOUNDED_UNVERIFIED_CODEX_BINARY_MISSING` — no `codex` executable on PATH
  in this environment)
- `NATIVE_LATENCY_MATRIX_MISSING`
- `NATIVE_DOGFOOD_SAMPLE_MISSING`

`NATIVE_CLAUDE_TRUST_UNVERIFIED` is resolved for the isolated-smoke scope
defined above and should be considered `VERIFIED` for that scope only.

W-07B remains `FIX-FIRST / NOT ACCEPTED`; no V2 promotion or Phase 20 unlock
is implied. Per the plan's own acceptance gate, W-07B cannot move until
**both** client paths are `VERIFIED`, so this step alone does not change the
package verdict.

## INDEPENDENT REVIEW

**PENDING — not yet independently reviewed.** This report was produced and
self-executed within one session; per this project's own convention,
self-review is not acceptance. A separate read-only reviewer should verify
the isolation claims (live-config hash check, `--setting-sources`
correctness, no live-vault write) and the terminal-effect verification
before this evidence step itself is treated as closed.

## SCORE BEFORE / AFTER

W-07B native maintenance delivery: **7.5 → 7.5 provisional**, unchanged.
Closing one of four open failures narrows the remaining gap but the plan's
own acceptance gate requires all four before the package score can move.

## VERDICT

**FIX-FIRST / NOT ACCEPTED** — Claude-side isolated native trust is now
evidenced for the scope above; Codex-side trust, the latency matrix and the
dogfood sample remain required and are not started.
