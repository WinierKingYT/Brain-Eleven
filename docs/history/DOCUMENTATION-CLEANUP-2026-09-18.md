# Documentation cleanup — 2026-09-18

This is a historical cleanup record. It does not change runtime behavior,
package authority, Phase 20, V2, or canonical stores.

## Scope

The inventory covered tracked Markdown files in the repository root and
`docs/history/`. Untracked working-tree files and the active SRT-00 changes
were left untouched.

## Archived root snapshots

Five files were moved with `git mv`; their content and Git history are intact:

- two superseded W-24 contract re-reviews (`...-02`, `...-03`);
- two superseded W-25 contract re-reviews (the initial review and `...-02`);
- the completed 2026-09-10 vault hygiene report.

No active contract, package report, final independent review, status document,
runtime map, or authority registry entry was deleted. The moved snapshots had
no live Markdown references outside the archive. `git diff --cached --check`
passed before the cleanup commit.

## Retention rule

Contracts, package reports, independent reviews, and evidence referenced by
`DOCUMENTATION-AUTHORITY.md`, `PROJECT-STATUS.md`, or
`ENGINEERING-WEAK-POINTS-AUDIT.md` remain available until a later bounded
archive pass updates every reference. Superseded material is archived rather
than deleted in accordance with `CONTRIBUTING.md`.

## Commit

Cleanup commit: `6799d3c` (`docs: archive superseded review snapshots`).
