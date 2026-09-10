# Next — plain-language status

Not a contract, not evidence — just "where are we, what's next." For SHAs,
CI runs and acceptance criteria, see `PROJECT-STATUS.md`. Update this file at
the end of a work session; keep entries to a few lines.

## Where we are

Active program: **Intelligence Graduation (IG)**, replacing the old
"Phase 20" plan (frozen). Last closed package: **IG-02** (autonomous
capture). **IG-04 is not open yet** — before opening it, two feasibility
probes (D0, R0) were run to de-risk the retrieval approach; see
`CODEX-RESULTS-D0.md` / `CODEX-RESULTS-R0.md`. Neither probe opens IG-04 by
itself.

Canonical branch: **master**. The topic branches were merged and removed
locally and on GitHub; only `master` remains remotely. The exact baseline
snapshot check passes on current master. Branch B/B1 implementation has not
started; owner and kickoff remain an explicit Ahmet decision.

## What's next

- Decide the retrieval approach for IG-04 based on the D0/R0 probe results,
  then open IG-04 under its own contract.
- Before starting any new work, read this file and confirm the active owner,
  branch and package. Update it with a few lines when the work session ends.

## Recent sessions

**2026-09-10** — Found `master` frozen 91 commits behind five sequential,
unmerged topic branches (each closing an IG package independently).
Merged the implementation and documentation branches into `master`, refreshed
the deterministic baseline snapshot, and removed the superseded local and
remote refs. Added `README.md`/`ARCHITECTURE.md`/`CONTRIBUTING.md`, fixed stale
vault paths in `CLAUDE.md`, and registered two evidence docs in
`DOCUMENTATION-AUTHORITY.md`. The full regression is green; B1 has not started.
