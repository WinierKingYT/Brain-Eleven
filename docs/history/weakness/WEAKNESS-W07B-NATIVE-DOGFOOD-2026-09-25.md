# W-07B native Claude/Codex dogfood evidence — 2026-09-25

**PACKAGE:** Roadmap stage 3, W-07B native client evidence and Codex transcript compatibility  
**IMPLEMENTATION REVISION:** `8140a48` (parent `19c8c89`)  
**DOGFOOD GATE:** PASSED for the isolated native-client scope below  
**PARENT W-07B ACCEPTANCE:** FIX-FIRST pending separate read-only review and the existing 500 ms hook target  
**PHASE 20 / V2:** FROZEN / SHADOW

## Objective and root cause

The original W-07B acceptance evidence had authenticated Claude smoke and
latency only. Codex trust, its latency cells and the two-client dogfood sample
were missing. A real Codex 0.155.0-alpha.16.4 invocation then exposed two
new transcript metadata records (`world_state`, `token_usage_record`) and a
`developer` message. The reader rejected the metadata as
`UNSUPPORTED_CODEX_TRANSCRIPT` and could have admitted developer text as
conversation evidence. The reader now skips known non-conversation records and
admits only user/assistant messages; unknown top-level records still fail
closed. The failed captures in the initial probe were also produced by a
background service started before this code change. Restarting it processed
the same native path successfully. Transcript session/project ownership
matched throughout; no ownership guard was weakened.

## Files changed

- `brain_eleven/runtime/evidence.py`: current Codex transcript compatibility.
- `evals/w07b/native_smoke.py`, `latency_matrix.py`, `dogfood.py`: isolated
  Claude/Codex native execution, receipt checks, latency and dogfood gates.
- `tests/test_w07b_codex_native_compat.py`,
  `tests/test_w07b_native_harness_gate.py`: fail-closed reader and harness
  regression tests.
- Six content-free JSON run reports under `evals/w07b/`.

Codex authentication was copied without parsing into disposable `CODEX_HOME`
directories. Hooks used the installed definitions with a one-invocation
trust override in that isolated home. The live vault and client settings were
not written. Three earlier exact Temp probe directories, including a copied
auth file, were removed after their paths were checked to be under Temp;
deletion is not recoverable. Disposable harness directories were removed by
their context managers.

## Native evidence

| Gate | Claude 2.1.278 | Codex 0.155.0-alpha.16.4 |
| --- | ---: | ---: |
| Authenticated smoke | 3/3 | 3/3 |
| New review per smoke | 3/3 | 3/3 |
| Verified terminal capture receipts | 6/6 | 6/6 |
| Cold SessionStart samples | 5/5 | 5/5 |
| Warm SessionStart samples | 5/5 | 5/5 |
| UserPromptSubmit / Stop / SessionEnd samples | 10/10 each | 10/10 each |
| Largest measured hook p95 | 1,784 ms | 1,761 ms |
| Dogfood | 5 sessions, 20 turns, 2 projects | 5 sessions, 20 turns, 2 projects |
| Capture commits / new dead letters | 40 / 0 | 40 / 0 |
| SessionStart receipts / project switch | 5/5 / observed | 5/5 / observed |
| Controlled maintenance failure then retry | pass | pass |
| Live client files unchanged | yes | yes |

The latency source reports are
`evals/w07b/2026-09-25-claude-latency-matrix-run.json` and
`evals/w07b/2026-09-25-codex-latency-matrix-run.json`. Both have
`gate_passed=true`; every observed p95 is below the existing 3,000 ms native
hook timeout. Only SessionStart has an independently cold path in a native
invocation. The other three events are measured over ten warm occurrences,
not relabeled as cold cells. The first Codex matrix had a missing cold
SessionStart/UserPromptSubmit pair despite successful CLI exits. The harness
had treated HTTP unavailability as proof the old service process had exited.
Waiting for that process before the next cold run produced a complete 5/5
diagnostic and the final 10/10 matrix; the missing sample remains recorded in
the work history, not counted in the passing matrix.

The dogfood source reports are
`evals/w07b/2026-09-25-claude-dogfood-run.json` and
`evals/w07b/2026-09-25-codex-dogfood-run.json`. The fault step is explicitly
test-injected after native capture: existing maintenance backlog is drained,
then one disposable intent fails once and succeeds on attempt two. The
canonical MemoryStore/StateStore revisions do not change during that step;
the staging directory is empty afterward. This proves retry behavior in the
same isolated vault, not that a production maintenance failure happened
spontaneously. Previous process-boundary tests independently cover intent,
claim, staging, publication and final receipt recovery with three repetitions
each.

## Tests and safety

- Focused W-07B, capture and runtime tests: **137 passed**.
- Full regression from clean `8140a48`: **1,614 passed, 4 skipped**.
- Critical flake8 (`E9,F63,F7,F82`), `compileall`, `git diff --check`: **pass**.
- An earlier full run on a dirty worktree gave five W06C0R1 scope-allowlist
  failures because that historical verifier rejects unrelated uncommitted
  paths. All five disappeared on the clean implementation commit.
- Raw prompts, transcripts, credentials, session IDs and filesystem paths in
  committed run reports: **none**. Only counts, statuses, timings, project
  labels and version/revision metadata are retained.

## Quality before and after

Codex native capture changed from `EVIDENCE_INVALID` in the initial real
probe to 3/3 authenticated smoke and 40/40 dogfood commits. The native
two-client latency and dogfood matrices changed from missing to measured and
passing their explicit 3-second/capture gates. No canonical memory was
automatically accepted; review remained required.

## Limitations, open failures and review

The old 500 ms hook p95 target is not met by cold SessionStart (Claude
1,784 ms, Codex 1,761 ms), nor by several warm cells. The Stage 3 dogfood
evidence passes its native 3-second budget, but that result does not erase
the separate performance target. The formal W-07B package still requires a
separate read-only implementation/evidence review; this report is an
implementation-owner assessment, not an independent `SHIP` verdict. Native
run JSON files show the parent revision because the measurements preceded
the implementation commit; the tested source and harness bytes are the ones
committed in `8140a48`. Any later source change requires fresh native runs.

**SCORE BEFORE / AFTER:** Native dogfood coverage 1/2 clients to 2/2;
performance target remains open.  
**VERDICT:** Roadmap Stage 3 real-client dogfood gate verified; W-07B parent
package remains FIX-FIRST pending independent review and performance work.
