# Documentation cleanup — 2026-09-22

This historical record describes a structure-only cleanup. It does not change
runtime behavior, package verdicts, evaluation contracts, V2 status, Phase 20,
or canonical stores.

## Scope

- Moved 89 completed package reports, independent reviews, and generated result
  records out of the repository root with `git mv`.
- Grouped them under `docs/history/reports/`, `docs/history/reviews/`, and
  `docs/history/evidence/`.
- Updated references in active documentation to the new paths.
- Kept evaluation-bound IG01 and W06C0/W06C0R1 package reports at the root
  because runtime evaluation code addresses those exact paths.
- Left contracts at the root for a later authority-focused pass.
- Left all pre-existing untracked evaluation output and unrelated working-tree
  changes untouched.

## Status correction

`NEXT.md` was aligned with `PROJECT-STATUS.md`: SRT-00 is closed with green CI,
but does not carry an independent `SHIP`, and the frozen PRE-13 quality gate
remains red.

## Retention

Archived files retain their content and Git history. Current navigation begins
at `README.md`, `PROJECT-STATUS.md`, `NEXT.md`, and
`DOCUMENTATION-AUTHORITY.md`.
