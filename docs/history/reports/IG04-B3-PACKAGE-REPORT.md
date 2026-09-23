# IG04-B3 Package Report

**Status:** Implementation and local evidence complete; acceptance pending.
This report is not an independent review, package acceptance, or `SHIP` verdict.

**Package:** IG-04 Branch B, B3 — review-queue SessionStart nudge  
**Implementation/test head:** `bd3e4c3555456421956665cab8e5c16cb125dda3`
**Branch:** `ig/ig04b3-review-nudge`
**Contract:** [IG04-B3-CONTRACT.md](../../contracts/IG04-B3-CONTRACT.md)  
**Phase 0 audit:** [IG04-B3-AUDIT-NOTE.md](../evidence/IG04-B3-AUDIT-NOTE.md)

## Outcome and boundaries

The implementation adds a content-free review metadata index, a per-session
and per-project prompt counter, SessionEnd-only threshold finalization, and an
optional V1 SessionStart nudge. A nudge is considered only after at least five
valid prompts in an opted-in project, and only for one or more visible pending
B2 review groups. Per-turn Stop preserves the counter. SessionStart uses only
the marker ledger and a ready metadata index; it does not open review bodies,
list or expire queue records, rebuild an index, or write hook text directly.
Unknown index state fails closed and keeps a valid marker for retry. The line
uses the existing V1 safety, scope, revision and budget checks and is consumed
at most once.

No canonical MemoryStore, StateStore, project authority, gate, threshold, IG01,
HOLDOUT or V2 behavior was changed. The B3 state is operational metadata only.
Review index reconstruction for a legacy queue is deliberately deferred to an
explicit visit to the existing review-list path; SessionStart never initiates
that migration.

## Changed implementation and evidence

The implementation/test commits, in order after the frozen contract, are:

- `2fb93a0` — content-free review metadata index and queue lifecycle recovery.
- `29950e3` — per-session content-free prompt counter.
- `bd12874` — SessionEnd-only marker finalization; Stop preservation.
- `479e2c5` — optional V1 SessionStart rendering and at-most-once consumption.
- `bd3e4c3` — cross-boundary, concurrency, failure and latency tests.

Changed code: `brain_eleven/runtime/review.py`,
`brain_eleven/runtime/review_nudge.py` (new),
`brain_eleven/runtime/launcher.py`, and `brain_eleven/runtime/context.py`.
Added tests: `tests/test_ig04b3_review_index.py`,
`tests/test_ig04b3_review_nudge_counter.py`,
`tests/test_ig04b3_session_end_marker.py`,
`tests/test_ig04b3_session_start_nudge.py`, and
`tests/test_ig04b3_integration.py`.

## Verification

Focused verification on the implementation/test head passed:

- Review index plus B1/B2/PRE-13 regressions: **97 passed**.
- Prompt counter plus PRE-13/W-10/IG02 hook regressions: **119 passed**.
- SessionEnd marker/counter and prior end-hook regressions: **50 passed**.
- SessionStart nudge and IG-00/W-07a/W-10 regressions: **40 passed**.
- Integration, SessionStart and SessionEnd group: **23 passed**; the final
  integration-only rerun was **4 passed**.
- `python -m compileall -q brain_eleven/runtime`: passed.

An earlier full-suite run before correcting Markdown labels in
`PROJECT-STATUS.md` reported **1 failed, 1591 passed, 4 skipped**; the sole
failure was the documentation-integrity checker interpreting two linked file
labels formatted as inline code. The references were corrected. A subsequent
run with the documentation closure still uncommitted reported **5 failed,
1587 passed, 4 skipped**: W-06C0R1's repository-scope guard rejected those
uncommitted documentation files. No scope guard or package rule was changed.
After committing the documentation closure as `0a9812c07cf942573533c2fb0c330da1aa10698e`,
`python -m pytest -q -rs` passed **1592 tests with 4 platform skips** in
268.36 seconds. The four skips are existing Windows directory-fsync tests
(`tests/test_w18_memory_parent_fsync.py`), skipped because directory fsync is
unsupported on Windows; no B3 test is skipped. This is a pre-existing
platform-specific exception to the frozen contract's literal “no tests
skipped” clause, not a skip added or suppressed by this package.

### Same-host W-07B latency (real Claude CLI 2.1.278)

The same isolated temporary-vault harness was run before and after the change.
These are hook timing measurements, not proof that a native UI displayed the
B3 line. Units are milliseconds; `n` is sample count.

| Event | n | Before p50 / p95 | After p50 / p95 | Delta p50 / p95 |
|---|---:|---:|---:|---:|
| Cold SessionStart | 5 | 1354 / 1387 | 1380 / 1393 | +26 / +6 |
| Warm SessionStart | 5 | 181 / 203 | 238 / 253 | +57 / +50 |
| UserPromptSubmit | 10 | 225.5 / 258 | 262 / 285 | +36.5 / +27 |
| Stop | 10 | 95.5 / 105 | 98 / 125 | +2.5 / +20 |
| SessionEnd | 10 | 94.5 / 119 | 138 / 174 | +43.5 / +55 |

The harness exited successfully and used an isolated temporary vault/config.
Existing W-07B quality/latency gates were not modified and are not claimed to
pass. These measurements establish neither Codex latency nor native client
trust, user authentication, or visible B3 delivery.

## Configured versus verified; limitations

The code path and local integration behavior are verified by the tests above.
The package is not merged or deployed. Live Claude/Codex native B3 display,
Codex-specific latency, authenticated native capture trust, and actual
SessionEnd timing in a user's live client remain unverified. A pre-index legacy
queue needs one explicit review-list visit before a known pending count can be
used. SessionEnd may be delayed until the client ends or idles a session.
The existing PRE-13 runtime-quality failure remains visible and is a separate
decision; this package does not tune it or any rollout gate.

The branch was rebased on the latest green master `4a62b40b17bcb11bddbde867ce321048afeeb180`;
Validation run [35830565871](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35830565871)
passed on Ubuntu and Windows. The exact final documentation-head Validation
and separate independent read-only review are still required; neither this
report nor the implementer self-approves IG04-B3.

## Final local regression and final-head Validation

After this master rebase, the full suite is rerun on the report-finalization
commit. Exact final-head Validation and separate independent read-only review
remain pending. The final handoff records the exact documentation-head
Validation URL and SHA; this report does not self-approve IG04-B3.
