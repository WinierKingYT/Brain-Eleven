# Engineering Weak-Points Audit — Initial Baseline

**Audit date:** 2026-09-15
**Program:** Engineering Weak-Point Improvement Goal  
**Evidence revision:** `02c05c0` (W-21 exact implementation/review head)
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW

This is the first evidence-backed audit pass. A passing regression suite is
not treated as proof that product quality is high; the scores below reflect
the behavior and operational evidence found in the current repository.

## Baseline verification

- Full local suite at the committed W-21 evidence revision: **1329 passed, 4
  skipped, 2 dependency deprecation warnings**.
- W-07B process recovery evidence: **18 passed** across intent, claim,
  staging, publication and service-restart boundaries; native authenticated
  trust, latency and dogfood gates remain open.
- W-19A reminder-authority evidence: **22 focused tests passed** across newest
  clean/degraded suppression, timestamp/state validation, deterministic ties,
  unreadable reports and read-only canonical revision checks.
- W-20 embedding-cache evidence: **40 focused tests passed** across atomic
  publication, process crash/concurrency, durable clear, stale-reader
  refresh, deterministic merge and canonical/ranking isolation.
- W-21 V2 authority-coverage evidence: **114 focused tests passed** across
  missing/empty/partial/duplicate coverage, complete SUCCESS/DEGRADED
  behavior, OFF/stale precedence, content-free telemetry and read-only
  filesystem behavior.
- No production files were changed during the initial audit.
- The current working tree already contained pre-existing untracked evidence
  directories; they were left untouched.

## Preliminary scorecard

| Area | Score | Evidence / status |
|---|---:|---|
| Persistence and concurrency | 8.7 | W-08A registry durability/revision/CAS, W-08B coordinated backup, W-08C state-reference TOCTOU, W-08D typed API lifecycle, W-14 archive/state linearization, W-15 runtime-config CAS, W-16 append-boundary validation, W-18 parent-directory durability and W-20 embedding-cache atomic/no-loss publication are independently shipped; lower-priority durability gaps remain open. |
| Scope and fail-closed safety | 8.7 | W-13 root/ID consistency, W-14 archived-state linearization, W-16 malformed-record rejection, W-17 runtime path containment and W-21 complete V2 authority coverage are independently shipped. |
| Capture runtime | 8.5 | Claim/retry/lease crash-loss, late known-locator durability, transcript ownership and completed-folder terminal-state recovery are independently shipped; native end-to-end trust and broader daily-use behavior remain separate concerns. |
| Evaluation quality | 9.0 | W-09 and W-09A independently shipped explicit gate semantics, source/corpus/candidate reconciliation, same-input V1/V2 measurement, content-free reports and hard safety counters. Retrieval quality itself remains low and visible. |
| Semantic retrieval correctness | 6.0 | Active search still depends on legacy embedding path and lexical fallback; provider abstraction is not the active authority. |
| Retrieval quality | 4.5 | Broader task-aware retrieval remains open; W-06A only improves the V1 bootstrap slice. |
| Task understanding | 8.5* | Deterministic task model has strong parity evidence; marked provisional until the whole task/context boundary is audited. |
| Extraction intelligence | 7.0* | Safety and semantic layers exist, but full real-use quality is not yet independently measured. |
| Correction/lifecycle | 8.0* | B1/B2 package reviews are shipped; natural-reference quality and real-use evidence remain incomplete. |
| Context compilation | 6.8 | Related-note boundary, V1 bootstrap relevance/order and bounded structured native continuity are shipped; V2 is shadow-only. |
| V2 runtime readiness | 6.5 | W-10's explicit provider/approval delivery gate and W-21 authority-coverage fail-closed boundary are independently shipped; V2 remains SHADOW and current quality comparison remains below V1, so promotion is still blocked. |
| Reminder/continuity runtime | 6.5 | W-19A makes the newest valid maintenance report authoritative and W-19B exposes native warning/error health; authenticated trust, latency and broader dogfood remain open. |
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

**W-03B audit status:** A read-only native smoke reproduced a P1 ownership
gap: a transcript file inside a trusted Claude root, but belonging to an
unrelated session, was accepted when the hook supplied a different session
identifier. `capture_provenance.py` proves path containment only;
`worker.py` passes the claimed session/project into `read_increment`, and
`evidence.py` records those claims without matching them to transcript
metadata or the native path identity. The bounded successor contract must
define session/project ownership evidence, fail closed on mismatch, preserve
late-file retry behavior, and add content-free cross-session/cross-project
tests. Implementation is now independently `SHIP`ped at exact review head
`f1d8896`; ownership validation and replacement detection are closed without
automatic project inference.

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
evaluation-only implementation is independently reviewed `SHIP` at exact
review head `32d158f`. The bounded P1-A canonical final-holdout path and P1-B
historical W-06C0 scope compatibility are both closed. Focused W-06C0 plus
W-06C0R1 tests pass 31/31, full suite passes 1112 with two dependency
warnings, and no runtime retrieval or Phase 20 work was introduced.

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

**W-07B audit status:** The bounded runtime implementation is pushed at exact
head `f322d2c`. It schedules verified SessionEnd maintenance asynchronously,
binds reports to project/source revisions, enforces content-free projections,
reconciles enqueue/publication crash gaps, and fences active duplicate claims
with an expiring lease. Follow-up evidence at `7707a1e` adds 18 deterministic
process/restart repetitions with canonical revision preservation and full
regression (1291 passed). Independent read-only review remains
`FIX-FIRST`: authenticated Claude/Codex trust, latency matrix and multi-
session dogfood are still missing. The package remains `FIX-FIRST / NOT
ACCEPTED`; no automatic markdown writes or Phase 20/V2 promotion were
introduced.

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

**W-07B evidence update:** The former P2 implementation gap has a bounded
runtime package at exact head `f322d2c`. Process/restart evidence is now
covered at `7707a1e` (18 passed; full suite 1291 passed), but the independent
verdict remains `FIX-FIRST / NOT ACCEPTED` until authenticated native
executable, latency and dogfood evidence are closed. Automatic
markdown writes remain deferred.

**W-09A status:** Independently reviewed `SHIP` at exact review head
`31a436c` in `WEAKNESS-W09A-INDEPENDENT-REVIEW.md` (review commit
`c6dc3bb`). The evaluation-only boundary now runs V1 and V2 on identical
`evals/corpus-v2` DEV+TEST inputs, fingerprints source/corpus/candidate
snapshots, enforces K/label/safety gates, and keeps HOLDOUT separate. Public
quality is measured but weak (V1 precision 0.1723, V2 0.1472; V2 remains
below V1), so no retrieval tuning or V2 promotion is implied.

### W-10 — V2 shadow output reaches live client injection (P1)

The repository previously allowed a normal V2-rendered result to cross the
native model boundary while the product status was `SHADOW`. This was a
rollout-boundary defect, not a retrieval-quality result. The bounded contract
is
[`WEAKNESS-W10-V2-DELIVERY-GATE-CONTRACT.md`](WEAKNESS-W10-V2-DELIVERY-GATE-CONTRACT.md)
at `a867f2d`; it defines the explicit legacy V1 source for normal turns,
keeps the W06B path separate, and requires V2 comparison output to stay out of
client injection while SHADOW. Status: **CLOSED / SHIP** at exact code/test
revision `911564a`; independent review verified the 64-marker cap, fail-closed
metadata gate, no authority/canonical-write changes, and 1178-test full
regression. No V2 promotion is authorized by this finding.

### W-11 — W-06B selector drops normalized global memories (P2)

`brain_eleven/runtime/task_aware.py` admits global candidates only when
`project_id is None`, while canonical global records are normalized by
`scripts/memory_scope.py` to `scope="global", project_id=""`. A relevant global
decision can therefore be present in the compiler ranking but disappear from
the task-aware selection, producing an empty result. This affects the already
rejected opt-in W-06B path and is not a default-path regression, but it would
invalidate future evaluation. The bounded selector fix uses canonical
`infer_memory_scope()` and preserves foreign-project exclusion. Status:
**CLOSED / SHIP** at exact implementation revision `2efb943`; focused
isolation and full-regression evidence are recorded in
[`WEAKNESS-W11-GLOBAL-MEMORY-SELECTOR-PACKAGE-REPORT.md`](WEAKNESS-W11-GLOBAL-MEMORY-SELECTOR-PACKAGE-REPORT.md).

### W-12 — Derived router/compiler cache read-modify-write is unsynchronized (P2)

`context_router/cache.py` and `context_compiler_v2/cache.py` rewrite access
timestamps and read-modify-write cache snapshots without a shared lock; some
paths use direct `write_text()` rather than atomic replacement. A 16-writer
temporary-vault stress probe retained only one completed entry in repeated
runs and observed replacement errors. Canonical stores are unaffected, but
cache loss causes misses, latency spikes and unstable operational behavior.
The bounded fix applies the existing sidecar lock to complete read-modify-write
and access refresh paths, uses atomic fsync/replace, and fails open on cache
lock/write errors. Status: **CLOSED / SHIP** at exact implementation revision
`4cde804`; focused, process-stress, and full-regression evidence is recorded in
[`WEAKNESS-W12-DERIVED-CACHE-CONCURRENCY-PACKAGE-REPORT.md`](WEAKNESS-W12-DERIVED-CACHE-CONCURRENCY-PACKAGE-REPORT.md).
`authority/cache.py` had the same pre-existing race. The bounded W-12A fix now
guards its full store and validated-hit refresh operations with the existing
sidecar lock and atomic writer. Status: **CLOSED / SHIP** at exact
implementation revision `d33b38d`; process-stress, raw-reader, failure-path
and full-regression evidence is recorded in
[`WEAKNESS-W12A-AUTHORITY-CACHE-CONCURRENCY-PACKAGE-REPORT.md`](WEAKNESS-W12A-AUTHORITY-CACHE-CONCURRENCY-PACKAGE-REPORT.md) and the independent review in
[`WEAKNESS-W12A-AUTHORITY-CACHE-CONCURRENCY-INDEPENDENT-REVIEW.md`](WEAKNESS-W12A-AUTHORITY-CACHE-CONCURRENCY-INDEPENDENT-REVIEW.md).

### W-13 — Supplied project root and project ID can disagree (P1)

`scripts/memory_scope.py` derives the registered identity from `project_root`
but retains a caller-supplied `project_id`; `brain_eleven/memory/capture.py`
and `scripts/search-api.py` accept both values. A capture using project A's
root with project B's ID persisted project-A-labelled content under project B.
This violates the zero wrong-project-leakage invariant. Status:
**CLOSED / SHIP** at exact code revision `cc344e3`; current evidence/document
head is `366835b`. The shared resolver requires an exact registry match for
root+ID pairs, rejects unregistered explicit IDs without creating a registry
entry, and preserves root-only auto-registration/relocation. Focused
scope/capture/API coverage, full regression, and independent review are
recorded in `WEAKNESS-W13-PROJECT-ROOT-ID-PACKAGE-REPORT.md`.

### W-14 — Archived project can race a state mutation (P1)

`StateService` checks project activity before taking the state lock, while a
concurrent registry archive can commit between that check and the state
transaction. A fault-injected probe archived a project and then observed a
successful requirement write after archive. Status: **CLOSED / SHIP** at exact
head `aef19b8`; the shared registry sidecar lock now spans the active check and
state transaction. Archive-first/mutation-first race evidence, timeout
mapping, full regression, and independent review are recorded in
`WEAKNESS-W14-ARCHIVED-STATE-RACE-PACKAGE-REPORT.md`.

### W-15 — Runtime rollout/config updates can lose concurrent operator changes (P1)

`RuntimeConfig.set_mode()` and `set_human_approval()` load and rewrite the
whole config without a shared lock or revision/CAS. A delayed mode write can
erase a later approval change, and a delayed CANARY/ACTIVE write can override
a later operator `OFF`. Status: **CLOSED / SHIP** at exact package head
`7fd9d5a`; the final commit now reloads under the existing `config.json`
sidecar lock and rejects a changed snapshot with `RuntimeConfigConflict`.
The installer’s project-ID/mode update uses the same current-config lock
boundary. Full regression, race evidence and independent review are recorded
in `WEAKNESS-W15-RUNTIME-CONFIG-CAS-PACKAGE-REPORT.md` and
`WEAKNESS-W15-RUNTIME-CONFIG-CAS-INDEPENDENT-REVIEW.md`.

### W-16 — Public `MemoryStore.append()` accepts malformed canonical records (P2)

The public append surface validated the document envelope but accepted
arbitrary dictionaries without a minimum record boundary. A malformed record
could therefore be persisted directly, even though no current production
caller was found. Status: **CLOSED / SHIP** at exact review head `3406d7b`;
`_validate_record()` now rejects malformed required fields, explicit null
lifecycle/scope fields, invalid supplied types and inconsistent scope metadata
before the existing lock/revision/atomic transaction. Evidence is recorded in
[`WEAKNESS-W16-MEMORY-APPEND-PACKAGE-REPORT.md`](WEAKNESS-W16-MEMORY-APPEND-PACKAGE-REPORT.md)
and the independent review in
[`WEAKNESS-W16-MEMORY-APPEND-INDEPENDENT-REVIEW.md`](WEAKNESS-W16-MEMORY-APPEND-INDEPENDENT-REVIEW.md).

### W-17 — Runtime config writes follow symlinked/reparse runtime paths (P2)

`brain_eleven/runtime/storage.py::write_json()` creates directories and
replaces files without rejecting symlink/reparse path components. A temporary
vault with `.brain-eleven/runtime` redirected caused an approval update to
write outside the vault. Status: **CLOSED / SHIP** at exact implementation
revision `6017255c3405dfdbc8d9d154498c7a5edd5f7649`; runtime-owned writes and
locks now use component-level no-follow/reparse checks, identity revalidation,
descriptor-relative POSIX target locks and Windows target-scoped mutexes.
Evidence is recorded in
`WEAKNESS-W17-RUNTIME-CONFIG-PATH-CONTAINMENT-PACKAGE-REPORT.md` and the
independent review in
`WEAKNESS-W17-RUNTIME-CONFIG-PATH-CONTAINMENT-INDEPENDENT-REVIEW.md`.

### W-18 — MemoryStore replacement does not fsync the parent directory (P2)

`scripts/memory_store.py` fsyncs its temporary file but not the containing
directory after `replace()`, leaving rename durability weaker than the
ProjectRegistry and coordinated backup paths after power loss. Status:
**CLOSED / SHIP** at exact implementation revision `bc393e7`; supported POSIX
hosts now fsync the parent directory after replacement, while Windows keeps the
explicit file-fsync-only behavior. Fault visibility, cleanup, ordering, full
regression and independent review are recorded in
`WEAKNESS-W18-MEMORY-PARENT-FSYNC-PACKAGE-REPORT.md` and
`WEAKNESS-W18-MEMORY-PARENT-FSYNC-INDEPENDENT-REVIEW.md`.

### W-19A — Newer maintenance reports could fall back to stale reminders (P2)

`brain_eleven/runtime/maintenance_delivery.py::latest_reminder` previously
continued scanning after a current-revision report was valid but clean,
degraded or marked not to surface. A newer run could therefore expose an
older anomaly reminder again. The bounded fix validates timezone-aware
`generated_at`, matches an explicit current state revision including `None`,
handles report enumeration/read races, and selects one deterministic newest
report before interpreting its surface flag.

**Status:** Independently reviewed **SHIP** at exact head `352f51b`. The W-19A
focused suite has 22 passing tests and the full suite has 1298 passed, 4
skipped and 2 dependency warnings. No canonical store, retrieval, V2 or
Phase 20 behavior changed. Evidence is recorded in
`WEAKNESS-W19A-STALE-REMINDER-PACKAGE-REPORT.md` and the contract review is
recorded in `WEAKNESS-W19A-STALE-REMINDER-CONTRACT.md`.

### W-19B — Native hook health can report false green (P1 candidate)

The native launcher records `last-hook.status="OK"` when its service-unavailable
warning returns normally, while doctor and runtime status primarily inspect a
legacy breadcrumb. SessionStart can also return before writing current
privacy-safe context telemetry. This could make a failed or stale native path
look healthy. The bounded launcher/doctor diagnostics fix now derives
`DEGRADED` from warning-bearing output, safely reads missing/corrupt
`last-hook.json`, and surfaces native degradation as `ATTENTION`.

**Status:** Independently reviewed **SHIP** at exact head `5555318`. Focused
launcher/install/session-start evidence has 67 passing tests and the full suite
has 1304 passed, 4 skipped and 2 dependency warnings. Native client trust,
latency and dogfood remain W-07B gates; SessionStart context telemetry remains
separate. Evidence is recorded in
`WEAKNESS-W19B-NATIVE-HEALTH-PACKAGE-REPORT.md`.

### W-20 — Legacy embedding cache is non-atomic and stale in long-lived readers (P2)

The Docker production search path still constructs a long-lived legacy
`EmbeddingGenerator`. Its direct JSON overwrite can leave truncated cache data,
lose concurrent writers, and hide external updates until restart; `clear_cache`
also clears memory without durable deletion. This is an evaluation/retrieval
reliability candidate only after an explicit contract; no provider migration or
ranking tuning is authorized.

**Status:** Independently reviewed **SHIP** at exact head `db6ae44`. The cache
now publishes through the existing sidecar lock and same-directory atomic
writer, merges compatible entries without losing concurrent additions, rejects
incompatible same-ID provenance without replacing the prior snapshot, persists
clear operations, suppresses stale-writer resurrection and exposes an explicit
semantic-search refresh boundary. Process-crash, process-concurrency,
deterministic tie-break, canonical-revision and ranking-parity evidence is in
`WEAKNESS-W20-EMBEDDING-CACHE-PACKAGE-REPORT.md`; the focused suite has 40
passing tests and the full suite has 1318 passed, 4 skipped and 2 dependency
warnings. Provider selection, retrieval tuning, V2 promotion and Phase 20 are
unchanged.

### W-21 — V2 selection can accept candidates without authority coverage (P1 if promoted)

**Status:** Independently reviewed **SHIP** at exact head `02c05c0`. Missing,
empty, partial and duplicate authority coverage now fails closed before
selection with the bounded `AUTHORITY_COVERAGE_UNAVAILABLE` error. Complete
SUCCESS/DEGRADED coverage preserves selection and degraded visibility;
candidate/project scope mismatches remain omitted. The focused suite has 114
passing tests and the full suite has 1329 passed, 4 skipped and 2 dependency
warnings. V2 remains SHADOW; no promotion or Phase 20 work was introduced.

### W-22 — V2 optional-omission flag is accepted but ignored (P2)

`allow_optional_omission=false` is serialized by the V2 context models but is
not consumed by planning/rebalance; optional items are omitted under the same
budget pressure as `true`. This remains a contract decision candidate and is
not being tuned during the current W-07B acceptance work.

## Current package selection

**W-08 contract status:** `SHIP` at `90ac899`, reviewed in
`WEAKNESS-W08-CONTRACT-INDEPENDENT-REVIEW.md`. W-08A is independently
`SHIP` at `05fd7f6`; W-08C's bounded contract is independently `SHIP` at
`7f175b3`.
**Current package:** W-07B native runtime acceptance remains `FIX-FIRST / NOT
ACCEPTED` at exact evidence head `7707a1e`; its authenticated native trust,
latency matrix and multi-session dogfood gates are still open. W-19A stale
reminder authority and W-19B native health diagnostics are independently
`SHIP`ped at exact heads `352f51b` and `5555318`.
The next bounded candidate after W-07B is W-22 optional-omission contract
repair; W-21 V2 authority coverage is independently shipped at exact head
`02c05c0`.
W-06C0R1 scope-drift maintenance is independently `SHIP`ped
at exact implementation head `942aee8`, W-03B transcript ownership/provenance
is independently `SHIP`ped at exact review head `f1d8896`, and the W-02
completed-folder terminal-state successor is independently `SHIP`ped at exact
review head `ed54bfa`. W-07B's contract is independently `SHIP` at exact
revision `acebec1`, but its runtime package remains `FIX-FIRST / NOT ACCEPTED`
at exact head `f322d2c`. W-06 retrieval work remains evaluation-only and must
not tune HOLDOUT, promote V2 or open Phase 20. W-15 runtime-config lost-update
protection is independently `SHIP`ped at exact package head `7fd9d5a`; W-16
append-boundary validation is independently `SHIP`ped at exact review head
`3406d7b`; W-17 runtime path containment and W-18 parent-directory durability
are now independently `SHIP`ped. W-12A authority-cache concurrency is also
independently `SHIP`ped at exact implementation revision `d33b38d`; the next
bounded candidate is W-07B. W-10's
delivery gate is independently SHIP at exact review head `911564a`; W-07B's
runtime package remains FIX-FIRST / NOT ACCEPTED.
W-08D is closed at 8.0 for persistence/concurrency, 8.0 for scope/fail-closed
mutation safety, and 8.0 for API lifecycle reliability.
W-17 runtime-owned path containment is independently `SHIP`ped at exact
implementation revision `6017255`, with final evidence documentation at
`7c159a3`.
W-18 MemoryStore parent-directory durability is independently `SHIP`ped at
exact implementation revision `bc393e7`, with final evidence documentation at
`287c438`.
W-12A AuthorityCache concurrency is independently `SHIP`ped at exact
implementation revision `d33b38d`, with final evidence documentation at
`587c72f`.
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
W-20 legacy embedding-cache durability — `SHIP` at exact review head
`db6ae44`, report in `WEAKNESS-W20-EMBEDDING-CACHE-PACKAGE-REPORT.md` and
independent implementation review recorded there.
W-21 V2 authority coverage — `SHIP` at exact review head `02c05c0`, report in
`WEAKNESS-W21-V2-AUTHORITY-COVERAGE-PACKAGE-REPORT.md` and independent review
recorded there.
W-06C0R1 evaluation corpus/provenance remediation — `SHIP` at exact review
head `32d158f`, report in `WEAKNESS-W06C0R1-PACKAGE-REPORT.md` and independent
review `WEAKNESS-W06C0-REMEDIATION-CONTRACT-INDEPENDENT-REVIEW.md`.
W-03B transcript ownership/provenance — `SHIP` at exact review head `f1d8896`,
report in `WEAKNESS-W03B-PACKAGE-REPORT.md` and independent review in
`WEAKNESS-W03B-TRANSCRIPT-OWNERSHIP-INDEPENDENT-REVIEW.md`.
W-02 completed-folder terminal-state closure — `SHIP` at exact review head
`ed54bfa`, report in `WEAKNESS-W02-TERMINAL-STATE-PACKAGE-REPORT.md` and
independent review in `WEAKNESS-W02-TERMINAL-STATE-INDEPENDENT-REVIEW.md`.
W-02 completed-folder terminal-state closure — `SHIP` at exact review head
`ed54bfa`, report in `WEAKNESS-W02-TERMINAL-STATE-PACKAGE-REPORT.md` and
independent review in `WEAKNESS-W02-TERMINAL-STATE-INDEPENDENT-REVIEW.md`.
W-13 project-root/project-ID consistency — `SHIP` at exact code revision
`cc344e3`, report in `WEAKNESS-W13-PROJECT-ROOT-ID-PACKAGE-REPORT.md` and
independent implementation review recorded at test/documentation head
`366835b`.
W-14 archived-state mutation race — `SHIP` at exact implementation revision
`aef19b8`, report in `WEAKNESS-W14-ARCHIVED-STATE-RACE-PACKAGE-REPORT.md` and
independent review recorded at evidence head `439a62c`.
W-15 runtime-config lost-update protection — `SHIP` at exact package head
`7fd9d5a`, report in `WEAKNESS-W15-RUNTIME-CONFIG-CAS-PACKAGE-REPORT.md` and
independent review in `WEAKNESS-W15-RUNTIME-CONFIG-CAS-INDEPENDENT-REVIEW.md`.
W-16 malformed canonical append validation — `SHIP` at exact review head
`3406d7b`, report in `WEAKNESS-W16-MEMORY-APPEND-PACKAGE-REPORT.md` and
independent review in `WEAKNESS-W16-MEMORY-APPEND-INDEPENDENT-REVIEW.md`;
W-18 MemoryStore parent-directory durability — `SHIP`, report in
`WEAKNESS-W18-MEMORY-PARENT-FSYNC-PACKAGE-REPORT.md` and independent review in
`WEAKNESS-W18-MEMORY-PARENT-FSYNC-INDEPENDENT-REVIEW.md`; W-12A AuthorityCache
concurrency — `SHIP`, report in
`WEAKNESS-W12A-AUTHORITY-CACHE-CONCURRENCY-PACKAGE-REPORT.md` and independent
review in
`WEAKNESS-W12A-AUTHORITY-CACHE-CONCURRENCY-INDEPENDENT-REVIEW.md`.
**Required outcome:** W-09 and W-09A are complete as measurement-boundary
corrections. W-06B's lexical design is rejected by independent evidence; its
successor must improve retrieval against the frozen W-09A evidence without
tuning HOLDOUT, leaking scope, promoting V2, or opening Phase 20.
W-07B automatic markdown maintenance remains deferred; bounded native delivery
is implemented but not accepted until its remaining evidence gates pass.
**Explicitly deferred:** V2 promotion, ranking changes, Phase 20, and all
canonical persistence changes.

This document is a living audit record. Scores may go down when a stronger
holdout or real-use measurement reveals that an earlier estimate was too
optimistic.

## W-06C0R1 scope-drift maintenance (2026-09-14)

The W-03B full regression exposed a historical evaluator boundary defect:
`evals/w06c0r1/evaluation.py::verify_scope_diff()` compared its frozen base
with the current repository and incorrectly included later W-03B files. The
bounded maintenance package pins the historical range to
`3f795f94dde199ba4e970705d37686ee4f50bc5d` →
`0b5a262c437da13813e542c569857a68c2db7a69`, preserves the original allowlist
and old W-06C0 compatibility exception, and now hash-binds the immutable R4
maintenance anchor. R1, R2, and R3 pin files remain byte-identical historical
artifacts; R4 is the canonical pin.

Exact evidence at implementation revision `a6ac097`: W-06C0/W-06C0R1
focused **36 passed**;
W-03B/capture focused **127 passed, 2 warnings**; clean full suite
**1124 passed, 2 warnings**; critical flake8, compileall, manifest/seal, and
diff checks passed. Corpus cases, labels, provider metrics, runtime,
retrieval, V2, and Phase 20 were unchanged. Independent implementation review
at exact head `942aee8` returned `SHIP`; no P0/P1/P2 findings remain.

**W-06C0R1 independent review:** `SHIP` at `942aee8`, recorded in
`WEAKNESS-W06C0R1-SCOPE-DRIFT-INDEPENDENT-REVIEW.md`. The R4 immutable anchor
rejects post-anchor evaluator/pin renewal and keeps the historical allowlist
unchanged.
