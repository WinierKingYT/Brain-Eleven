# Next — plain-language status

Not a contract, not evidence — just "where are we, what's next." For SHAs,
CI runs and acceptance criteria, see `PROJECT-STATUS.md`. Update this file at
the end of a work session; keep entries to a few lines.

## Where we are

**2026-09-20** — SRT-00 is fixed on every gate that could be reproduced, but it
is still **NOT SHIP**. A remote run of the same SHA (`c61e072`, on the
non-publishing branch `ig/srt-00-ig07-ci`) is green for Ubuntu and Windows unit,
integration, privacy, coverage, security and PRE-13 runtime; the 11 master-only
Validation jobs are skipped by design; PRE-13 quality (the frozen holdout,
precision 0.169 / required recall 0.676) is still an honest FAIL. Root causes:
the W-03B fixtures were one byte off on Linux; the task CLIs' `--json` output
could not be encoded under a cp1252 Windows pipe (a real bug, now UTF-8); the
Windows backup reader mishandled short-name and UNC roots; PRE-13 measured too
little of the runtime. `SRT00-PLAN.md` records each finding, the corrections to
the earlier claims and the evidence. Nothing is pushed to `master`.
`chore/hygiene` (hook line endings, `ubuntu-24.04` pin, no `PYTHONPATH`) is
merged into the local `master` as `b30c6d5`; its remote run at `a4a3411` was
green apart from the holdout. The frozen W06C0R1 scope contract only fails while
the tree has uncommitted changes; it was not relaxed.

Holdout decision (2026-09-20, delegated by Ahmet): the frozen corpus-v2 gate
stays exactly as it is and PRE-13 promotion is deferred. No corpus, label or
threshold change is acceptable; improving retrieval quality needs its own
contract.

Active program: **Intelligence Graduation (IG)**, replacing the old
"Phase 20" plan (frozen). Last closed engineering weak-point package:
**SRT-01 Linux runtime lock protocol repair** — independent review `SHIP` at
review head `775d0d2`; implementation `335b6df`, focused tests `f0866b6`.
B1 and B2 are both closed; the earlier IG-04 B2 review queue package remains
closed as well. SRT-00 is the active stabilization package.
`INTELLIGENCE-GRADUATION.md` documents the Branch B pivot — IG-04's slot is
the Branch B track, not the original reference/correction scope (deferred,
not deleted). The earlier D0/R0 feasibility probes remain evaluation-only
evidence; see `CODEX-RESULTS-D0.md` / `CODEX-RESULTS-R0.md`.

**Ownership as of 2026-09-10:** Ahmet delegated project management — status,
documentation, quality bar and direction — to Claude. Codex executes from
Claude's instructions; Claude has no direct connection to Codex in this
environment, so Ahmet relays. See `CONTRIBUTING.md`'s Roles section.

Canonical branch: **master**. The exact baseline snapshot check passes.
SRT-01 closed the Linux POSIX lock protocol defect; exact implementation-head
evidence and terminal report-only checks are recorded in
`SRT01-LINUX-RUNTIME-LOCK-PACKAGE-REPORT.md`. SRT-00 remains active: its unit,
runtime and coverage identities are green on the remote run above, but PRE-13
quality is still red and no independent review has happened. V2 remains SHADOW
and Phase 20 remains FROZEN / LOCKED.

**Pilot status: blocked by design, not by accident.** Ahmet's real install
(`C:\Users\faruk\Documents\Brain-Eleven`) has `b1_human_approval=true`
(turned on 2026-09-10) but `mode` could not be promoted to `CANARY` —
`RuntimeConfig.set_mode` runs the same PRE-13 holdout quality gate before
allowing CANARY, and it still fails (precision 0.1368). This gate predates
B1 and assumes safety comes from retrieval quality, not human review; Ahmet
was asked whether to relax it now that B1 makes it redundant, and **decided
to leave it as-is** — the pilot stays blocked until PRE-13 quality genuinely
improves, rather than bypassing the gate. Current safe state:
`mode=SHADOW`, `b1_human_approval=true`.

**Engineering weak-point goal:** W-25 is the latest closed implementation
package; its package report and independent remediation review record
zero wrong-project graph leakage after the bounded HTTP fix. W-24 remains
closed as the preceding direct memory-truth safety/provenance package. Its
closure covers the direct memory-truth safety/provenance boundary at exact
code/test head `4f1fd9e` (initial code `525b116`, remediation `d78295c`,
tests `e912f44`/`4f1fd9e`); package report `80846d1` and independent review
`9048ca5` are `SHIP`. Shared capture safety covers truth content and
lifecycle notes, active registry authority gates project scope, global
project metadata is rejected, and provenance is kept outside the historical
`TruthCandidate`/worker request-hash shape. Archive/disable policy changes
replay matching operation receipts safely and readable preflight rejections
retain revision lineage. The NEW memory-ID collision is explicitly deferred
to W-24A. W-21 remains closed at `02c05c0` with complete
authority coverage, and W-20 remains closed at `db6ae44` with atomic,
no-loss embedding cache publication. W-07B native runtime
acceptance evidence is still active:
deterministic process/restart recovery has 18 passing repetitions, but the
committed native trust, latency and dogfood gates remain open. Independent
review still keeps W-07B
`FIX-FIRST / NOT ACCEPTED` because authenticated Claude/Codex trust and
native latency evidence are missing; the synthetic matrix is complete but is
not a native-client substitute. Multi-session dogfood is also missing.
Retrieval quality and V2 promotion remain deferred, and Phase 20 stays FROZEN
/ LOCKED.

W-07B-R1 is the active evidence package at exact head `ca15e31`: the synthetic
benchmark binds disposable Claude/Codex transcript roots, verifies the
canonical revision/count delta, records hook degradation instead of raising,
and now emits the complete synthetic 2-client × 4-event × cold/warm matrix.
Its focused suite is 47/47, the W06C0R1 scope suite is 36/36, and full
regression is 1345 passed, 4 skipped, 2 warnings. The synthetic run completes
20/20 canonical effects with no dead letters; the matrix is complete and its
3-second p95 bound, queue drain and 40/40 terminal delta pass, while the hook,
queue latency and all-hooks quality gates fail. Authenticated native trust and
multi-session dogfood remain open. The independent read-only follow-up review
recorded `FIX-FIRST` at `ca15e31` and found no remaining bounded-harness
P0/P1/P2 defect; W-07B stays `FIX-FIRST / NOT ACCEPTED`.

The bounded remediation **TSC-01 timezone-bound state resolution** is now
independently `SHIP`ped at exact tip `6225d4f` (implementation `9bb24d8`;
review `SHIP` in `WEAKNESS-TSC-01-TIMEZONE-INDEPENDENT-REVIEW.md`). Explicit
offset validation and bounded `STATE_CORRUPT` mapping are in place without
changing native context translation, project identity lineage or serialized
decoder behavior. **TSC-02 project identity and registry lineage** is now
independently `SHIP`ped at reviewed code head `709a9c2` (review `79120f4`):
root-reuse and registry races are rejected before delivery, valid relocation
preserves stable project IDs, and the cache-access correction leaves bytes
unchanged on stale lineage races. TSC-03 strict state decoding is deferred
until its own bounded contract; `task_state_context.py` package inversion
remains a separate IG-07 slice. W-07B's native
trust/latency/dogfood acceptance gates remain open in parallel.

W-24 direct memory-truth safety and provenance is also independently
`SHIP`ped. Its implementation/test head is `4f1fd9e`, package report
`80846d1`, and remediation review `9048ca5`. The package keeps the worker and
canonical-store implementations unchanged while adding shared safety checks,
registry authority, bounded provenance and policy-invalid replay protection.
The deferred NEW memory-ID collision is tracked as W-24A; no retrieval, V2 or
Phase 20 work was opened.

W-19B is independently `SHIP`ped at `5555318`: warning-bearing native
hook output and exceptions persist as `DEGRADED`, and doctor surfaces that as
`ATTENTION` without changing canonical data. Native client trust, latency and
dogfood still belong to W-07B. The remaining read-only findings are recorded
in `ENGINEERING-WEAK-POINTS-AUDIT.md`: legacy embedding-cache
durability/staleness (W-20), V2 authority coverage (W-21) and optional
omission enforcement (W-22) are now closed. The remaining acceptance gap is
W-07B's native trust/latency/dogfood evidence.

**IG-07 (architecture consolidation) — Slice 1 is closed.** `IG07-INVENTORY.md`
catalogs all 58 `scripts/` modules (14,014 impl LOC, 20 low/12 medium/26 high
risk). Slice 1's four bridge-only, non-authority modules (`logging_config`,
`cache_manager`, `summarizer`, `anomaly_detector`) are all migrated into
`brain_eleven/support/*` with real implementation authority, independently
reviewed and accepted (`IG07-SLICE1-INDEPENDENT-REVIEW.md`, verdict `SHIP`).
One P2 finding open (unnecessary `sys.modules` dependency lookup in
`anomaly.py` — not blocking). `MemoryStore`/`StateStore`/`ProjectRegistry`
and capture/retrieval paths remain untouched and out of scope.

**IG-07 Slice 2A is closed.** `IG07-SLICE2-PLAN.md` reassessed all 11
remaining medium-risk modules more deeply than slice 1's coarse pass —
several got reclassified to HIGH (`entity_extractor`, `knowledge_graph`,
`remember`, both `migrate-*` scripts, `install-cross-project-memory`,
`task_model`). Sub-slice 2A (`memory_provenance.py` → `chat_interface.py` →
`post_session_maintenance.py`) is fully migrated into `brain_eleven/memory/`
and `brain_eleven/runtime/`, independently reviewed and accepted
(`IG07-SLICE2A-INDEPENDENT-REVIEW.md`, verdict `SHIP`, 2026-09-11). Full
suite reproduces at 895 passed; `session_pipeline.py` and the hook budget
are unchanged. No new P0/P1/P2 findings; Slice 1's two open P2s (the
`anomaly.py` `sys.modules` lookup and a hook-timing stabilization pass)
remain open and unaffected.
`task_state_context.py` (26-27 callers, highest blast radius in the whole
inventory) is excluded from Slice 2 entirely, needs its own plan later.

**Slice 2B plan approved, not yet implemented.** `IG07-SLICE2B-PLAN.md`
covers `entity_extractor.py` and `knowledge_graph.py` — unlike slices 1/2A,
this is a bridge-direction *inversion* (package currently re-exports the
script; target is the reverse). Independently spot-checked: every cited
bridge line, docstring, and caller reference in the plan matched the actual
code exactly. Approved order: graph projection inverts first (`brain_eleven/graph/projection.py`
becomes canonical) since entity extraction already depends on it; entity
extraction inverts second into a new `brain_eleven/extraction/entities.py`.
Same five-gate discipline as before, plus an explicit object-identity
contract across package/script/bare names and revision/lock/corruption/scope
parity evidence (these two modules are HIGH risk — derived graph projection,
not simple utility code).

**IG-07 Slice 2B is fully closed (B2.1 + B2.2).** `brain_eleven/graph/projection.py`
and `brain_eleven/extraction/entities.py` are now the sole implementation
authorities for graph projection and entity extraction; `scripts/knowledge_graph.py`
and `scripts/entity_extractor.py` are adapter-only, and `scripts/remember.py`
now consumes the package surface directly instead of a dynamic legacy
loader. Both moves independently verified byte-for-byte against the
pre-migration scripts — only docstrings, one import each, and additive CLI
wrapping differ, no logic changed. Full suite reproduces at 913 passed;
`brain_eleven/graph/*` and all canonical authority paths confirmed untouched
by diff at each step. Independent reviews: `IG07-SLICE2B-B21-INDEPENDENT-REVIEW.md`
and `IG07-SLICE2B-INDEPENDENT-REVIEW.md`, both `SHIP`. This closes all of
Slice 2 (2A + 2B) from `IG07-SLICE2-PLAN.md`.

**Two-track workflow started (2026-09-11).** Codex continues on relayed
instructions as before; Claude now also implements small bounded pieces
directly via an isolated agent worktree, reviewed with the same rigor as
Codex's work before merging. First Claude-track task closed: `anomaly.py`'s
`sys.modules.get` P2 finding fixed with plain imports (`9712d39`),
independently re-verified (standalone import, focused + full suite at 913
passed, clean flake8). The intermittent
`test_cold_native_session_start_delivers_v1_within_hook_budget` flake was
investigated thoroughly (~90 reproduction attempts including cold-bytecode
and CPU-stress conditions) but could not be reproduced; no speculative fix
was applied — the test's 3s budget matches a real host-enforced hook
`timeout: 3` in `brain_eleven/runtime/install.py:113`, so loosening it would
stop validating a real contract. Left as-is; still worth a future look if it
recurs.

**Slice 2C plan approved with a scope change.** `IG07-SLICE2C-PLAN.md`
covers the three canonical-memory-writing migration tools; unlike Slice
2A/2B these touch real writes, so the plan requires idempotence, backup,
rollback, and CAS evidence, not just object-identity/adapter checks. It also
caught a real bug by code inspection: `migrate-legacy-memory.py` writes
`migrated_at`/`migration_version` unconditionally every run, and its
mutator never signals `_NoChange` to `MemoryStore.transact`, so re-running
it bumps the revision even with zero actual changes. C0 usage decision
(2026-09-11): `dedupe-validated-memory.py` is retained and migrated (C1,
now open) since it's a recurring operational need once the pilot starts
generating duplicates; `migrate-legacy-memory.py` is archived in place,
untouched, excluded from this slice (one-time schema tool, zero callers,
known bug, not worth full migration). C3 (scope migration + rollback)
remains gated on C1's independent review.

**Slice 2C step C1 (dedupe) is closed.** `brain_eleven/lifecycle/dedupe.py`
is now canonical; `scripts/dedupe-validated-memory.py` is adapter-only. This
is the first canonical-memory-writing migration in IG-07, and it met a
meaningfully higher bar than the earlier read-only slices: idempotence,
CAS-conflict, dry-run, and integrity are proven by tests that would fail if
the property didn't actually hold (verified independently, not taken on the
report's word) — e.g. a spy manager proving `save()` is called exactly once
across two `--apply` runs, and a concurrent-write test proving a stale
snapshot raises `MemoryStoreConflict` with no partial write. One intentional
behavior change: equal-timestamp tie-break is now `(timestamp, memory_id)`
instead of list order. Full suite reproduces at 920 passed.
`migrate-legacy-memory.py`, `migrate-memory-scope.py`, `MemoryStore`, and
`MemoryLifecycleManager` confirmed untouched. Independent review:
`IG07-SLICE2C-C1-INDEPENDENT-REVIEW.md`, verdict `SHIP`.

**IG-07 Slice 2C is fully closed (C1 + C3).** `brain_eleven/memory/migrations.py`
is now canonical for scope migration (`migrate_scope`/`rollback_scope`);
`scripts/migrate-memory-scope.py` is adapter-only. The rollback CAS gap the
plan flagged (`replace()` called with no `expected_revision`) is fixed and
independently verified under an actually forced concurrent-write race (not
just asserted) — `MemoryStore.replace` was monkeypatched to inject a real
concurrent write mid-call, and `MemoryStoreConflict` correctly fires with no
data loss. A second rollback of the same backup is a guarded
`already_rolled_back` no-op. Full suite reproduces at 927 passed.
`migrate-legacy-memory.py` (C2) remains archived per the C0 decision,
untouched. Independent review: `IG07-SLICE2C-C3-INDEPENDENT-REVIEW.md`,
verdict `SHIP`. One non-blocking finding: the combined report's original
commit-chain citations didn't exist in git history (pre-push local rewrite),
corrected in-file.

**IG-07 Slice 2D plan approved, scoped down to D1 only.**
`IG07-SLICE2D-PLAN.md` covers `install-cross-project-memory.py` and
`remember.py`; independently spot-checked (found and verified two real bugs
by reading the code: `uninstall()` deletes manifest-listed paths with no
containment check against `home/.claude`, and `_atomic_json_write` never
calls `fsync`). C0 decision (2026-09-12): the installer is not in active
operational use, so it's **archived as historical** — not migrated,
security findings documented but not fixed while unused. D2 (installer) is
removed from this slice. Capture-safety bridge direction set to a minimal
identity-preserving bridge (no logic copy from `capture_safety.py`).
**Slice 2D now covers only D1** (`remember.py` → `brain_eleven/memory/capture.py`),
approved for implementation — real production caller
(`scripts/remember_opt_in.py`), lock-based (not CAS) canonical write via
`memory-validator.py`'s `transact`, which the plan correctly says must not
be copied into the new capture package.

**IG-07 Slice 2D is fully closed (D1 shipped, D2 archived).**
`brain_eleven/memory/capture.py` is now canonical for manual capture
(`remember`); `scripts/remember.py` is adapter-only, and
`scripts/remember_opt_in.py` now calls the package surface directly. The
core risk — a second canonical write path — was verified absent both by
reading the code and via a structural test that greps `capture.py`'s own
source for `MemoryStore(`/`.transact(` and fails if either appears.
Safety-before-registry ordering and concurrent-replay idempotence were
proven under genuine conditions (a registry double that raises if
constructed too early; a real `ThreadPoolExecutor` race), independently
re-run, not just asserted. Full suite reproduces at 936 passed. Independent
review: `IG07-SLICE2D-D1-INDEPENDENT-REVIEW.md`, verdict `SHIP`.

**IG-07 Slice 2E is fully closed.** `IG07-SLICE2E-PLAN.md` covered
`task_model.py` → `brain_eleven/runtime/task.py`; plan independently
spot-checked (roughly 20 line-number/structural citations, all accurate)
and approved for E1 (baseline) then E2 (inversion) implementation. E1/E2
implemented (`b739241`/`c0fe23f`), evidence recorded (`7aad3d0`), package
report written (`c7f8913`). Independent review re-verified every
load-bearing claim directly rather than on the report's word: byte-identical
canonical source at the moment of the cut (27428 bytes both sides), adapter
is a genuine thin loader with zero duplicate implementation, `task_state_context.py`
diff empty across the whole range, exact before/after evaluator JSON
equality on smoke/public/holdout, full suite reproduces at 943 passed,
focused suite at 114 passed. Independent review: `IG07-SLICE2E-INDEPENDENT-REVIEW.md`,
verdict `SHIP`. One documentation-hygiene note: a later commit
(`0a8f26a`) regenerated `IG07-SLICE2E-PLAN.md` from the pre-inversion
baseline for an unrelated reason and left a stale "PLAN ONLY/REVIEW
PENDING" header despite implementation already being complete — corrected
in-file, not a functional finding.

**IG-07 Slice 2F is complete for its bounded six-gate scope.** The 26/26
caller inventory, task/state/lineage contract, AST/identity/fixture/CLI and
fail-closed tests, package inversion, thin legacy adapter, canonical coverage
and source-fingerprint paths, and full regression evidence are recorded in
`IG07-SLICE2F-PLAN.md` and `IG07-SLICE2F-PACKAGE-REPORT.md`. The focused suite
passed at 143 tests; the established full baseline passed at 1359 tests with
4 skips and 82 deselections. No task/state schema, routing, persistence or
evaluation label behavior changed. A separately commissioned independent
review is not part of this bounded execution. The work is committed as
`5da9e8c`, on top of the SRT-00 commit `cf98741`; the PRE-13 manifest with it
measured 557 (Windows) and 555 (Ubuntu) tests at 82.93% and 83.13%.

## What's next

- Keep `master` unpushed until it is a deliberate choice: a push runs the 11
  master-only Validation jobs but also lets `build.yml` publish
  `ghcr.io/…:latest` while PRE-13 quality is red. Independent review of the
  final SHA is still required before SRT-00 can be called SHIP.
- Retrieval quality is the only thing that can turn PRE-13 quality green. It
  needs its own bounded contract; the W-06C0R1 answerability corpus is the
  starting evidence. It is not started.
- The IG01-E `baseline_boundary` FAIL in the diagnostics report is by design,
  not a defect: that step runs the audit without the IG01-D pair artifact,
  which the audit requires for a `SHIP` verdict. The real `ig01e-audit` job
  supplies it and gates on `SHIP`; the same commands on a clean checkout of
  `ba0d7ab` gave `SHIP` with all nine checks passing. Making the diagnostics
  step pair-backed would stop its report from reading `FIX-FIRST`; not done.
- Finish W-07B's bounded acceptance evidence: authenticated isolated native
  Claude/Codex smoke and privacy-safe multi-session dogfood. The synthetic
  latency matrix is complete at `ca15e31`, but it cannot substitute for native
  evidence; do not mark W-07B SHIP while any native gate is absent.
- W-25 HTTP scope/authorization is closed at bounded score 9.1/10 after
  independent remediation review. Before opening another implementation, the
  next P1 must be selected from the read-only findings and given its own
  contract. Current candidates are native `Stop`/`SESSION_END` distinction,
  `doctor` health truthfulness, and canonical `.claude` reparse containment.
- IG-07 Slice 2F's bounded implementation and regression gates are complete;
  the remaining non-retrieval high-risk cluster below is the next architecture
  consolidation scope and needs its own contract before implementation.
- After 2F, the non-retrieval high-risk cluster (`memory_store.py`,
  `state_store.py`, `project_registry.py`, `memory_scope.py`,
  `memory_store_lock.py`, `memory_backup.py`, `memory-validator.py`, the
  capture/safety/truth chain) is the largest remaining untouched share of
  `IG07-INVENTORY.md`'s 26 high-risk modules (~8,500 of 14,014 total impl
  LOC) and does not depend on the retrieval-quality question below.
  Embedding/search/`context-compiler.py` remain correctly deferred per
  `IG07-INVENTORY.md` §5 until Branch B's daily-use quality resolves.
- The retrieval-quality research track (D0 recheck + BGE-M3) has run its
  cheap experiments; the next move there is Ahmet's call — see
  `D0-RECHECK-FINDINGS.md` for the options (try a third angle like eval
  corpus representativeness, or treat Branch B as settled for now).
- Claude-track pivoted to retrieval/recall quality research (2026-09-12).
  First finding is significant: `D0-RECHECK-FINDINGS.md` shows the D1
  decision's own evidence has a metric-design flaw (0.45/0.60 thresholds
  are below/at the mathematical ceiling of D0's `precision@5` metric on its
  own corpus — oracle ceiling is 0.425, independently re-derived twice) and
  a mislabeled "hybrid" control (fused real semantic search with a
  query-blind ranker). Does not reopen D1 by itself. Both recheck
  experiments now run (2026-09-12, `evals/ig01d/D0-RECHECK-RESULTS.md`):
  corrected MPNet precision is 0.259722 against the 0.425 ceiling (vs raw
  0.205); a real lexical+semantic hybrid beats semantic-only for MPNet
  (0.215) but underperforms it for E5-large (0.185 vs 0.190) — an honest,
  model-inconsistent result, not a clean case to reverse D1 on its own.
  Whether to revisit D1 next (try a third embedding model, fix the eval
  corpus's synthetic/templated queries, or accept Branch B and move on) is
  Ahmet's call.
- Vault hygiene and B1's P2 gaps are closed; pilot resumes automatically once
  PRE-13 quality clears the CANARY gate (or Ahmet revisits the gate
  decision) — no separate action needed to "start" it beyond that.
- Before starting any new work, read this file and confirm the active owner,
  branch and package. Update it with a few lines when the work session ends.

## Recent sessions

**2026-09-16** — Closed W-24 direct memory-truth safety and provenance after
one independent contract `FIX-FIRST` cycle and one independent implementation
`FIX-FIRST` remediation cycle. The final implementation/test head is
`4f1fd9e`, full regression is 1404 passed with 4 skipped and 2 warnings, and
the remediation review `9048ca5` is `SHIP`. The package keeps
`TruthCandidate`/worker request-hash compatibility, gates content and
lifecycle notes through shared capture safety, enforces registry-bound project
scope, and leaves the NEW memory-ID collision as W-24A. Phase 20 remains
FROZEN / LOCKED and V2 remains SHADOW.

**2026-09-15 (continued)** — W-07B-R1 extended the synthetic runtime evidence
harness at `ca15e31`. Disposable transcript roots and native-shaped fixtures
exercise ownership successfully; hook degradation and latency failures are
reported as bounded metrics, including canonical revision/count verification,
and all 16 client/event/cold-warm cells now have five samples each. Full
regression is 1345 passed, 4 skipped, and the package remains
`FIX-FIRST / NOT ACCEPTED` because authenticated native trust and dogfood are
still absent; a fresh independent review is pending.

**2026-09-10** — Found `master` frozen 91 commits behind five sequential,
unmerged topic branches (each closing an IG package independently).
Merged the implementation and documentation branches into `master`, refreshed
the deterministic baseline snapshot, and removed the superseded local and
remote refs. Added `README.md`/`ARCHITECTURE.md`/`CONTRIBUTING.md`, fixed stale
vault paths in `CLAUDE.md`, and registered two evidence docs in
`DOCUMENTATION-AUTHORITY.md`. The B1 contract was approved and its bounded
human-approval implementation started; no V2 or Phase 20 work was opened.
Later the same day: B1 and B2 both closed with independent `SHIP`; ran a
rigorous vault content assessment (dead Companion memory, `Kararlar/`
polluted with generic reference notes, broken wikilinks); Codex executed a
vault-hygiene pass (104 files reclassified to `Referans/`, links fixed,
Companion memory revived from real git history), independently reviewed and
accepted; closed B1's two P2 test-coverage gaps (crash/replay, cross-project
isolation), independently reviewed and accepted. Checked remote CI directly
via the GitHub Actions API instead of trusting the "not run" assumption
everyone had been carrying: it had actually been running and failing 100%
of the time since a pre-existing regression (`09935e0` dropped `import sys`
from `scripts/session_pipeline.py`, breaking a flake8 F821 check that only
Ubuntu's CI runs - Windows skips that step, so Codex's local checks never
saw it, and Linux-side local checks used a different scope). Fixed at
`647bfad`, confirmed green via the API. Agreed next step is a real-use
pilot, not more engineering, before deciding IG-04's next sub-package.

**2026-09-11** — Closed IG-07 Slice 1 (independent `SHIP`). Planned and
approved Slice 2A (`IG07-SLICE2-PLAN.md`, several modules reclassified to
HIGH risk vs. slice 1's coarse pass; `task_state_context.py` excluded).
Codex implemented all three Slice 2A modules (`memory_provenance.py`,
`chat_interface.py`, `post_session_maintenance.py`) into
`brain_eleven/memory/` and `brain_eleven/runtime/`; each independently
reviewed, full suite re-run at 895 passed, CI's exact lint command clean,
adapter-only/identity/parity checks re-verified rather than trusted from the
report. Closed with `IG07-SLICE2A-INDEPENDENT-REVIEW.md`, verdict `SHIP`.
No new P0/P1/P2 findings. Same day: Codex produced `IG07-SLICE2B-PLAN.md`
(a bridge-direction inversion for `entity_extractor.py`/`knowledge_graph.py`,
not a simple move); independently spot-checked every cited line reference
against actual code and approved for implementation in the plan's
graph-first order.

**2026-09-15** — Engineering weak-point audit continued with W-18
MemoryStore parent-directory durability and W-12A AuthorityCache
concurrency. W-18 and W-12A both received independent `SHIP`; W-12A now
serializes authority-cache read-modify-write and access refresh with the
existing sidecar lock while preserving content-free fail-open behavior.
W-07B follow-up then added intent/claim/staging/publication/service restart
evidence (18 passing repetitions), and full regression at committed head
`78c5671` passed 1291 tests with 4 skips and 2 existing dependency warnings.
Independent review kept W-07B `FIX-FIRST / NOT ACCEPTED`: native
authenticated trust, latency and dogfood evidence remain open. No V2
promotion or Phase 20 work is open.

**2026-09-15 (continued)** — W-20 embedding-cache and W-21 authority-coverage
packages were independently reviewed `SHIP`; W-22 optional-omission contract
and implementation then independently reached `SHIP` at `736c6c9`. W-22 now
enforces visible false-flag budget failures and preserves mandatory-overflow
precedence; focused coverage is 27 tests and full regression is 1338 passed,
4 skipped, 2 warnings. W-07B remains open; Phase 20 remains FROZEN / LOCKED.
