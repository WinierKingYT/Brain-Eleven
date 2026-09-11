# Next — plain-language status

Not a contract, not evidence — just "where are we, what's next." For SHAs,
CI runs and acceptance criteria, see `PROJECT-STATUS.md`. Update this file at
the end of a work session; keep entries to a few lines.

## Where we are

Active program: **Intelligence Graduation (IG)**, replacing the old
"Phase 20" plan (frozen). Last closed package: **IG-04 B2** (review queue
dedup + deterministic ordering) — independent review `SHIP` on 2026-09-10.
B1 and B2 are both closed; no package is currently active.
`INTELLIGENCE-GRADUATION.md` documents the Branch B pivot — IG-04's slot is
the Branch B track, not the original reference/correction scope (deferred,
not deleted). The earlier D0/R0 feasibility probes remain evaluation-only
evidence; see `CODEX-RESULTS-D0.md` / `CODEX-RESULTS-R0.md`.

**Ownership as of 2026-09-10:** Ahmet delegated project management — status,
documentation, quality bar and direction — to Claude. Codex executes from
Claude's instructions; Claude has no direct connection to Codex in this
environment, so Ahmet relays. See `CONTRIBUTING.md`'s Roles section.

Canonical branch: **master**. The exact baseline snapshot check passes.
**Remote CI is confirmed green** (fixed 2026-09-10) except the long-standing,
already-documented PRE-13 quality gate. V2 remains SHADOW and Phase 20
remains FROZEN / LOCKED.

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

## What's next

- Implement Slice 2C step C1 (`dedupe-validated-memory.py` →
  `brain_eleven/lifecycle/dedupe.py`) under its own bounded contract, per
  `IG07-SLICE2C-PLAN.md` §5-7 — idempotence, CAS/stale-snapshot, and
  equal-timestamp tie-break evidence required, not just identity/adapter
  checks. Independent review required before C3 opens.
- Vault hygiene and B1's P2 gaps are closed; pilot resumes automatically once
  PRE-13 quality clears the CANARY gate (or Ahmet revisits the gate
  decision) — no separate action needed to "start" it beyond that.
- Before starting any new work, read this file and confirm the active owner,
  branch and package. Update it with a few lines when the work session ends.

## Recent sessions

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
