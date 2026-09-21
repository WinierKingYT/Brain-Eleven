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

## Second pass

After reviewing the published GitHub root, a second pass moved another 56
documents. Current program material now lives under `docs/programs/`, reusable
contract records under `docs/contracts/`, and closed plans, reports, reviews,
audits, and evidence under their corresponding `docs/history/` groups.

The repository root now retains 25 Markdown paths: the small navigation and
status surface plus evaluation-bound documents whose exact root paths are part
of frozen source/scope checks. Moving those remaining evaluation documents
would change code-backed evidence contracts, so they were deliberately kept.

## Final root consolidation

The remaining IG01 and W06C0/W06C0R1 documents were subsequently moved after
their code-backed path consumers were updated explicitly. IG contracts now
live in `docs/contracts/`, package evidence in `docs/history/reports/`, and the
engineering weakness baseline in `docs/audits/`. Historical path names remain
accepted by frozen scope allowlists where replay compatibility requires them.

The repository root is reduced to nine maintained entry-point documents.

## Status correction

`NEXT.md` was aligned with `PROJECT-STATUS.md`: SRT-00 is closed with green CI,
but does not carry an independent `SHIP`, and the frozen PRE-13 quality gate
remains red.

## Retention

Archived files retain their content and Git history. Current navigation begins
at `README.md`, `PROJECT-STATUS.md`, `NEXT.md`, and
`DOCUMENTATION-AUTHORITY.md`.
