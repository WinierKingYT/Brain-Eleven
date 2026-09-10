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

## What's next

- Decide the retrieval approach for IG-04 based on the D0/R0 probe results,
  then open IG-04 under its own contract.
- Delete the 6 stale branches on GitHub that were superseded when `master`
  was fast-forwarded on 2026-09-10 (`ig/00-freeze-baseline`,
  `ig/01-evaluation-foundation`, `ig/02-autonomous-capture`,
  `ig/03-semantic-extraction`, `codex/ig-provider`, `codex/ig-rethink`) —
  needs manual deletion in the GitHub UI, the git remote here can't do it.
- Fix `tests/test_evaluation_baseline_snapshot.py::test_baseline_v2_snapshot_matches_current_public_suite_inputs`
  — fails on current `master`; `evals/reports/baseline-v3.json` no longer
  matches what the code deterministically produces. Not yet root-caused.

## Recent sessions

**2026-09-10** — Found `master` frozen 91 commits behind five sequential,
unmerged topic branches (each closing an IG package independently).
Fast-forwarded `master` to the tip. Added `README.md`/`ARCHITECTURE.md`/
`CONTRIBUTING.md` (none existed before — only status/contract docs did).
Fixed stale vault paths in `CLAUDE.md` (wrong folder name, files that don't
exist). Registered two unregistered evidence docs in
`DOCUMENTATION-AUTHORITY.md`. Added this file.
