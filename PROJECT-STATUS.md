# Brain-Eleven v3 — Current Project Status

**Last updated:** 2026-09-09
**PHASE 20: FROZEN** — feature development is stopped; intelligence graduation remains **LOCKED**.
**ACTIVE PROGRAM: INTELLIGENCE GRADUATION (IG)**.
**LAST CLOSED PACKAGE: IG-01 Evaluation Foundation — CLOSED / SHIPPED**.
**ACTIVE PACKAGE: IG-03 Semantic Extraction — READ-ONLY AUDIT / CONTRACT**.

The [IG program contract](INTELLIGENCE-GRADUATION.md) replaces the former “next: Phase 20” schedule. PRE-12 is a closed historical foundation record; it does not mean product intelligence is complete. PRE-13 development is preserved at `7e6f55a82465f6fef7abf8318a451308bbe9a0e9`; its quality failures and missing live-use evidence are not erased by feature freeze. IG-01 is now open under its separate [evaluation foundation contract](IG01-EVALUATION-FOUNDATION.md); implementation remains bounded to measurement work and does not authorize intelligence tuning.

The immutable `intelligence-graduation-baseline` tag binds PRE-12 commit `211bf2eb74cdb457b7b07430848bf6c6665e7f12`. Matching [Validation](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34027088697) and [Docker](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34027393699) completed successfully on that exact SHA. This is infrastructure baseline evidence, not current-head validation or intelligence graduation.

Read [IG-01 contract](IG01-EVALUATION-FOUNDATION.md), then [IG01-C evaluator contract](IG01-C-EVALUATOR-CONTRACT.md), [IG-00 status and gates](IG00-FREEZE-BASELINE.md), [IG-00 independent review](IG-00-INDEPENDENT-REVIEW.md), [actual runtime paths](RUNTIME-DATAFLOW.md), and [documentation authority](DOCUMENTATION-AUTHORITY.md) before older plans. Native V2 remains SHADOW; V1 delivery ownership correction is implemented and installed. IG-00 remains closed at `18e88876495db77a2e99ea927f01a2d28c5d9ed6`; IG01-A is shipped at immutable tag `ig01a-ship`, IG01-B is shipped at reviewed exact head `6cb4e2b584addf7ac66aa5330266c80db096c5c2`, and IG01-C is shipped at the exact revision recorded in [its package report](IG01-C-PACKAGE-REPORT.md) with independent `SHIP`. Validation/runtime evidence and the historical PRE-13 holdout quality failure remain visible. IG01-D paired baseline measurement is implemented at exact head `61c89e9934f669b5c624e5e1a921cd62e4f49b04`; [its package report](IG01-D-PACKAGE-REPORT.md) records the V1/V2 comparison, no-HOLDOUT proof, strict evidence contract and semantic feasibility limitation. Independent technical review returned `SHIP` at 9/10 and the user supplied `IG01-D human checkpoint PASS`; IG01-D is fully accepted. IG01-E is shipped at `a38433090da662a35379620b223ddfade21dd5a9` with independent read-only `SHIP` at 9/10, and the user supplied `IG-01 closure human checkpoint PASS` on 2026-09-09. IG-01 is closed. IG-03 is now limited to its read-only reality audit and bounded contract; implementation is not yet authorized by the status document. Production intelligence, V2 promotion and Phase 20 remain closed.

The closed IG-00 review included a bounded semantic safety correction: when
the real embedding provider is unavailable, semantic search emits no synthetic
vectors and hybrid retrieval uses lexical-only scoring. Cached vectors now
require matching content, provider, model and dimension provenance. This is
reliability work completed inside IG-00; it does not alter the IG-01
measurement-only boundary or the Phase 20 lock.

IG01-B owns the versioned `ig-eval-v2` public corpus under
`evals/ig01b/`: 153 answerable cases across 17 phenomena and three language
strata, a separate six-case abstention set, a 39-case double-labeled holdout,
an immutable holdout hash, a guarded local-only private mechanism, and an empty
sanitized-failure reservation for IG-08. The corpus is measurement data only;
IG01-C is closed under its separate production-independent evaluator contract;
its report, exact CI evidence and independent `SHIP` are revision-bound. All
production intelligence tuning remains closed until the later baseline and
intelligence packages are separately reviewed.

The current head also closes bounded review findings without promoting any
shadow runtime: task confidence records ambiguity instead of claiming 0.95
certainty, state retrieval preserves mandatory records while ranking matches,
continuity retrieval is age-aware, graph-only candidates have their own budget,
derived caches use recent-access eviction, compiler telemetry distinguishes an
audit-manifest hit from a compiled-context hit, extraction records confidence
components, and the search corpus cache key includes content fingerprints.

## Status vocabulary

| Status | Meaning |
|---|---|
| **VERIFIED** | A bounded claim has reproducible automated evidence or a revision-bound CI result. |
| **VERIFIED (SURFACE)** | Public import/caller boundaries are verified; implementation ownership may still use a documented compatibility bridge. |
| **PARTIALLY VERIFIED** | The implementation is present, but a required environment or operational check is still absent. |
| **NOT VERIFIED** | No adequate evidence exists; this is not a claim of failure. |
| **HISTORICAL** | A past implementation or validation record; it does not describe the current head. |
| **FROZEN (Phase 20)** | Program feature freeze; does not mean technically complete or graduated. |
| **GRADUATED / FROZEN (Foundation)** | Historical completed, review-approved contract bound to its immutable Foundation tag. |
| **SHADOW** | Implemented and evaluated, but intentionally not connected to the active SessionStart delivery path. |

“Implemented” and “verified” are deliberately different: an implementation is
only **VERIFIED** when its stated evidence can be rerun or inspected.

## Product boundary

Brain-Eleven is a local, privacy-first second-brain system. Canonical memory
remains in the vault; API, hooks, context compiler, knowledge graph and search
layers consume that same validated store rather than creating parallel write
paths.

## Historical Foundation / PRE-12 evidence-backed state

| Area | Status | Evidence boundary |
|---|---|---|
| Canonical memory authority | **VERIFIED** | `MemoryStore` is the revisioned, locked and atomic canonical write boundary; malformed input and write failures are tested fail-closed. |
| Cross-project isolation | **VERIFIED** | Default retrieval admits global + current-project memory only; conflict, dedup, graph and context tests cover wrong-project exclusion. |
| Derived-state safety | **VERIFIED** | Graph and bootstrap are revisioned projections. Missing/corrupt projections rebuild; stale or scope-mismatched bootstrap is rejected. |
| Concurrent writers | **VERIFIED** | Foundation graduation tests cover 10 and 50 simultaneous state writers, 100 contested transactions, stale CAS, lock timeout and writer crash recovery with zero lost updates. |
| Backup and restore | **VERIFIED** | A manifest/checksum ZIP restores into a blank vault, preserves canonical IDs/revision/lifecycle, then rebuilds graph and context. Corrupt or overwrite targets are refused. |
| CI and release topology | **VERIFIED** | Unit, integration, coverage, Bandit, secrets, dependency and image-security gates precede the validated-image publish workflow. CI evidence is revision-bound; inspect the matching Actions run for a particular head. |
| Global `/remember` installer | **PARTIALLY VERIFIED** | The installer and portability tests are versioned; installation into each user’s global Claude configuration remains a local operational action. |
| Phase 15 evaluation harness | **GRADUATED / FROZEN** | Offline synthetic corpus, deterministic metrics and leakage hard gates are bound to the immutable `context-engine-foundation-v1` checkpoint. Immutable baseline-v1 preserves the historical 101-case public measurement; versioned baseline-v2 measures the synthetic corpus with explicit dev/test/holdout boundaries. |
| Phase 15 baseline-v1 | **VERIFIED** | Public suite has 101 cases; forbidden, wrong-project, superseded and resolved leakage invariants all pass. Snapshot source fingerprint: `sha256:e6a14efb84900449924d41b63fdc10a55961d05c0bb7241c7cc13e720976a29f`. |
| Phase 16 Task + State Model | **GRADUATED / FROZEN** | `TaskEnvelope`, deterministic analyzer, revisioned `StateStore`, typed state CLI, resolver, state-aware bootstrap lineage, canonical-state backup support, and public task/state evaluation are bound to the immutable Foundation checkpoint. The Foundation review verified isolation, stale/revision guards and canonical-write boundaries. |
| Phase 16 isolation and fail-closed behavior | **GRADUATED / FROZEN** | The revision-bound suite covers corruption, unsupported schemas, stale CAS, lock/write failure, AI-proposed provenance, invalid cross-project references, bootstrap staleness and concurrent writers. |
| Phase 17 Task-Aware Context Router | **GRADUATED / FROZEN / SHADOW** | A read-only `context_router` produces content-free retrieval plans and candidates from Phase 16 TaskStateContext. It is limited to `OFF`/`SHADOW`, has no SessionStart or ContextCompiler injection path, and enforces trusted current/global/explicit-selected scope plus revision guards. |
| Phase 18 Authority & Conflict Resolver | **GRADUATED / FROZEN / SHADOW** | Read-only `authority` consumes Router references and canonical snapshots without schema changes. It resolves only explicit lifecycle, supersession, duplicate and typed blocker-reference metadata; free-text conflicts remain unresolved. |
| Phase 19 Context Compiler V2 + Token Budgeter | **GRADUATED / FROZEN / SHADOW** | Read-only `context_compiler_v2` rehydrates only Phase 18 canonical references, records router/authority/compiler lineage, enforces a caller-owned conservative token/byte budget, preserves mandatory overflow visibly, and renders safe shadow-only context. V1 and SessionStart remain active because V2 runtime promotion is deferred. PRE-10 adds profile budgets, final-measurement verification, stronger cache privacy and expanded secret filtering; it is verified by Validation #78. |
| Context Engine Foundation V1 | **GRADUATED / FROZEN** | Phase 15–19 manifests, the state concurrency suite and deterministic cross-phase Task → State → Router → Authority → Compiler chain passed in Validation #55; the independent Foundation review returned `SHIP`; the immutable `context-engine-foundation-v1` tag binds that checkpoint. Current post-tag hardening is tracked separately below. |
| Live Docker Compose deployment (local Docker Desktop) | **VERIFIED** | On 2026-09-02, `app`, `postgres`, and `redis` became healthy; `127.0.0.1:8000/health` returned 200; the API port was unreachable through a non-loopback IPv4 address. The API key was unset, so its optional auth-gate branch was not applicable. |
| Public deployment and daily-use telemetry | **NOT VERIFIED** | Outside the local-first memory-foundation graduation boundary. |

## Historical Pre-Phase 20 execution status

The post-foundation hardening program is being delivered as bounded packages.
Each package is considered **VERIFIED** only after its implementation commit
and the matching cross-platform Validation and Docker workflows are green.
This is package verification, not a claim that the entire Pre-Phase 20
program is graduated.

| Package | Status | Revision-bound evidence |
|---|---|---|
| PRE-01 Capture event contract | **VERIFIED** | `e9f1d11` / `f85245`; Validation #58; Docker #58. |
| PRE-02 Durable fast-path queue | **VERIFIED** | `9397a02` / `3cad82e`; Validation #60; Docker #60. |
| PRE-03 Evidence reader and retention | **VERIFIED** | `534a348`; Validation #61; Docker #61. |
| PRE-04 Extraction V2 foundation | **VERIFIED** | `076ec56`; Validation #62; Docker #62. |
| PRE-05 Temporal provenance migration | **VERIFIED** | `9c65845` / `129f24d`; Validation #64; Docker #64. |
| PRE-06 Memory truth and lifecycle | **VERIFIED** | `9fdc329` / `3a962f1`; Validation #66; Docker #66. |
| PRE-07 State boundary integration | **VERIFIED** | `1ac8a8e` / `0be180e`; Validation #71; Docker #71. |
| PRE-08 Retrieval decision V2 | **VERIFIED** | `d422788` / `b0ad09b` / `dd8906d`; Validation #75; Docker #75. |
| PRE-09 Diversity, coverage and density | **VERIFIED** | `f78ffc3` / `4f730b1`; Validation #77; Docker #77. |
| PRE-10 Compiler V2 production hardening | **VERIFIED** | `53e16c9`; Validation #78; [Docker run #78](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33992047104). Profile budgets, final render remeasurement, cache content-safety checks and expanded secret screening are verified. Runtime promotion remains deferred; V1 and SessionStart remain active. |
| PRE-11 Private real-use evaluation and derived feedback | **VERIFIED** | `64604f3`; [Validation #80](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33992641072); [Docker #80](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33992964482). Local-only annotations, explicit private-data boundary, deterministic scoring and non-authoritative observable usage telemetry are covered. |
| PRE-12 Compatibility-surface consolidation | **VERIFIED (SURFACE)** | Packages 1–24 and the final read-only closure audit established stable public package surfaces and migrated callers. The surface covers project identity, memory, state, graph, extraction, search, support, locking, lifecycle, router, authority, compiler, evaluation, hooks, API, backup, validation, maintenance, manual capture, and migration callers. The closure audit baseline is `a77d88a`; [Validation #135](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34026682142) and [Docker #135](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34026970572) passed. Implementation ownership is not yet fully consolidated: selected `brain_eleven.*` modules still bridge to `scripts/` compatibility implementations. |

## Runtime graduation evidence

The manifest is generated, never edited by hand:

```powershell
python scripts/graduation_evidence.py run --output .phase-evidence/phase14-graduation.json
```

It records the exact test count, coverage, runtime, invariant outcomes,
wrong-project leakage and lost-update metrics from JUnit/Cobertura output.
The artifact is intentionally ignored by Git. In GitHub Actions, the same
manifest is produced only after all security hard gates pass and is uploaded as
the `phase14-graduation-evidence` artifact. The validation run for the Phase
14G implementation revision `004627e87ae007ad6e1a30e493b460cce49542f1`
completed successfully and retains that artifact: [GitHub Actions run 33721296500](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33721296500).
An earlier local regeneration at historical commit
`9bfdb0cad928884a5ba3a590f27fd58fe9dd9dcf` produced `PASS` with 341/341 tests,
83.11% coverage, zero wrong-project leakage, and zero lost updates. A manifest
itself does not claim live deployment verification; that separate, bounded
runtime check is recorded in the table above.

## Operational guidance

- Keep proactive capture opt-in. Register a project before enabling it and use
  project scope for project decisions; reserve global scope for intentional
  cross-project facts.
- Treat hook failures as degraded convenience behavior, never as permission to
  bypass validation or write canonical memory directly.
- Retain migration backups until normal use has been observed and a verified
  backup/restore drill has completed for the intended vault.
- Final independent Phase 14G review returned `SHIP` on 2026-09-03 with no
  current blockers after reviewing revision
  `a02f9df8a401fb24d0c1eb405be3e24d76b7ffcc` and its successful
  [Validation run 33721896260](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33721896260).
  The memory foundation is frozen: changes now require a new phase and
  revision-bound regression evidence.

- Phase 15 baseline-v1 is reproducible from the committed synthetic corpus:
  `python -m evals.baseline_snapshot --baseline baseline-v1 --check` verifies
  its 101-case historical public measurement. The current compatibility
  baseline is checked with
  `python -m evals.baseline_snapshot --baseline baseline-v2 --check` against
  130 public V2 cases. The committed historical baseline
  reports context precision `0.18415841584158418` and context recall
  `0.8168316831683168`; these are the honest baseline measurements, not release
  targets. Independent Phase 15 re-audit returned `SHIP` on 2026-09-03 with no
  P0/P1 findings. Task-aware ranking, authority resolution and conflict
  resolution remain intentionally unsupported baseline capabilities for Phase
  16, not Phase 15 safety failures.

- Phase 16 uses three distinct authorities: `MemoryStore` for durable history,
  `ProjectRegistry` for identity/lifecycle, and `StateStore` for mutable
  project truth. Use `python scripts/task_model.py analyze --vault .
  --project-root . --request "..." --json` to inspect a deterministic task
  envelope. Initialize state only for an existing active registry project, then
  mutate it through the typed `python scripts/state.py` commands with the
  expected project revision; no generic JSON patch exists.

- The Phase 16 public, offline evaluator is
  `python -m evals.task_state_eval --suite all`. A master-branch validation
  run produces the ignored `.phase-evidence/phase16-task-state.json` solely
  from its JUnit result and full evaluator report, then uploads it as the
  `phase16-task-state-evidence` artifact. That artifact and a read-only
  independent review are the remaining graduation requirements; neither is
  claimed complete by this working-tree status document.

- Phase 17 is intentionally a candidate router, not a context replacement.
  `python -m context_router --request "..." --json` emits only IDs,
  revisions, lifecycle and retrieval signals; it never writes canonical memory
  or state, and its `SHADOW` output is not injected into SessionStart. Router
  history, archived access and selected-project comparison are trusted caller
  options, never permissions inferred from user prompt text. The Phase 17
  route-expectation runner is `python -m evals.router_evaluation`; the same
  synthetic Phase 15 corpus can be measured with
  `python -m evals.run --provider router --suite smoke`. Graduation also
  requires public+holdout, performance and independent-review evidence as
  specified in `docs/history/PHASE17-TASK-AWARE-CONTEXT-ROUTER-CONTRACT.md`.

- Phase 18 is intentionally an authority annotation layer, not a semantic
  truth engine or final context selector. `python -m authority shadow --request
  "..." --json` is content-free and never injects a result into a prompt.
  `python -m evals.authority_evaluation --suite all` validates the 180-case
  metadata-first corpus. See `docs/history/PHASE18-AUTHORITY-CONFLICT-CONTRACT.md` for the
  frozen scope, provenance and rollout boundaries.

- Phase 19 is intentionally a constrained downstream compiler, not a router,
  authority engine, or SessionStart replacement. `python -m context_compiler_v2
  shadow --request "..." --json` creates a non-injecting V2 bundle. Its default
  token accounting is explicitly conservative, not provider-exact. The 220-case
  policy suite is `python -m evals.compiler_v2_evaluation --suite all`; use
  `python -m evals.compiler_v2_shadow --suite all` to compare the existing V1
  baseline and V2 without promotion. The current shadow comparison has lower
  relevance recall than V1, so V2 stays shadow-only pending improvement and
  independent review. See `docs/history/PHASE19-CONTEXT-COMPILER-V2-CONTRACT.md`.

## Historical planning documents

Older phase plans are **HISTORICAL** execution records. They may contain
superseded assumptions; use this file and revision-bound evidence artifacts for
the current state.
