# SRT-00 stabilization plan

Status: **NOT SHIP.** On a remote run of the same SHA the Ubuntu and Windows
unit, integration, coverage and PRE-13 runtime gates are green, but the PRE-13
holdout quality gate is still an honest **FAIL**, the master-only Validation
jobs ran green on GitHub only on a throwaway branch (not on `master`), and no
independent review has happened.

Record date: 2026-09-20. This replaces the 2026-09-18 version of this file; the
claims of that version that turned out to be wrong are corrected in
"Corrections to the 2026-09-18 record" below.

Inputs: two findings reports (2026-09-17 and 2026-09-18). They are not stored in
the repository and are treated as evidence and recommendations, not as
instructions that override the repository or the request.

## Bounded work order

1. **A — transcript fixtures.** Byte-deterministic W-03B fixtures; production
   ownership checks unchanged.
2. **B — Windows CLI and backup.** Content-safe diagnostics first, then a fix
   only for a reproduced defect.
3. **C — PRE-13 coverage and cold start.** Measure the real runtime surface at
   the unchanged 80% gate.
4. **D — holdout evidence.** Keep the independent holdout strict; guarantee a
   content-free error artifact; never filter, relabel or relax.
5. **E — topology.** Diagnostics produce evidence after an upstream failure while
   release and publish chains keep their hard `needs`.

## Outcome by finding

| Finding | Disposition | Evidence |
|---|---|---|
| P0-1 W-03B same-size fixtures | **FIXED** | Fixtures used `write_text`; on Linux the "same size" replacement was one byte longer (119 vs 118 and 120 vs 119) and only matched on Windows because CRLF added a byte. Reproduced on Ubuntu 24.04 at `5dc0121` (2 failed, 5 passed). Fixtures now write bytes and assert the length in the test; two matrix cases were added (new inode, multibyte). The fixed tests also pass against unmodified `5dc0121` production code, so the ownership checks were never at fault. `33a06b2`, `cf98741`. |
| P0-2 Windows task / task-state CLI parity | **FIXED — real production bug** | Reproduced by forcing a cp1252 stdout: all four CLI invocations exit 1 with `UnicodeEncodeError` on U+0131 and write nothing. The JSON contract used `ensure_ascii=False` and printed through a pipe that inherits the ANSI code page, so it never passed on an en-US Windows runner and always passed on a UTF-8 developer machine. `brain_eleven.runtime.cli_output.use_utf8_stdout()` is called by both CLI entrypoints when `--json` is requested. `c61e072`. |
| P0-3 Windows MemoryBackup disaster drill | **FIXED; CI cause not proven** | Reproduced two real defects: a short-name (8.3) root produced a false `BACKUP_FINAL_PATH_OUTSIDE_ROOT`, and slicing four characters corrupted `\\?\UNC\` paths. Containment is now component-wise and case-insensitive on `ntpath` with the root canonicalised; errors carry bounded codes. `tests/test_memory_backup_windows.py` covers short-name roots, junction escape, casing, Unicode and handle release. The drill no longer fails on the Windows runner. The original CI failure body was in a protected artifact, so the short-name defect is a matching, not a proven, cause. |
| P0-4 PRE-13 coverage | **FIXED** | The runtime workflow measures a 41-file manifest (adding `test_phase11_graph_chat.py`, which takes `chat_interface` from 35% to 88%) at the **unchanged** 80% gate: Windows 82.87%, Ubuntu 83.07% (Python 3.12 locally). Both runtime jobs are green remotely. The margin is about three points. |
| P0-5 PRE-13 holdout quality | **OPEN — gate kept, promotion deferred** | Still FAIL (precision 0.169014, required recall 0.676471 in the last local measurement; the remote `quality` job exits 1). The `STALE_INPUT` boundary is fixed (compiler snapshots preserve the registry revision) and a failed run now leaves a content-free error artifact while still exiting non-zero. The frozen `corpus-v2` has six duplicate `(project_id, prompt)` inputs, three of them with different required memory IDs, so no deterministic provider that sees only task inputs can select both labels. Hidden labels or task IDs, filtering rows and lower gates are not acceptable. Decision of 2026-09-20 (the project owner delegated the choice): keep the frozen corpus-v2 gate exactly as it is and defer PRE-13 promotion; no corpus, label or threshold changes. Improving retrieval quality is a separately contracted package (the W-06C0R1 answerability corpus is the starting evidence) and is not part of SRT-00. |
| P1 diagnostics topology | **FIXED** | `diagnostics.yml` runs Bandit, secrets, dependency, IG01-E audit and evaluation smoke independently of the release graph; it succeeded on every pushed SHA. Release and publish chains keep their `needs`. A diagnostic pass is not release authority. |
| P2 action versions | **DONE** | `setup-python@v7` and `upload-artifact@v7`; both tags were confirmed to exist with `git ls-remote`. |
| P2 runner pin | **DONE** | Ubuntu jobs are pinned to `ubuntu-24.04` because `ubuntu-latest` migrates to Ubuntu 26 on 2026-10-19. The matrix keeps its `os` label (job names, artifact names and `if:` checks key on it) and gains a `runner` field. `windows-latest` is deliberately unpinned. `007f24e`. |
| P2 documentation integrity script | **DONE, diagnostics only** | `scripts/check_documentation_integrity.py` checks link targets (exact case), authority citations, the `docs/history` index in both directions and active/archived duplicates over root `*.md`, `docs/`, `evals/` and `templates/`; archived files and the personal vault notes are out of scope. It found one real index drift (`DOCUMENTATION-CLEANUP-2026-09-18`), now fixed. 17 tests, 95% module coverage, identical 180-file result on Windows and Ubuntu, and three deliberate breakages each failed with the right file and line. It runs in the non-release diagnostics workflow; making it a release gate is a separate choice. |

### Findings that were not in the audit

- **Race in `test_two_concurrent_creators…`.** It timed the lock release
  against spawn plus import. Under a randomised spawn delay the old test failed
  8/8 at the assertion seen in the flake and the fixed test passed 8/8
  (`cf98741`).
- **Cold start.** A recent launch marker belonging to a dead process suppressed
  a service restart. The marker now records a pid and the service lazy-imports
  its heavy graph (`cf98741`). The related test
  (`test_cold_native_session_start_delivers_v1_within_hook_budget`) asserts a
  hard 3 s budget on a real subprocess. It is timing-sensitive: on a busy local
  Windows machine it failed twice inside a larger run (once right after a
  checkout, once while heavy file and process activity ran alongside), while it
  passed 8/8 alone on an idle machine and in every remote run. One idle run took
  2 s longer than the others and still passed, so the margin is real but
  shrinks under contention. It protects a real hook-window requirement and was
  not loosened.
- **`PYTHONPATH=scripts` hid real gaps.** Without it six tests failed on
  Windows: five multiprocessing tests whose spawned children could not import
  bare script names, and one identity test whose `logging_config` alias was
  missing from `conftest.py`. The tests now import `scripts.<name>`
  (`ac04f53`) and the variable is gone from the workflows (`a4a3411`). It does
  not change what coverage measures — two clean runs of the same commit gave
  identical coverage with and without it.
- **Hook line endings.** Extensionless hook scripts became CRLF under
  `core.autocrlf=true` and broke under bash. `.gitattributes` now pins them to
  LF; a fresh checkout went from 145/37/18 CRLF to zero (`4211851`).
- **IG01-E audit `baseline_boundary` FAIL — explained, not a defect.** The
  diagnostics step runs `python -m evals.ig01e.audit` without the IG01-D pair
  artifact, and the audit deliberately fails that check without it
  (`evals/ig01e/audit.py`: a local audit "can never emit SHIP without the exact
  CI-produced pair artifact"). It therefore reads `FIX-FIRST` at every commit
  back to `5dc0121` while exiting 0. The real `ig01e-audit` job downloads the
  artifact and exits non-zero unless the verdict is `SHIP`. Generating the
  pair with `python -m evals.ig01d.baseline` and running the real command on a
  clean checkout of `ba0d7ab` gave `SHIP` with all nine checks passing. Making
  the diagnostics step pair-backed would stop its report from reading
  `FIX-FIRST`; that change is not made.
- **Human-readable output** of the two CLIs still uses the platform encoding;
  only the `--json` contract was changed.
- **Automatic capture never succeeded on the real install.** All 205 capture
  jobs in the real dead-letter queue failed with `EVIDENCE_INVALID`. Cause: the
  Claude transcript reader accepted only a fixed list of record types and
  rejected the whole session on any other; current clients write many more
  (`attachment`, `mode`, `permission-mode`, `bridge-session`, ...). The size
  hypothesis (2 MiB increments) was refuted: a 0.02 MiB session failed too.
  Fix (`1ef1176`, review remediation `f0a0a4f`): only `user`/`assistant` records
  produce evidence; a *string* type the reader does not know is skipped and
  counted by bounded ASCII name; a record with a missing or non-string `type`
  is still rejected. The count is written to `last-transcript-stats.json` and
  shown by `doctor` as `last_transcript` (advisory, never affects readiness).
  The 7 real dead-lettered sessions now all read; one 2.98 MiB session gave 67
  messages and 62 PENDING review items in a throw-away vault with 0 canonical
  writes. In `SHADOW` those items cannot be accepted (accept needs
  `CANARY`/`ACTIVE`), and 62 items from one session say nothing about capture
  precision yet. The Codex adapter has the same strict whitelist; it was not
  changed because there is no real Codex data to check it against. `attachment`
  text is not captured. The 205 old dead-letter jobs were not requeued.

## Corrections to the 2026-09-18 record

- "The four reported P0 tests pass locally … no product change was justified"
  was wrong. They pass on a UTF-8 developer machine; the Windows CLI failure is
  a real defect and the W-03B failure reproduces on Linux.
- "`PYTHONPATH=scripts` lets Windows spawn children load the script-backed
  adapter" was wrong. It only masked import gaps in the tests.
- "503 runtime tests at 80.00% coverage" is superseded by 560 (Windows) and 558
  (Ubuntu) tests at 82.87% and 83.07% after the manifest was corrected.
- "Same-SHA validation still required" stands, but is now partly satisfied on a
  non-master branch; see below.

## Commits and evidence

| Commit | Content |
|---|---|
| `33a06b2` | W-03B byte fixtures, bounded backup error codes and containment, content-free eval failure artifact, diagnostics workflow |
| `cf98741` | PRE-13 manifest and topology, cold-start marker, stale-input registry revision, Windows backup tests, race-test fix |
| `5da9e8c` | IG-07 Slice 2F package migration (see `IG07-SLICE2F-PACKAGE-REPORT.md`) |
| `c61e072` | UTF-8 `--json` contract for the task CLIs |
| `4211851` `007f24e` `ac04f53` `a4a3411` | `chore/hygiene`: hook LF, runner pin, spawn-safe tests, no `PYTHONPATH` — merged into the local `master` as `b30c6d5` |
| `43a204b` `c9ac7d4` `fd9bbc0` `dc2fae5` | Documentation integrity checker, its tests, the diagnostics step and the Bandit-convention fix — fast-forwarded into the local `master` |
| `b66636c` | `test.yml` off Node 20 actions and CodeQL v3: `download-artifact` v4→v8 (all 12 uses download by name and path, so v5's by-ID path change does not apply), `codecov-action` v4→v7 (`file`→`files`), `setup-buildx` v3→v4, `build-push` v6→v7, `upload-sarif` v3→v4 |
| `7e384a1` | `build.yml` docker actions v3/v5/v6 → v4/v4/v6/v7. Its own commit because `build.yml` only runs for a validated `master` push and no branch run exercises it; revert this commit alone if the first publish run fails |
| `f3dfa6f` | `CLAUDE.md` work-order line replaces the "no new phase, recall test only" line (owner-approved 2026-09-21) |

Remote runs on `ig/…` branches (`ig/srt-00-ig07-ci`, and
`ig/master-only-preview` for `d7852e8`), which cannot publish an image:

| SHA | Validation | PRE-13 runtime (Ubuntu / Windows) | PRE-13 quality | Diagnostics |
|---|---|---|---|---|
| `5da9e8c` | failure — two Windows CLI parity tests (P0-2) | green / green | FAIL | success |
| `c61e072` | **success** — 19 jobs green, 11 skipped by design | green / green | FAIL (holdout) | success |
| `a4a3411` | **success** — 19 jobs green, 11 skipped by design | green / green | FAIL (holdout) | success |
| `dc2fae5` | **success** — 19 jobs green, 11 skipped by design; includes the Bandit hard gate and both Unit jobs | green / green | FAIL (holdout) | success |
| `d7852e8` | **success** — 30 of 30 jobs green, **0 skipped**; the 11 master-only jobs ran (their branch condition was relaxed, see below) | green / green | FAIL (holdout) | success |
| `7e384a1` | **success** (#819) — 19 jobs green, 11 skipped by design; both Unit jobs green; **0 annotations** (the Node 20 and CodeQL v3 warnings are gone) | green / green | FAIL (holdout) | success |
| `03920bb` | **success** (#820) — 30 of 30 jobs green, **0 skipped**, **0 annotations**; `f3dfa6f` plus the `ig/**` relaxation, merged onto the earlier throwaway so the push was a fast-forward | green / green | FAIL (holdout) | success |
| `6103a3d` | **success** (#822) — 19 jobs green, 11 skipped by design, **0 annotations**; includes the opt-in router scope sweep (off by default) and the `retrieval_decision_v2` fix | not read | FAIL (holdout) | not read |
| `00fddcf` | **success** (#823) — 30 of 30 jobs green, **0 skipped**, **0 annotations**; `6103a3d` plus the `ig/**` relaxation; the three Phase 17 router jobs (shadow smoke, public suite, evidence) ran against the new router code | not read | FAIL (holdout) | not read |

`dc2fae5` is the local `master` tip at the time of writing, so the whole
current code state has run on GitHub. Its first push (`fd9bbc0`) failed the
Bandit gate because the new checker did not follow the repository's `nosec`
convention; that was caught on this branch before it reached `master`. Run
links for `dc2fae5`: Validation
[`35473233931`](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35473233931),
PRE-13 [`35473233917`](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35473233917),
diagnostics [`35473233904`](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35473233904).

`d7852e8` is a throwaway commit on `ig/master-only-preview`, made on top of the
`master` tip `5da23b4` and never to be merged. It changes only the 11 job
conditions that read `github.ref == 'refs/heads/master'` to
`startsWith(github.ref, 'refs/heads/ig/')`, so the public suites, the Phase
15–19 evidence jobs and the foundation graduation job ran on GitHub without
pushing `master`. All 11 succeeded and no job was skipped. `build.yml` is
untouched and published nothing: it produced no run for that branch. This is
evidence for identical code, not a `master` run. Run links: Validation
[`35495699060`](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35495699060),
PRE-13 [`35495699068`](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35495699068),
diagnostics [`35495699042`](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35495699042).

`a4a3411` is the tip of `chore/hygiene`; its run also shows that the
`ubuntu-24.04` pin and the removal of `PYTHONPATH` work on GitHub. Run links:
Validation [`35455331470`](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35455331470)
and [`35459215283`](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35459215283),
PRE-13 [`35455331293`](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35455331293)
and [`35459215254`](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35459215254)
for `c61e072` and `a4a3411` respectively.

Local measurements, not CI: Ubuntu 24.04 under WSL, Python 3.12 (CI uses 3.13),
real clone with history. Full unit run 1410 passed, 8 skipped, coverage gate and
context-engine coverage contract passed. A replay of the 11 master-only jobs'
commands passed: 25/25 evaluation, shadow and benchmark commands, the Phase
15–19 evidence generators (`status: PASS` in each output), the graduation tests
(3 passed) and the foundation evidence; the GitHub run of `d7852e8` then
confirmed those jobs. On Windows the full unit run passes
apart from five `test_w06c0r1_contract.py` tests that only fail while there are
uncommitted changes; the whole file passes (23/23) on a committed tree.

The frozen W06C0R1 scope contract was not relaxed.

## Remaining acceptance blockers

1. **Holdout quality (P0-5)** stays red by decision: the frozen corpus-v2 gate
   is kept and PRE-13 promotion is deferred. SRT-00 cannot be `SHIP` while the
   PRE-13 quality gate fails; only a separately contracted quality package can
   change that.
2. **The 11 master-only Validation jobs** (public suites, Phase 15–19 evidence,
   graduation) are verified on GitHub, but not on `master`: they only run on a
   push to `master`, so the throwaway `d7852e8` relaxed exactly those
   conditions and Validation finished 30 of 30 green with nothing skipped.
   Pushing `master` would still add the image publication
   (`ghcr.io/…:latest`) while PRE-13 quality is red, because that gate is a
   separate workflow. Because the holdout stays red, `master` is not pushed by
   default; pushing it is a separate, explicit decision.
   Update 2026-09-21: `origin/master` is still `5dc0121` and red (four unit
   tests fail deterministically on every run since 2026-09-18 — #807, #808,
   #815, #818 — plus the timing-sensitive w08b test once). Those fixes are all
   on the branch. The action bumps were verified across all 30 jobs on
   `03920bb`. `build.yml`'s bump (`7e384a1`) is the one change no branch run
   can verify. A master push also re-runs `runtime.yml`, whose `quality` job
   stays red by the holdout decision, so "every job green" holds for
   Validation only.
3. **Independent review** of the exact final SHA has not happened.
4. Windows and Ubuntu results must come from the same final SHA; the local
   replay above does not substitute for it.

Phase 20 stays frozen and V2 stays SHADOW. Closing SRT-00 does not open either.

## Rollback

Every commit above is independent and can be reverted on its own in reverse
order; nothing was pushed to `master`. `chore/hygiene` was merged locally as
`b30c6d5`; reverting that merge commit undoes it without touching `c61e072`.
