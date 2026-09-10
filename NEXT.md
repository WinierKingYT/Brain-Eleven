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
B1 is implemented and reviewed but the `b1_human_approval` switch is off by
default — nobody's daily retrieval changes until it's explicitly turned on.
Remote exact-head CI and live native-client trust for B1 remain open,
non-blocking follow-ups (see `IG04-B1-INDEPENDENT-REVIEW.md`'s Deferred
section). V2 remains SHADOW and Phase 20 remains FROZEN / LOCKED.

## What's next

- Decide the next IG-04 sub-package (or whether the Branch B track is mature
  enough to reconsider IG-05) — Claude's call to make and propose, per the
  delegated ownership above.
- Decide whether/when to turn `b1_human_approval` on for real use, and close
  the remaining B1/B2 remote-CI and native-client-trust follow-ups or accept
  them as tracked-open.
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
