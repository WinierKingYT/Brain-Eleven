# W-07B Capture Silent Gap Contract

**Status:** APPROVED CONTRACT — assigned to Codex; implementation not started
**Package:** W-07B follow-up (dogfood section fallout), bounded diagnosis + fix
**Priority:** P1 — a real capture path can silently produce nothing, with no
error anywhere in the pipeline
**Phase 20:** FROZEN / LOCKED — **V2:** SHADOW

This is a bounded follow-up to `WEAKNESS-W07B-NATIVE-ACCEPTANCE-EVIDENCE-PLAN.md`.
It does not reopen W-07B's other gates (native Codex trust, the full latency
matrix, Phase 20, V2 promotion, any threshold or holdout change) and does not
by itself move W-07B out of `FIX-FIRST / NOT ACCEPTED`.

## Evidence-backed finding

`docs/history/weakness/WEAKNESS-W07B-CLAUDE-DOGFOOD-EVIDENCE-REPORT.md`
("Finding 3"), reproduced with `evals/w07b/dogfood.py` (an isolated,
credential-gated harness — throwaway vault/config, real authenticated
`claude` CLI, live vault/settings never touched):

- Two registered projects in one vault; 5 sessions / 20 turns total (3
  sessions for project A, 2 for project B, one project switch), each turn a
  real `claude -p` (first turn) or `claude -p --resume <session_id>`
  (subsequent turns) invocation.
- All 20 invocations returned exit code `0` and `is_error: false` — the
  client and hooks never failed visibly.
- In the representative run, project A's three sessions produced **zero**
  captures (not dead-lettered — never enqueued: `queued`/`processing`/
  `dead-letter` were all empty when checked), while project B's two sessions
  captured correctly (review items created, ledger `COMMITTED`, in the
  expected `SHADOW` shape). A second full run reproduced the identical
  pattern.
- Isolating either project alone (same registration, same
  `RuntimeConfig.project_ids` membership, single project invoked) does not
  reproduce the gap — that project's captures always complete cleanly.
- Which project's block fails has not been consistent across every attempt
  made while diagnosing this (see the report for the two *different*,
  already-fixed harness bugs found on the way — a Windows
  `TemporaryDirectory` cleanup race, and a real two-gate registration
  requirement, `ProjectRegistry` membership *and* `RuntimeConfig.project_ids`
  membership — neither of those explains this finding; both are already
  fixed in the harness and are not part of this contract).

## Bounded objective

Reproduce this deterministically (or characterize precisely when it does and
does not occur), find the actual root cause, and fix it if it is a real
runtime defect — without touching anything outside the capture/enqueue path
this finding is in.

Two closure shapes are both acceptable, decided by what you find:

1. **Real defect** — a genuine bug in candidate capture/enqueue/scope
   resolution that silently drops a project's `SessionEnd` events under
   multi-project/sequential-session load. Fix it, add a regression test that
   fails before the fix and passes after (TDD RED → GREEN), and confirm the
   fix does not change behavior for any currently-passing capture path.
2. **Not a runtime defect** — the gap is specific to `evals/w07b/dogfood.py`
   itself (a harness bug this contract did not find). Fix the harness, show
   the corrected harness no longer exhibits the gap across at least 5
   consecutive full 5-session/20-turn runs, and record precisely why the
   original harness triggered it.

Either way, close with a new evidence report in
`docs/history/weakness/`, following the existing W-07B report fields
(`PACKAGE`, `REVISION`, `OBJECTIVE`, `FILES CHANGED`, `ROOT CAUSES ADDRESSED`,
`TESTS ADDED`, `TESTS EXECUTED`, `QUALITY METRICS BEFORE/AFTER`,
`SAFETY METRICS`, `KNOWN LIMITATIONS`, `OPEN FAILURES`,
`INDEPENDENT REVIEW`, `SCORE BEFORE/AFTER`, `VERDICT`), and add the taxonomy
entry proposed in the dogfood report (`CAPTURE_SILENT_GAP`) to whichever
document tracks that taxonomy if the finding is confirmed as a real defect.

## Scope

Allowed:

- Read/trace `brain_eleven/runtime/worker.py` (`allowed`, `enqueue`,
  `Worker`/queue processing), `brain_eleven/runtime/capture_queue.py`,
  `brain_eleven/projects/registry.py`, and anything in the actual call path
  from a `SessionEnd` hook to a queued/committed/dead-lettered capture job,
  for **two concurrently registered projects sharing one vault** specifically.
- A minimal, targeted production fix if a real defect is found, confined to
  that call path.
- `evals/w07b/dogfood.py` and new test-only reproduction helpers.
- A new evidence report under `docs/history/weakness/`.

Not allowed:

- Any threshold, holdout corpus, quality-gate, Phase 20 or V2-mode change.
- Any change to `MemoryStore`/`StateStore`/`ProjectRegistry` schemas.
- Touching the live vault, live Claude/Codex client configuration, or
  Codex-side native trust (still unavailable in this environment; leave it
  `BOUNDED_UNVERIFIED_CODEX_BINARY_MISSING` as recorded).
- Widening this into a general capture-pipeline refactor. If the root cause
  turns out to implicate something larger than the enqueue/scope path above,
  stop and report back for a new contract rather than expanding this one.

## Invariants

- No canonical `MemoryStore`/`StateStore`/`ProjectRegistry` write occurs
  outside the existing, already-tested SHADOW/CANARY/ACTIVE rules.
- A fix must not change behavior for any single-project vault or for a
  project already proven to capture correctly in isolation.
- Reproduction and regression tests must be content-free (no real prompt,
  transcript or credential data), matching every other W-07B evidence
  artifact.
- Self-review is not acceptance; this closes only with a separate read-only
  reviewer's verdict, same as the rest of this package.

## Required evidence

1. A deterministic (or precisely characterized probabilistic) reproduction,
   with the exact trigger conditions stated plainly.
2. If a production fix is made: a regression test proven RED before the fix
   and GREEN after, plus full regression (`pytest -m "not integration and not
   graduation"`), critical flake8 (`E9,F63,F7,F82`), and `compileall` all
   passing.
3. At least 5 consecutive clean runs of `evals/w07b/dogfood.py` (or its
   fixed successor) after the fix, with both projects capturing correctly in
   every run.
4. The new evidence report, revision-bound to the exact fix commit.
5. Independent read-only review returning `SHIP`, `FIX-FIRST` or `RETHINK`.

## Exit gate

This contract closes only when the finding is either fixed (with regression
evidence) or definitively re-attributed to the harness (with the harness
fixed and evidence it no longer reproduces). A plausible guess without
reproduction, and a fix without a regression test, are both insufficient.
This closure does not by itself move W-07B out of `FIX-FIRST / NOT ACCEPTED`
— Codex-side trust and the full latency/dogfood matrix remain separately
open — and does not promote V2 or unlock Phase 20.

**Status: APPROVED — assigned to Codex 2026-09-22 by Claude (project
management delegation, `CONTRIBUTING.md` Roles). Implementation not started.**
