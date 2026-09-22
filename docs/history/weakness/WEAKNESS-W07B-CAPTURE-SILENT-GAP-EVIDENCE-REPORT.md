# W-07B Capture Silent Gap Evidence Report

**PACKAGE:** W-07B follow-up (dogfood section fallout) — bounded diagnosis +
fix per `docs/contracts/WEAKNESS-W07B-CAPTURE-SILENT-GAP-CONTRACT.md`

**REVISION:** repository HEAD at investigation start was `ed2aaa8`. The fix
this report documents is commit `4858366fcecea96ca9fa91d20365408dc826c9bb`
("fix(w07b): correct native client project-slug computation in
ownership.py"); this report is committed immediately after it in the same
package.

**STATUS:** Real production defect found, reproduced deterministically, and
fixed with a regression test (RED before, GREEN after). This closes the
capture-silent-gap contract only; it does not by itself move W-07B out of
`FIX-FIRST / NOT ACCEPTED` (Codex-side trust and the full dogfood/latency
matrix acceptance remain separately open, per the contract).

**PHASE 20:** FROZEN / LOCKED — **V2:** SHADOW (unchanged)

## OBJECTIVE

Reproduce Finding 3 from `WEAKNESS-W07B-CLAUDE-DOGFOOD-EVIDENCE-REPORT.md`
("project-a's sessions produced zero captures while project-b's captured
correctly, in the same 5-session/20-turn/two-project dogfood run") either
deterministically or as a precisely characterized condition, find the real
root cause, and fix it if it is a genuine runtime defect in the capture
enqueue/scope path — confined to that path, with TDD regression evidence.

## TRIGGER CONDITION (exact, deterministic once known)

Not a race condition, not a two-project-specific interaction, and not about
which project runs first or second. The trigger is purely path-content
based:

**Any registered project whose absolute root path contains a character
outside `[A-Za-z0-9:\/\\]` (most commonly `_`, which Python's own
`tempfile.TemporaryDirectory`/`mkdtemp` suffixes routinely contain) has
every one of its `SessionEnd`/`Stop` captures permanently dead-lettered**
with the terminal error code `TRANSCRIPT_OWNERSHIP_UNVERIFIED`, with no
error surfaced anywhere else in the pipeline (not stuck in `queued`, not
retried — terminal codes bypass retry entirely per
`brain_eleven/runtime/worker.py`'s `once()`).

This is deterministic given the same path: a project root containing an
underscore (or any other character the old `_project_slug` did not convert)
**always** dead-letters; a project root without one **always** captures
correctly. The original dogfood report's apparent non-determinism
("project-a fails in one run, project-b in another, isolating either alone
never reproduces it") was fully explained by `tempfile.TemporaryDirectory`'s
random suffix: it draws from `[a-z0-9_]`, so roughly 1 in a few runs the
random suffix happens to contain `_` and the affected project's vault path
changes from run to run — `evals/w07b/dogfood.py` uses a
`TemporaryDirectory`-generated path for **project-a** (the vault itself) and
a fixed, underscore-free path (`w07b-dogfood-project-b`) for project-b. This
is why project-b never failed in any observed run, and why isolating either
project alone by itself proves nothing about the multi-project claim — it
was never actually a multi-project interaction at all.

## ROOT CAUSE

`brain_eleven/runtime/ownership.py`'s `_project_slug()` computed a
project's `~/.claude/projects/<slug>` directory name as:

```python
normalized.replace(":", "-").replace("/", "-").replace("\\", "-")
```

The real Claude Code CLI computes that same directory name differently.
Verified empirically against a real, authenticated `claude` CLI invocation
(`claude -p ... --cwd <dir with several special characters>`): a `cwd` of
`...\under_score.dot plus+paren(1)tilde~end` produced the transcript
directory `...-under-score-dot-plus-paren-1-tilde-end` — **every** character
outside `[A-Za-z0-9]` (not just `:`, `/`, `\`) becomes a literal `-`, one
hyphen per character, with no collapsing of adjacent separators (`C:\`
becomes `C--`, not `C-`).

`Worker.process()` calls `verify_transcript_ownership()` before ever reading
a transcript. For the `client == "claude"` case, that function requires
**exactly one** registered project whose *own* `_project_slug(root)` equals
the transcript's actual parent directory name on disk:

```python
matching_roots = [item for item in registry.list_projects()
                   if _project_slug(str(item.get("root", ""))) == resolved.parent.name]
if len(matching_roots) != 1:
    raise TranscriptOwnershipError("TRANSCRIPT_OWNERSHIP_UNVERIFIED")
```

Because the old `_project_slug` left `_` (and every other non-alphanumeric
character besides `:`/`/`/`\`) unconverted, a project root containing one
produced a slug string that could **never** equal the real directory the
client wrote to. `matching_roots` was always empty (`len == 0`), so this
raised `TRANSCRIPT_OWNERSHIP_UNVERIFIED` for every single capture from that
project, every time, with no exceptions. `TRANSCRIPT_OWNERSHIP_UNVERIFIED`
is one of the two terminal ownership codes in `Worker.once()`'s exception
handler, so the job goes straight to `DEAD_LETTER` on the very first
attempt — it is never retried, never left `QUEUED`/`PROCESSING`, and never
surfaces a hook-visible error, because `enqueue()` itself succeeds cleanly
(the failure happens later, inside the worker's own processing, not at
enqueue time). This is why the original report's check of
`queued`/`processing`/`dead-letter` being "all empty" was based on an
incomplete manual check; a fresh instrumented run for this contract found
`dead-letter` fully populated with 8–24 `TRANSCRIPT_OWNERSHIP_UNVERIFIED`
entries for the affected project's block, every one of them terminal on the
first attempt.

This is **not** specific to two concurrently registered projects. The
`matching_roots` computation runs once per verification and does not depend
on how many other projects are registered; a **single-project** vault whose
root contains an underscore would hit exactly the same defect. The
multi-project dogfood harness only surfaced it first because it happened to
be the first place in this package that used a `tempfile`-generated path as
a project root and checked capture outcomes closely enough to notice.

## REPRODUCTION

1. **Deterministic, no real `claude` CLI needed** (new regression test,
   `tests/test_w03b_transcript_ownership.py::test_project_root_with_underscore_is_captured_not_dead_lettered`):
   register a project whose root contains `_`, place a real transcript under
   the directory name the real client would actually use (computed with the
   verified `[^A-Za-z0-9]` → `-` rule), enqueue, and run the worker. **RED**
   before the fix (`DEAD_LETTER` / `TRANSCRIPT_OWNERSHIP_UNVERIFIED`),
   **GREEN** after (`PROCESSED`, one canonical memory write, no dead-letter
   entries).
2. **Real, authenticated `claude` CLI, full dogfood harness** (this
   contract's own investigation, pre-fix): `evals/w07b/dogfood.py` run
   twice with hook-level and ledger-level instrumentation added and later
   fully reverted (never shipped) confirmed the exact mechanism:
   - Run 1: clean (vault path `w07b-dog-vault-km0ptint` — no underscore in
     the random suffix) — both projects captured correctly, 4 review items
     per session throughout.
   - Run 2: reproduced Finding 3 exactly (vault path
     `w07b-dog-vault-ni7k3_tm` — underscore present) — project-a: 0, 0, 0
     review items across its three sessions; project-b: 4, 4. The
     instrumented hook trace showed `enqueue()` returning `status: QUEUED`
     for **every single one** of project-a's 24 hook calls (contradicting
     the original report's "never enqueued" framing) — the capture-ledger
     snapshot taken immediately afterward showed all of project-a's jobs
     reaching `DEAD_LETTER` with `last_error_code:
     TRANSCRIPT_OWNERSHIP_UNVERIFIED` on `attempt: 1`, while project-b's
     jobs all reached `COMMITTED`.
   - A third, empirical probe of the real client's own slug algorithm
     (`claude -p` against a `cwd` containing `_`, `.`, a space, `+`, `(`,
     `)` and `~`) produced the exact transformation rule used in the fix.

## FILES CHANGED

- `brain_eleven/runtime/ownership.py` — `_project_slug()` now replaces every
  character outside `[A-Za-z0-9]` with `-` (a single `re.sub`), matching the
  real client's own algorithm exactly. This is the entire production fix:
  one function, no other call sites reference `_project_slug` outside this
  file (`verify_transcript_ownership`'s two `client == "claude"` checks).
- `tests/test_w03b_transcript_ownership.py` — new regression test (see
  above) plus the file's own `_slug()` test helper updated to mirror the
  corrected algorithm (it must match production or the test constructs a
  transcript directory production can no longer find).
- `tests/test_ig02_capture_closure.py`, `tests/test_capture_provenance.py`,
  `tests/test_ig04_b1_human_approval.py`, `tests/test_shadow_accept.py`,
  `tests/test_w02_terminal_state.py`, `tests/test_pre13_runtime.py` — each
  file had its own local copy of the same narrow slug helper (used to place
  synthetic transcripts under the directory name production would look
  for). All were updated to the corrected algorithm; **this was required,
  not optional** — pytest's own `tmp_path` fixture embeds the test
  function's name (which is full of underscores) in the temp directory
  path, so every one of these tests was silently relying on the *same* bug
  being present on both the test and production sides. Running the affected
  files against the fixed `ownership.py` without updating their helpers
  reproduced the exact `DEAD_LETTER`/`TRANSCRIPT_OWNERSHIP_UNVERIFIED`
  failure in 17 previously-passing tests across 5 files, which is itself
  corroborating evidence for how easy this defect was to trigger
  incidentally.
- `evals/runtime_benchmark.py` — same narrow slug pattern, same fix, for
  consistency (not part of the required pytest regression suite, but
  exercises the identical `verify_transcript_ownership` path).
- `docs/programs/INTELLIGENCE-GRADUATION.md` — added the `CAPTURE_SILENT_GAP`
  taxonomy entry proposed in `WEAKNESS-W07B-CLAUDE-DOGFOOD-EVIDENCE-REPORT.md`,
  next to the existing dogfood-failure taxonomy list, with a short
  description and a pointer to this report. Documentation-only; no
  threshold, gate, corpus or Phase 20/V2 change.
- `docs/history/weakness/WEAKNESS-W07B-CAPTURE-SILENT-GAP-EVIDENCE-REPORT.md`
  (this file, new).

No `MemoryStore`/`StateStore`/`ProjectRegistry` schema changed. No hook
configuration, live vault or live `~/.claude/settings.json` touched at any
point — all reproduction used throwaway vaults/configs via
`tempfile.TemporaryDirectory`, matching every other W-07B evidence artifact.
A short-lived diagnostic instrumentation was added to
`brain_eleven/runtime/launcher.py` and `evals/w07b/dogfood.py`-derived
scratch scripts during the investigation, entirely to collect the hook-level
and ledger-level traces described above; it was fully reverted
(`git checkout -- brain_eleven/runtime/launcher.py`) before this fix was
written and is not part of any commit in this package.

## ROOT CAUSES ADDRESSED

- `TRANSCRIPT_OWNERSHIP_UNVERIFIED` (a real, previously-unattributed cause
  of `CAPTURE_MISS`/silent capture loss) for any project whose root path
  contains a character `_project_slug` did not convert.

## TESTS ADDED

- `tests/test_w03b_transcript_ownership.py::test_project_root_with_underscore_is_captured_not_dead_lettered`
  — TDD RED→GREEN regression test for the exact defect (see Reproduction
  §1).

## TESTS EXECUTED

- New regression test alone: RED before the fix (`DEAD_LETTER` /
  `TRANSCRIPT_OWNERSHIP_UNVERIFIED`), GREEN after.
- `tests/test_w03b_transcript_ownership.py` + `tests/test_ig02_capture_closure.py`:
  41 passed.
- `tests/test_capture_provenance.py` + `tests/test_ig04_b1_human_approval.py`
  + `tests/test_shadow_accept.py` + `tests/test_w02_terminal_state.py` +
  `tests/test_pre13_runtime.py` + the two files above: 170 passed (0
  failed) — this includes the 17 tests that failed against the fixed
  production code before their own local slug helpers were corrected,
  confirming those failures were purely about test-helper/production
  algorithm parity, not new defects introduced by the fix.
- Full regression: `python -m pytest tests -m "not integration and not
  graduation" -q` → **1463 passed, 4 skipped, 82 deselected, 5 failed in
  348.31s**. The 5 failures are all in `tests/test_w06c0r1_contract.py`
  (`test_explicit_corpus_version_and_source_scope`,
  `test_scope_drift_pin_tampering_fails_closed`,
  `test_scope_drift_pin_rejects_protected_changes_after_anchor`,
  `test_unpinned_post_end_owned_path_fails_closed`,
  `test_historical_scope_compatibility_is_pinned_and_unpinned_hash_fails`),
  a scope-drift guard for the unrelated, already-closed W-06C0R1 corpus
  package that fails whenever the working tree has *any* uncommitted change
  outside its own allowlist — **confirmed pre-existing and unrelated to
  this fix**: `git stash`-ing every file this contract touched and
  re-running `tests/test_w06c0r1_contract.py` alone reproduced the exact
  same 5 failures, driven entirely by two changes already present in the
  working tree before this investigation started (`.claude/hooks/.state/compile.log`
  and a deleted `🧠 Brain-Eleven.md`, both visible in this session's
  starting `git status`, neither touched by this contract). This fix adds
  zero new test failures.
- `flake8 --select=E9,F63,F7,F82` on every changed file: **PASS** (exit 0).
- `python -m compileall` on every changed file: **PASS** (exit 0).
- `python scripts/check_documentation_integrity.py`: **PASS** (0 findings,
  64 files checked), both before and after the taxonomy addition.
- 5 consecutive full runs of `evals/w07b/dogfood.py` after the fix, real
  authenticated `claude` CLI (`--settings`/`--setting-sources ""` isolation,
  same as every other harness in this package):

  | Run | Elapsed | project-a review items (3 sessions) | project-b review items (2 sessions) | All 20 turns exit 0 |
  |---|---|---|---|---|
  | 1 | 136.1s | 4, 4, 4 | 4, 4 | yes |
  | 2 | 140.0s | 4, 4, 4 | 4, 4 | yes |
  | 3 | 135.8s | 4, 4, 4 | 4, 4 | yes |
  | 4 | 129.9s | 4, 4, 4 | 4, 4 | yes |
  | 5 | 143.8s | 4, 4, 4 | 4, 4 | yes |

  **5/5 clean.** Both projects captured correctly in every single run —
  the exact opposite of the pre-fix pattern reproduced during root-causing
  (§ Reproduction, run 2: project-a 0/0/0, project-b 4/4).

## QUALITY METRICS BEFORE / AFTER

| Gate | Before | After this fix |
| --- | --- | --- |
| Multi-project dogfood capture reliability | Non-deterministic per-run (depended on whether a `tempfile`-generated project root happened to contain `_`) | Deterministic — **5/5 consecutive clean runs**, both projects capturing every turn |
| Single-project capture reliability for a root containing `_`, `.`, space, or other non-`:`/`/`/`\` special characters | **Broken** (100% dead-letter, silent) | Fixed |
| `_project_slug` correctness vs. the real client | Verified wrong (empirically, against a real invocation) | Verified correct (same empirical method) |

## SAFETY METRICS

- Live vault (`C:\Users\faruk\Documents\Brain-Eleven`) and live global
  `~/.claude/settings.json`: never read or written by any reproduction or
  test in this investigation. All reproduction used
  `tempfile.TemporaryDirectory`-based throwaway vaults/homes, matching the
  sibling W-07B harnesses' isolation pattern.
- No `MemoryStore`/`StateStore`/`ProjectRegistry` schema change.
- No threshold, holdout corpus, quality-gate, Phase 20 or V2-mode change —
  the `CAPTURE_SILENT_GAP` taxonomy addition is a documentation label, not a
  gate.
- No Codex-side code touched; `BOUNDED_UNVERIFIED_CODEX_BINARY_MISSING`
  remains exactly as recorded, out of scope here.
- Only synthetic, content-free transcript text used in every test and
  reproduction (`"We decided to use SQLite."`-style decision statements, no
  real user data).
- The one real-`claude`-CLI probe used to empirically verify the client's
  slug algorithm (`under_score.dot plus+paren(1)tilde~end`) used a
  content-free `hello` prompt against a throwaway temp directory; its
  session and transcript live only under the machine's own real
  `~/.claude/projects/` (the same location every real `claude` invocation
  in this package's sibling harnesses already writes to) and contain no
  repository or user data.

## KNOWN LIMITATIONS

- The fix was verified against one real `claude` CLI version
  (`2.1.278`, same as the sibling W-07B reports) on one machine, one day.
  If a future client version changes its own slug algorithm again, this
  function would need re-verification the same empirical way — there is no
  documented, versioned contract for this transcript-directory naming
  scheme; it is reverse-engineered from observed behavior in this report
  and the two prior W-07B reports.
- Codex-side transcript ownership (`client == "codex"`) does not use
  `_project_slug` at all (it verifies via the transcript's own embedded
  `cwd` metadata instead) and was not touched or re-examined by this fix.
- This fix does not add a "warn if a registered project's root contains an
  unusual character" pre-flight check; it fixes the slug computation to be
  correct for any character, which is a stronger guarantee than a warning
  would have been, but there is no regression test proving robustness
  against the *next* real client version potentially changing this
  algorithm again — that is a KNOWN limitation, not a claimed guarantee.

## OPEN FAILURES

None newly opened by this fix. Pre-existing, unchanged and unaddressed by
this contract per its own scope:

- `BOUNDED_UNVERIFIED_CODEX_BINARY_MISSING` — no `codex` executable in this
  environment.
- The rest of W-07B's dogfood/latency acceptance gates beyond what this
  contract covers (per the contract, this closure does not by itself move
  W-07B out of `FIX-FIRST / NOT ACCEPTED`).
- The 5 pre-existing `tests/test_w06c0r1_contract.py` scope-drift-guard
  failures (see Tests Executed) are unrelated to this contract, confirmed
  present before this investigation began and reproducible with none of
  this contract's own changes present. Not fixed here — the guard reacts to
  two unrelated pre-existing working-tree changes
  (`.claude/hooks/.state/compile.log`, a deleted `🧠 Brain-Eleven.md`), and
  touching `evals/w06c0r1/evaluation.py` or that allowlist would be exactly
  the "widening into a general refactor" this contract's scope forbids.
  Flagged here for whoever owns that package, not silently left out of this
  report.

## INDEPENDENT REVIEW

**PENDING — not yet independently reviewed.** Self-review is not
acceptance, per this project's own convention and this contract's explicit
invariant. A reviewer's first job should be: (1) independently confirm the
empirical slug-algorithm claim (re-run the real-CLI probe described above,
or an equivalent), (2) confirm the RED→GREEN regression test actually
exercises the fixed function and not some other code path, (3) spot-check
that the 6 other test files' helper updates are each still correct against
the fixed production algorithm, and (4) form their own verdict — `SHIP`,
`FIX-FIRST`, or `RETHINK` — rather than accept this report's self-assessment.

## SCORE BEFORE / AFTER

W-07B native maintenance delivery: **7.5 → 7.5 provisional**, unchanged —
per the contract, closing this capture-silent-gap finding does not by
itself promote W-07B's overall score; Codex-side trust and the full
dogfood/latency acceptance gates remain separately open.

## VERDICT

**Real production defect confirmed, root-caused with empirical evidence,
fixed with a minimal one-function change, and covered by a TDD regression
test proven RED before and GREEN after.** Closure shape (a) from the
contract ("real defect ... fix it ... add a regression test"), not shape
(b) (harness bug) — `evals/w07b/dogfood.py` itself needed no changes; it
correctly reproduced a genuine runtime defect. This does not close W-07B
overall and does not promote V2 or unlock Phase 20.
