# Next — plain-language status

Not a contract, not evidence — just "where are we, what's next." For SHAs,
CI runs and acceptance criteria, see `PROJECT-STATUS.md`. Update this file at
the end of a work session; keep entries to a few lines.

## Where we are

Active program: **Intelligence Graduation (IG)**, replacing the old
"Phase 20" plan (frozen). Last closed package: **IG-03** (semantic
extraction). **IG-04 B1 implementation is now active** under the approved
human-approval contract. The earlier D0/R0 feasibility probes remain
evaluation-only evidence; see `CODEX-RESULTS-D0.md` /
`CODEX-RESULTS-R0.md`.

Canonical branch: **master**. The topic branches were merged and removed
locally and on GitHub; only `master` remains remotely. The exact baseline
snapshot check passes on current master. Ahmet approved B1 on 2026-09-10;
Codex is implementing the bounded review boundary. V2 remains SHADOW and
Phase 20 remains FROZEN / LOCKED.

## What's next

- Finish the bounded B1 review boundary, focused tests and evidence, then
  obtain the independent read-only review. Keep V2 SHADOW and Phase 20
  FROZEN / LOCKED.
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
