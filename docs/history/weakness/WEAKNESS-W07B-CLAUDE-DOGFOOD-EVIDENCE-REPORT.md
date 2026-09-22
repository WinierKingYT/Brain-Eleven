# W-07B Claude Native Dogfood Evidence Report

**PACKAGE:** W-07B evidence closure (Claude side of the "Dogfood" section only)

**REVISION:** repository HEAD at execution time is `0a3df20`;
`evals/w07b/dogfood.py` is the harness bound to this evidence.

**PLAN:** `docs/history/plans/WEAKNESS-W07B-NATIVE-ACCEPTANCE-EVIDENCE-PLAN.md`,
section "Dogfood"

**STATUS:** FIX-FIRST / NOT ACCEPTED — **this section is NOT closed.** It
surfaces a real, unresolved finding rather than closing
`NATIVE_DOGFOOD_SAMPLE_MISSING`.

**PHASE 20:** FROZEN / LOCKED — **V2:** SHADOW

## OBJECTIVE

Run at least five sessions and twenty turns across two registered projects,
including a project switch, a `SessionEnd`→next-`SessionStart` handoff, and
whatever real maintenance-intent/failure behavior surfaces, using the same
isolation as the sibling harnesses in this package. No production code, hook
configuration, canonical data or live client config was changed.

## FILES CHANGED

- `evals/w07b/dogfood.py` (new) — reusable harness. Same isolation as
  `evals/w07b/native_smoke.py`/`latency_matrix.py`. Registers a second
  project against the same throwaway vault, runs 5 sessions of 4 turns each
  (`claude -p` then three `--resume <session_id>` turns, 1 s apart) across
  the two projects, and records only sanitized counts/status per session —
  never prompt or transcript content.
- `evals/w07b/2026-09-22-dogfood-run.json` (new) — the raw report from the
  representative run discussed below.

## What was structurally verified (clean, reproducible)

- **5 sessions, 20 turns, 2 registered projects, 1 project switch**: met in
  every run, including the one reported below. All 20 real, authenticated
  `claude` invocations returned exit code `0` and `is_error: false`.
- `--resume`-chained multi-turn sessions work end to end against the
  isolated hook configuration.
- Live global `~/.claude/settings.json` and this repository's own
  project-local config: unread and unwritten, same guarantee as the sibling
  reports.

## Real findings (two fixed in the harness, one left open)

**Finding 1 — fixed.** The harness never stopped the background service
before its `tempfile.TemporaryDirectory` tried to remove the vault.
On Windows this raised `WinError 145` ("directory not empty") from inside
`TemporaryDirectory.__exit__`, because the still-running service process
held an open handle under `.brain-eleven/runtime/maintenance-delivery`, and
that exception replaced the harness's own return value with a crash. Fixed
by calling `POST /api/runtime/stop` and waiting for the service to actually
exit before the `with` block ends (`_stop_service`, same pattern the latency
harness already used). This is a harness lifecycle bug, not a runtime
defect — production code was not touched.

**Finding 2 — fixed.** `ProjectRegistry.register()` alone does not make a
second project capturable. `brain_eleven/runtime/worker.py`'s `allowed()`
requires the project's ID to **also** be present in
`RuntimeConfig.project_ids` (`record['project_id'] not in
config['project_ids']` → refused); `install()` only adds the vault's own
project there. Registering a second project directly against the
`ProjectRegistry`, as this harness originally did, leaves every one of its
capture events silently `SCOPE_DISABLED` — zero ledger entries, zero review
items, no error surfaced anywhere. Fixed by also adding the second
project's ID to `RuntimeConfig.project_ids` via the same
`_mutate_current` pattern `install()` itself uses. This is a genuine,
reproducible, now-understood two-gate design (registry identity +
runtime-config scope) that a harness (or a real second-project setup script)
must satisfy; it is not a runtime defect, but it is worth noting for anyone
scripting multi-project registration outside `install()`.

**Finding 3 — open, not root-caused.** With both fixes applied, the harness
runs cleanly end to end (`all_turns_ok: true`, exit `0`), but the two
projects' *capture outcomes* are not both reliably non-zero in the same run.
Representative run (`evals/w07b/2026-09-22-dogfood-run.json`), and
reproduced identically on a second full run:

| Session | Project | Review items created | Maintenance intent | Ledger COMMITTED total (cumulative) |
|---|---|---|---|---|
| 1 | project-a | 0 | none | 0 |
| 2 | project-a | 0 | none | 0 |
| 3 | project-a | 0 | none | 0 |
| 4 | project-b | 4 | QUEUED | 8 |
| 5 | project-b | 4 | QUEUED | 16 |

Every `project-a` turn returned `exit_code 0` / `is_error: false` — the
real client succeeded — but nothing was ever enqueued for it in this run;
`project-b`'s three sessions after it worked correctly. Isolating
`project-a` alone, with `project-b` registered exactly the same way but
never invoked, reproduces the **opposite**: `project-a` completes 8/8 with
no dead letters. In other words, `project-a` fails only inside the full
five-session sequence, and only ever as a contiguous block (never
scattered); which project's block fails was not the same across every
attempt made while diagnosing this. `queued`/`processing`/`dead-letter`
were all empty when this was checked — the missing captures were never
enqueued at all, not stuck or dead-lettered, which rules out the two fixed
issues above (both would have produced a `SCOPE_DISABLED` or a
`dead-letter` entry, not silence).

This was not resolved within this evidence step. Chasing it further would
mean debugging production capture/enqueue behavior under sustained
multi-session, multi-project load — exactly the kind of change this plan
explicitly says it does not make ("This plan changes no production code").
It is recorded here as a new, real, reproducible-in-aggregate finding for a
dedicated follow-up, not fixed and not papered over.

## Taxonomy addition (proposed, not applied to any code)

A candidate entry for the existing failure taxonomy
(`CAPTURE_MISS`, `STALE_CONTEXT`, `TOKEN_WASTE`, …): **`CAPTURE_SILENT_GAP`**
— a project's `SessionEnd` capture is neither enqueued, processed, nor
dead-lettered during a multi-session, multi-project dogfood run, with no
error surfaced anywhere in the pipeline, while an isolated single-project
repro of the identical setup does not reproduce it. This is a proposal for
whoever picks up the follow-up, not an applied change.

## SessionEnd → next SessionStart handoff

Checked via the ledger's cumulative `COMMITTED` count immediately after each
session (`handoff_checks` in the raw JSON): for the sessions that did
capture successfully, the count is monotonically non-decreasing across the
session boundary and a following session's `SessionStart` always completed
without error. This much held in every run, independent of Finding 3.

## SAFETY METRICS

Same isolation guarantees as the two sibling reports: live global
`~/.claude/settings.json` untouched, this repository's own project config
excluded, only synthetic content-free prompts used, canonical `MemoryStore`
revision `0` throughout (SHADOW), temporary vault/config removed on every
run once Finding 1's fix was applied.

## KNOWN LIMITATIONS

- Finding 3 is unresolved; this report does not claim to understand its
  cause.
- Single machine, one `claude` version (`2.1.278`), one session's worth of
  diagnosis time. Not a statistically large sample of dogfood runs (this
  exact 5-session/2-project scenario was run four times in total while
  diagnosing; two showed the pattern in the table above, two showed
  different partial patterns before the two fixes were in place).
- Codex side entirely unmeasured — no `codex` executable exists in this
  environment, same limitation as the other two W-07B evidence steps in
  this batch.
- The `--resume`-based multi-turn design was not compared against genuinely
  separate (non-resumed) sessions; whether Finding 3 depends on `--resume`
  specifically was not isolated.

## OPEN FAILURES

- `NATIVE_DOGFOOD_SAMPLE_MISSING` — **not closed.** Structural requirements
  (session/turn/project counts, project switch) are met; content-pipeline
  reliability across the full sample is not, per Finding 3.
- `NATIVE_CODEX_TRUST_UNVERIFIED` — unchanged, out of this step's scope.

W-07B remains `FIX-FIRST / NOT ACCEPTED`; no V2 promotion or Phase 20 unlock
is implied.

## INDEPENDENT REVIEW

**PENDING — not yet independently reviewed.** Given Finding 3 is unresolved,
a reviewer's first job should be trying to reproduce or rule out the
capture-attribution inconsistency, not just checking the isolation claims
this package's other two reports already establish the pattern for.

## SCORE BEFORE / AFTER

W-07B native maintenance delivery: **7.5 → 7.5 provisional**, unchanged.

## VERDICT

**FIX-FIRST / NOT ACCEPTED.** The dogfood section is attempted, not closed:
structural coverage is real and reproducible, two real harness bugs were
found and fixed along the way, and a third, more significant finding
(inconsistent multi-project capture attribution under load) is left open
and explicitly flagged rather than hidden or claimed resolved.
