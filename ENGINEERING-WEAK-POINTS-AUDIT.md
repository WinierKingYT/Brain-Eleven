# Engineering Weak-Points Audit — Initial Baseline

**Audit date:** 2026-09-12  
**Program:** Engineering Weak-Point Improvement Goal  
**Repository revision:** `cc1c0b5`
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW

This is the first evidence-backed audit pass. A passing regression suite is
not treated as proof that product quality is high; the scores below reflect
the behavior and operational evidence found in the current repository.

## Baseline verification

- Full local suite after the shipped W-06A package: **978 passed, 2 dependency
  deprecation warnings**.
- No production files were changed during the initial audit.
- The current working tree already contained pre-existing untracked evidence
  directories; they were left untouched.

## Preliminary scorecard

| Area | Score | Evidence / status |
|---|---:|---|
| Persistence and concurrency | 7.0 | Registry durability/revision gap; uncoordinated multi-authority backup; state-memory reference TOCTOU. |
| Scope and fail-closed safety | 7.0 | Related-note and native transcript path boundaries are independently shipped; project/session ownership proof remains open. |
| Capture runtime | 8.5 | Claim/retry/lease crash-loss and late known-locator durability are independently shipped; prompt-event semantics remain. |
| Evaluation quality | 6.5 | Harness is versioned and tested, but D0 retrieval thresholds are below the measured oracle ceiling and the hybrid control is mislabeled. |
| Semantic retrieval correctness | 6.0 | Active search still depends on legacy embedding path and lexical fallback; provider abstraction is not the active authority. |
| Retrieval quality | 4.5 | Broader task-aware retrieval remains open; W-06A only improves the V1 bootstrap slice. |
| Task understanding | 8.5* | Deterministic task model has strong parity evidence; marked provisional until the whole task/context boundary is audited. |
| Extraction intelligence | 7.0* | Safety and semantic layers exist, but full real-use quality is not yet independently measured. |
| Correction/lifecycle | 8.0* | B1/B2 package reviews are shipped; natural-reference quality and real-use evidence remain incomplete. |
| Context compilation | 6.3 | Related-note boundary and V1 bootstrap relevance/order are shipped; raw continuity markdown remains and V2 is shadow-only. |
| V2 runtime readiness | 4.0 | V2 is implemented and measured but not promoted; current shadow comparison remains below V1 on relevance recall. |
| Reminder/continuity runtime | 3.5 | Session end queues evidence, but Daily/Last Session/open-loop maintenance remains legacy/manual. |
| Architecture cleanliness | 7.0 | IG-07 slices reduced compatibility debt, but canonical implementation still spans legacy script surfaces. |
| Daily-use reliability | 4.5 | Native client trust is not fully verified and active user delivery remains V1. |

Scores marked with `*` are provisional and require a dedicated audit before
they are treated as final.

## Confirmed weaknesses and bounded follow-ups

### W-01 — V1 related-note path boundary (P1, selected first)

`scripts/context-compiler.py:386-406` builds
`self.hamle_dir / f"{link}.md"` from canonical `related_notes` values without
resolving and confining the result to the notes directory. A value such as
`../../outside` can make the compiler read a vault-external file into the
bootstrap context. This is a read-boundary violation and a prompt-injection
surface. The bounded fix is path resolution plus directory containment,
allowlisted note-name handling, and focused traversal/symlink tests. It must
not change ranking or V2 behavior.

### W-02 — Capture queue claim crash window (P1)

`capture_queue.py` moves a job to `processing` before rewriting its status.
An exit between those operations leaves a `QUEUED` document in `processing`,
which lease recovery rejects. A bounded fault-injection package is required.

**Status:** Closed and independently reviewed `SHIP` at `46f2ff8` (evidence
report correction at `b35facf`). Claim, retry/requeue, retry/dead-letter and
lease-recovery transitions now persist the next state before rename, repair
state-location pairs after an interrupted rename, and have pre/post-rename
fault-injection coverage.

### W-03 — Transcript provenance boundary (P1)

Native hook input supplies `transcript_path`, but the evidence reader checks
only generic filesystem properties. It does not prove that the file belongs to
the trusted client/project transcript root or current session. This needs a
separate capture-safety contract.

**W-03A status:** Path confinement is independently shipped at `bae7c15` (code
`a6f7fd1`, report `WEAKNESS-W03A-PACKAGE-REPORT.md`). Enqueue and worker read
boundaries now enforce configured/native client roots, traversal and symlink
containment. Project-slug ownership, Codex project association, session
ownership and stable replacement identity remain explicit follow-up work.

### W-04 — Late transcript loss (P1)

The worker refuses to enqueue a missing transcript and returns degraded before
durable queueing. A normal SessionEnd race can therefore lose the event before
retry/dead-letter handling begins.

**Status:** Closed as the bounded W-04 package and independently reviewed
`SHIP` at `6a786b6` (implementation `64e2591`, report
`WEAKNESS-W04-PACKAGE-REPORT.md`). A trusted but temporarily absent locator is
now durable and retryable; a missing locator is still explicitly degraded and
never guessed.

### W-05 — Prompt event dead-letter loop (P1)

Legacy `USER_PROMPT_SUBMIT` events have no transcript locator, yet the worker
routes every no-evidence result through retry/dead-letter. The event contract
must be made explicit and tested.

**Status:** Closed and independently reviewed `SHIP` at `ac29c51`
(implementation `1f98a7d`, report `WEAKNESS-W05-PACKAGE-REPORT.md`). Validated
prompt events now complete once with a zero-effect receipt; SessionEnd evidence
behavior remains unchanged.

### W-06 — V1 task-unaware ranking (P1)

`context-compiler.py`, `memory-retriever.py` and `hybrid-search.py` rank by
type, confidence, freshness and lexical signals without the current task.
Tie behavior can depend on input/file order. This remains behind the evaluation
and retrieval-quality gates; no ranking tuning starts from this audit alone.

**W-06A status:** The bounded SessionStart bootstrap slice is independently
shipped at `cc1c0b5` (implementation/tests `8270fef`, report
`WEAKNESS-W06A-PACKAGE-REPORT.md`). It uses resolved project-state lexical
relevance, fixed normalized weights and deterministic identity/content
tie-breaking. The broader task-aware retrieval work in
`memory-retriever.py`/`hybrid-search.py` remains deferred behind evaluation
gates.

### W-07 — Reminder/continuity is not an automatic product path (P2)

Session end queues an event, but continuity files are still updated through
legacy/manual maintenance. This needs a bounded runtime contract after capture
reliability is fixed.

### W-08 — Persistence consistency gaps (P1/P2)

Backup reads multiple authorities without a coordinated snapshot; registry
writes lack revision/CAS and fsync parity; state references can race memory
lifecycle changes; and API update paths can bypass typed lifecycle checks.
These are separate authority packages and are intentionally not mixed with W-01.

## Current package selection

**Next package:** W-07 reminder/continuity runtime contract.
**Closed packages:** W-01 context related-note boundary — `SHIP`, report in
`WEAKNESS-W01-PACKAGE-REPORT.md`; W-02 capture queue transition crash safety —
`SHIP`, report in `WEAKNESS-W02-PACKAGE-REPORT.md`; W-03A transcript path
confinement — `SHIP`, report in `WEAKNESS-W03A-PACKAGE-REPORT.md`; W-04 late
transcript durability — `SHIP`, report in `WEAKNESS-W04-PACKAGE-REPORT.md`; W-05
prompt event terminal semantics — `SHIP`, report in
`WEAKNESS-W05-PACKAGE-REPORT.md`; W-06A V1 bootstrap ranking — `SHIP`, report
in `WEAKNESS-W06A-PACKAGE-REPORT.md` and independent review
`WEAKNESS-W06A-INDEPENDENT-REVIEW.md`.
**Required outcome:** a bounded reminder/continuity runtime contract,
evidence-backed focused tests, full regression, critical lint/compile checks,
and independent read-only review. Broader W-06 retrieval remains an explicit
deferred package rather than being treated as complete.
**Explicitly deferred:** V2 promotion, ranking changes, Phase 20, and all
canonical persistence changes.

This document is a living audit record. Scores may go down when a stronger
holdout or real-use measurement reveals that an earlier estimate was too
optimistic.
