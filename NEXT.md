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

## What's next

- Decide and plan IG-07 slice 2 (medium/high-risk modules) — needs a new
  bounded plan before implementation begins, same as slice 1 did.
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
