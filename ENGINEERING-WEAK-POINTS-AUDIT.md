# Engineering Weak-Points Audit — Initial Baseline

**Audit date:** 2026-09-12  
**Program:** Engineering Weak-Point Improvement Goal  
**Repository revision:** `a26912c`
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW

This is the first evidence-backed audit pass. A passing regression suite is
not treated as proof that product quality is high; the scores below reflect
the behavior and operational evidence found in the current repository.

## Baseline verification

- Full local suite after W-09: **1062 passed, 2 dependency deprecation
  warnings**.
- No production files were changed during the initial audit.
- The current working tree already contained pre-existing untracked evidence
  directories; they were left untouched.

## Preliminary scorecard

| Area | Score | Evidence / status |
|---|---:|---|
| Persistence and concurrency | 8.0 | W-08A registry durability/revision/CAS, W-08B coordinated backup, W-08C state-reference TOCTOU, and W-08D typed API lifecycle are independently shipped. |
| Scope and fail-closed safety | 8.0 | Related-note, native transcript path, W-08C state-reference, and W-08D API project-scope boundaries are independently shipped; broader project/session ownership work remains open. |
| Capture runtime | 8.5 | Claim/retry/lease crash-loss and late known-locator durability are independently shipped; prompt-event semantics remain. |
| Evaluation quality | 9.0 | W-09 and W-09A independently shipped explicit gate semantics, source/corpus/candidate reconciliation, same-input V1/V2 measurement, content-free reports and hard safety counters. Retrieval quality itself remains low and visible. |
| Semantic retrieval correctness | 6.0 | Active search still depends on legacy embedding path and lexical fallback; provider abstraction is not the active authority. |
| Retrieval quality | 4.5 | Broader task-aware retrieval remains open; W-06A only improves the V1 bootstrap slice. |
| Task understanding | 8.5* | Deterministic task model has strong parity evidence; marked provisional until the whole task/context boundary is audited. |
| Extraction intelligence | 7.0* | Safety and semantic layers exist, but full real-use quality is not yet independently measured. |
| Correction/lifecycle | 8.0* | B1/B2 package reviews are shipped; natural-reference quality and real-use evidence remain incomplete. |
| Context compilation | 6.8 | Related-note boundary, V1 bootstrap relevance/order and bounded structured native continuity are shipped; V2 is shadow-only. |
| V2 runtime readiness | 4.0 | V2 is implemented and measured but not promoted; current shadow comparison remains below V1 on relevance recall. |
| Reminder/continuity runtime | 5.0 | Native V1 reads bounded project state for continuity; automatic Daily/Last Session/open-loop maintenance remains legacy/manual. |
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

**W-06B status:** The first task-aware V1 design reached independent
`RETHINK` at exact review head `a26912c` (`WEAKNESS-W06B-INDEPENDENT-REVIEW.md`).
Runtime safety, malformed-gate handling, fallback, deterministic ordering and
public safety counters are covered, but W-06B precision is about `0.18` on
both DEV and TEST against the frozen `>=0.60` contract floor; TEST precision
and MRR also regress against V1. The lexical reranking design is rejected for
promotion. A successor retrieval contract is required before further tuning;
V2 remains SHADOW and Phase 20 remains FROZEN / LOCKED.

**W-06C0 status:** The evaluation-only retrieval feasibility harness was
independently reviewed `FIX-FIRST` at `60f8e08` (implementation/test revision
`62b8aea`). It freezes split/source fingerprints, reports explicit
answerability states, measures token waste, exercises optional providers only
when explicitly requested, and enforces the package scope allowlist. The
measurement exposed two P1 gaps that remain open: TEST and HOLDOUT contain
zero answerable cases (only one DEV case is scored), and the v3
`provenance_hash` is format-checked but its two-labeler derivation cannot be
recomputed from repository evidence. No W-06C1 provider selection, retrieval
tuning, V2 promotion, or Phase 20 work is authorized until a separately
reviewed corpus/provenance remediation contract closes these gaps.

**W-06C0R1 contract status:** The corpus/provenance remediation contract is
independently reviewed `SHIP` at `f391dd6` (contract revision `946b5cd`). It
freezes an immutable corpus-v4 target, exact candidate/order/task fingerprints,
opaque provider task handles, and machine-checkable HOLDOUT sealing. Its
evaluation-only implementation is now authorized within the allowlist; no
runtime retrieval work is authorized until that package independently ships.

### W-07 — Reminder/continuity is not an automatic product path (P2)

Session end queues an event, but continuity files are still updated through
legacy/manual maintenance. This needs a bounded runtime contract after capture
reliability is fixed.

**W-07A status:** Native SessionStart structured continuity is independently
shipped at `ad8c544` (implementation `a83f93d`, baseline evidence refresh
`2fff176`, review `WEAKNESS-W07A-INDEPENDENT-REVIEW.md`). The V1 read path now
renders bounded, deterministic, project-scoped work items, requirements,
blockers, constraints and risks. Automatic markdown reminder writing remains
open and is not implied by this package.

### W-08 — Persistence consistency gaps (P1/P2)

Backup reads multiple authorities without a coordinated snapshot; registry
writes lack revision/CAS and fsync parity; state references can race memory
lifecycle changes; and API update paths can bypass typed lifecycle checks.
These are separate authority packages and are intentionally not mixed with W-01.

**W-08A status:** Independently reviewed `SHIP` at `05fd7f6` (implementation
`7fc2860`, tests `a2b065d` plus integrity evidence `05fd7f6`, review
`WEAKNESS-W08A-INDEPENDENT-REVIEW.md`). ProjectRegistry revision/CAS,
durable atomic writes, backup envelope, stale-safe monotonic rollback and
complete identity/status/opt-in rollback integrity are covered. W-08B
coordinated backup and W-08C state-reference TOCTOU are independently shipped;
W-08D typed API lifecycle contract is independently `SHIP` at exact revision
`f4d83b1` in `WEAKNESS-W08D-CONTRACT-INDEPENDENT-REVIEW.md`; implementation is
independently `SHIP` at exact head `a9c64cf` in
`WEAKNESS-W08D-INDEPENDENT-REVIEW.md`.

**W-08B contract status:** Independently reviewed `SHIP` at `17954cc` in
`WEAKNESS-W08B-CONTRACT-INDEPENDENT-REVIEW.md`. The amended contract freezes
the three-attempt/five-second retry and error boundary, destination
no-clobber publication with durability evidence, read-time no-follow
symlink/reparse containment and project-identifier privacy assertions. The
**W-08B implementation status:** Independently reviewed `SHIP` at exact head
`90336ee` in `WEAKNESS-W08B-INDEPENDENT-REVIEW.md` after the bounded privacy
correction `e4df824`. The focused suite (35), full suite (1018) and critical
static gates pass; malformed registry validation now emits content-free
errors. W-08C implementation is independently shipped at exact review
 revision `ecee32b` in `WEAKNESS-W08C-INDEPENDENT-REVIEW.md`. W-08D typed API
 lifecycle is independently shipped; its focused, combined, full-suite and
 privacy/CAS evidence is recorded in `WEAKNESS-W08D-INDEPENDENT-REVIEW.md`.

**W-08C contract status:** Independently reviewed `SHIP` at `7f175b3` in
`WEAKNESS-W08C-CONTRACT-INDEPENDENT-REVIEW.md`. The contract freezes the
memory-lock-then-state-lock linearization guard, lifecycle/status policy,
 scope isolation, stale-CAS/replay/audit behavior, privacy boundary and
holdout-preserving evidence requirements. The contract was accepted
 separately; the implementation status follows.
**W-08C implementation status:** Independently reviewed `SHIP` at exact head
`ecee32b`; the bounded memory-lock/state-lock guard, lifecycle policy, CLI
mapping, privacy evidence, and frozen evaluation boundary all passed review.
W-08D typed API lifecycle contract is independently `SHIP` at `f4d83b1` in
`WEAKNESS-W08D-CONTRACT-INDEPENDENT-REVIEW.md`; implementation is independently
`SHIP` at `a9c64cf` in `WEAKNESS-W08D-INDEPENDENT-REVIEW.md`.

**W-09 audit finding:** Evaluation Evidence Integrity & Gate Semantics is a
bounded P1 weakness. `evals/ig01c/engine.validate_report()` accepts some
self-consistent but tampered case/gate rows without reconciling them to the
source cases; `evals/run.py` can report a safety-only `gate: pass` while the
quality result is unavailable or materially below target. Exact public/holdout
measurements remain visible (V1 public precision `0.1800`, V2 public
precision `0.1472`; V1 holdout `0.1733`, V2 holdout `0.1026`). No retrieval or
corpus tuning is authorized by this finding.

**W-09 status:** Independently reviewed `SHIP` at exact head `c90a9ca` in
`WEAKNESS-W09-INDEPENDENT-REVIEW.md` (final review commit `3dce089`). The
bounded implementation now distinguishes unsupported safety from pass,
separates quality/evidence/measurement/promotion, reconciles IG01-C/IG01-D
source and public split identity, fails closed on pair-gate tampering, bounds
generic identifiers and content-free errors, and records reproducible public
split/report hashes. Retrieval quality, corpus labels, V2 and Phase 20 were
unchanged.

**W-07B audit finding:** Native maintenance/reminder delivery remains a P2
weakness. Native SessionEnd/worker paths do not invoke post-session maintenance,
and native SessionStart does not consume the derived report. A future bounded
contract must define trigger, revision/freshness, idempotence, project scope and
privacy-safe signals before implementation; automatic markdown writes remain
deferred.

**W-09A status:** Independently reviewed `SHIP` at exact review head
`31a436c` in `WEAKNESS-W09A-INDEPENDENT-REVIEW.md` (review commit
`c6dc3bb`). The evaluation-only boundary now runs V1 and V2 on identical
`evals/corpus-v2` DEV+TEST inputs, fingerprints source/corpus/candidate
snapshots, enforces K/label/safety gates, and keeps HOLDOUT separate. Public
quality is measured but weak (V1 precision 0.1723, V2 0.1472; V2 remains
below V1), so no retrieval tuning or V2 promotion is implied.

## Current package selection

**W-08 contract status:** `SHIP` at `90ac899`, reviewed in
`WEAKNESS-W08-CONTRACT-INDEPENDENT-REVIEW.md`. W-08A is independently
`SHIP` at `05fd7f6`; W-08C's bounded contract is independently `SHIP` at
`7f175b3`.
**Next package:** A bounded W-06C0 corpus/provenance remediation contract must
be independently reviewed before implementation. It must leave corpus-v3
immutable, add answerable DEV/TEST/HOLDOUT evidence in a new version, and
freeze a reproducible two-labeler provenance recipe without weakening the
quality floor or safety gates. Only after that package is accepted may a
successor W-06 retrieval contract be designed. W-07B native
maintenance/reminder delivery remains a separate P2 package and is not opened
until its trigger, freshness, idempotence, scope and privacy contract is
independently reviewed.
W-08D is closed at 8.0 for persistence/concurrency, 8.0 for scope/fail-closed
mutation safety, and 8.0 for API lifecycle reliability.
**Closed packages:** W-01 context related-note boundary — `SHIP`, report in
`WEAKNESS-W01-PACKAGE-REPORT.md`; W-02 capture queue transition crash safety —
`SHIP`, report in `WEAKNESS-W02-PACKAGE-REPORT.md`; W-03A transcript path
confinement — `SHIP`, report in `WEAKNESS-W03A-PACKAGE-REPORT.md`; W-04 late
transcript durability — `SHIP`, report in `WEAKNESS-W04-PACKAGE-REPORT.md`; W-05
prompt event terminal semantics — `SHIP`, report in
`WEAKNESS-W05-PACKAGE-REPORT.md`; W-06A V1 bootstrap ranking — `SHIP`, report
in `WEAKNESS-W06A-PACKAGE-REPORT.md` and independent review
`WEAKNESS-W06A-INDEPENDENT-REVIEW.md`; W-07A native continuity read — `SHIP`,
report in `WEAKNESS-W07A-PACKAGE-REPORT.md` and independent review in
`WEAKNESS-W07A-INDEPENDENT-REVIEW.md`; W-08A ProjectRegistry durability/CAS —
`SHIP`, report in `WEAKNESS-W08A-PACKAGE-REPORT.md` and independent review in
`WEAKNESS-W08A-INDEPENDENT-REVIEW.md`; W-08B coordinated backup snapshot —
`SHIP`, report in `WEAKNESS-W08B-PACKAGE-REPORT.md` and independent review in
`WEAKNESS-W08B-INDEPENDENT-REVIEW.md`.
**Required outcome:** W-09 and W-09A are complete as measurement-boundary
corrections. W-06B's lexical design is rejected by independent evidence; its
successor must improve retrieval against the frozen W-09A evidence without
tuning HOLDOUT, leaking scope, promoting V2, or opening Phase 20.
W-07B automatic reminder delivery remains explicit deferred work rather than
being treated as complete.
**Explicitly deferred:** V2 promotion, ranking changes, Phase 20, and all
canonical persistence changes.

This document is a living audit record. Scores may go down when a stronger
holdout or real-use measurement reveals that an earlier estimate was too
optimistic.
