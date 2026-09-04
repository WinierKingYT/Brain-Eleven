# Brain-Eleven v3 — Current Project Status

**Last updated:** 2026-09-04
**Current milestone:** Context Engine Foundation V1 — **CI VERIFIED / INDEPENDENT REVIEW PENDING**. Phases 15–19 remain shadow-safe where applicable; [Validation run #52](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33896562025) is green and produced revision-bound Phase 15–19 plus Foundation evidence for `e5c1069`. Independent read-only review remains required before any graduation, tag, or frozen claim.

## Status vocabulary

| Status | Meaning |
|---|---|
| **VERIFIED** | A bounded claim has reproducible automated evidence or a revision-bound CI result. |
| **PARTIALLY VERIFIED** | The implementation is present, but a required environment or operational check is still absent. |
| **NOT VERIFIED** | No adequate evidence exists; this is not a claim of failure. |
| **HISTORICAL** | A past implementation or validation record; it does not describe the current head. |

“Implemented” and “verified” are deliberately different: an implementation is
only **VERIFIED** when its stated evidence can be rerun or inspected.

## Product boundary

Brain-Eleven is a local, privacy-first second-brain system. Canonical memory
remains in the vault; API, hooks, context compiler, knowledge graph and search
layers consume that same validated store rather than creating parallel write
paths.

## Current evidence-backed state

| Area | Status | Evidence boundary |
|---|---|---|
| Canonical memory authority | **VERIFIED** | `MemoryStore` is the revisioned, locked and atomic canonical write boundary; malformed input and write failures are tested fail-closed. |
| Cross-project isolation | **VERIFIED** | Default retrieval admits global + current-project memory only; conflict, dedup, graph and context tests cover wrong-project exclusion. |
| Derived-state safety | **VERIFIED** | Graph and bootstrap are revisioned projections. Missing/corrupt projections rebuild; stale or scope-mismatched bootstrap is rejected. |
| Concurrent writers | **VERIFIED** | Foundation graduation tests cover 10 and 50 simultaneous state writers, 100 contested transactions, stale CAS, lock timeout and writer crash recovery with zero lost updates. |
| Backup and restore | **VERIFIED** | A manifest/checksum ZIP restores into a blank vault, preserves canonical IDs/revision/lifecycle, then rebuilds graph and context. Corrupt or overwrite targets are refused. |
| CI and release topology | **VERIFIED** | Unit, integration, coverage, Bandit, secrets, dependency and image-security gates precede the validated-image publish workflow. CI evidence is revision-bound; inspect the matching Actions run for a particular head. |
| Global `/remember` installer | **PARTIALLY VERIFIED** | The installer and portability tests are versioned; installation into each user’s global Claude configuration remains a local operational action. |
| Phase 15 evaluation harness | **PARTIALLY VERIFIED** | Offline synthetic corpus, deterministic metrics and leakage hard gates are implemented. Immutable baseline-v1 preserves the historical 101-case public measurement; versioned baseline-v2 measures a 160-case synthetic corpus with exact 70 dev / 60 test / 30 holdout boundaries. Current-worktree GitHub Actions evidence and final review remain pending. |
| Phase 15 baseline-v1 | **VERIFIED** | Public suite has 101 cases; forbidden, wrong-project, superseded and resolved leakage invariants all pass. Snapshot source fingerprint: `sha256:e6a14efb84900449924d41b63fdc10a55961d05c0bb7241c7cc13e720976a29f`. |
| Phase 16 Task + State Model | **PARTIALLY VERIFIED** | `TaskEnvelope`, deterministic analyzer, revisioned `StateStore`, typed state CLI, resolver, state-aware bootstrap lineage, canonical-state backup support, and public task/state evaluation are implemented. The local full task/state suite passes 28 task + 28 state cases with all hard gates green. The complete local suite is 422/422 passing at 84% coverage; remote CI evidence requires a pushed revision, and a separate reviewer must still provide the graduation verdict. |
| Phase 16 isolation and fail-closed behavior | **PARTIALLY VERIFIED** | The source test suite covers corruption, unsupported schemas, stale CAS, lock/write failure, AI-proposed provenance, invalid cross-project references, bootstrap staleness, and 10 concurrent state writers. The local JUnit/evaluator evidence manifest is PASS, but it is a working-tree run rather than revision-bound remote CI evidence. |
| Phase 17 Task-Aware Context Router | **PARTIALLY VERIFIED** | A read-only `context_router` produces content-free retrieval plans and candidates from Phase 16 TaskStateContext. It is limited to `OFF`/`SHADOW`, has no SessionStart or ContextCompiler injection path, and enforces trusted current/global/explicit-selected scope plus revision guards. The 160-case public+holdout suite, shadow report, graph degradation and 100-run determinism checks pass locally; revision-bound CI and independent review remain required. |
| Phase 18 Authority & Conflict Resolver | **PARTIALLY VERIFIED** | Read-only `authority` consumes Router references and canonical snapshots without schema changes. It resolves only explicit lifecycle, supersession, duplicate and typed blocker-reference metadata; free-text conflicts remain unresolved. The 180-case policy corpus, 160-case selection corpus and shadow-only provider pass locally. Revision-bound CI and independent review remain required. |
| Phase 19 Context Compiler V2 + Token Budgeter | **PARTIALLY VERIFIED** | Read-only `context_compiler_v2` rehydrates only Phase 18 canonical references, records router/authority/compiler lineage, enforces a caller-owned conservative token/byte budget, preserves mandatory overflow visibly, and renders safe shadow-only context. The 220-case policy corpus, 160-case selection corpus, 100/1,000/10,000-memory benchmark and all scope/secret gates pass locally. V1 and SessionStart remain active; V2’s current shadow relevance metrics are diagnostic rather than a promotion claim. |
| Context Engine Foundation V1 | **PARTIALLY VERIFIED** | Phase 15–19 manifests, a 50-writer/100-transaction state suite and a 100-run deterministic cross-phase Task → State → Router → Authority → Compiler chain pass locally. The generated foundation manifest is deliberately review-pending until one GitHub Actions SHA and independent reviewers substantiate a freeze. |
| Live Docker Compose deployment (local Docker Desktop) | **VERIFIED** | On 2026-09-02, `app`, `postgres`, and `redis` became healthy; `127.0.0.1:8000/health` returned 200; the API port was unreachable through a non-loopback IPv4 address. The API key was unset, so its optional auth-gate branch was not applicable. |
| Public deployment and daily-use telemetry | **NOT VERIFIED** | Outside the local-first memory-foundation graduation boundary. |

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
  specified in `PHASE17-TASK-AWARE-CONTEXT-ROUTER-CONTRACT.md`.

- Phase 18 is intentionally an authority annotation layer, not a semantic
  truth engine or final context selector. `python -m authority shadow --request
  "..." --json` is content-free and never injects a result into a prompt.
  `python -m evals.authority_evaluation --suite all` validates the 180-case
  metadata-first corpus. See `PHASE18-AUTHORITY-CONFLICT-CONTRACT.md` for the
  frozen scope, provenance and rollout boundaries.

- Phase 19 is intentionally a constrained downstream compiler, not a router,
  authority engine, or SessionStart replacement. `python -m context_compiler_v2
  shadow --request "..." --json` creates a non-injecting V2 bundle. Its default
  token accounting is explicitly conservative, not provider-exact. The 220-case
  policy suite is `python -m evals.compiler_v2_evaluation --suite all`; use
  `python -m evals.compiler_v2_shadow --suite all` to compare the existing V1
  baseline and V2 without promotion. The current shadow comparison has lower
  relevance recall than V1, so V2 stays shadow-only pending improvement and
  independent review. See `PHASE19-CONTEXT-COMPILER-V2-CONTRACT.md`.

## Historical planning documents

Older phase plans are **HISTORICAL** execution records. They may contain
superseded assumptions; use this file and revision-bound evidence artifacts for
the current state.
